"""
CC_victoria_goj_integration.py
===============================
Victoria — GOJ Voice Agent Integration (Retell AI)
Gold Health Systems · Garden of Joy Adult Day Care

⚠️  STATUS: DEAD — Retell API key expired.
    Activation requires: renew Retell subscription → new API key →
    update RETELL_API_KEY in ~/.rex/config.json → confirm VICTORIA_AGENT_ID.
    See CC_VOICE_INTEGRATION_GUIDE.md for full reactivation checklist.

Mounts as FastAPI router at prefix="/victoria" inside main REX app.
Add to main.py:
    from CC_victoria_goj_integration import victoria_router
    app.include_router(victoria_router, prefix="/victoria")

Capabilities:
    1. Outbound auth-expiry reminders  (daily 10am trigger)
    2. Inbound sick-day callout handler (Retell webhook)
    3. Driver no-show alert             (called by scheduler at 7:45am)
    4. Auth-expired family notification (triggered by auth status change)

HIPAA NOTE: Victoria handles PHI (client names + medical context).
    - All calls are logged to victoria_call_log in auth_tracker.db.
    - Retell MUST have a BAA in place before going live.
    - PHI never leaves the local perimeter except via encrypted Retell call.
"""

import json
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("victoria")

# ── Configuration constants — fill after Retell reactivation ──────────────────
RETELL_API_KEY: str = os.getenv("RETELL_API_KEY", "")          # ← BLOCKED: key expired
VICTORIA_AGENT_ID: str = os.getenv("VICTORIA_AGENT_ID", "")   # ← from Retell dashboard
VICTORIA_PHONE_NUMBER: str = os.getenv("VICTORIA_PHONE_NUMBER") or os.getenv("VICTORIA_FROM_PHONE", "+164****3781")
RETELL_WEBHOOK_SECRET: str = os.getenv("RETELL_WEBHOOK_SECRET", "")

# Database path — never changes, per CLAUDE.md
AUTH_DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

# Telegram config (reads from rex_notify_config.json matching RexNotify pattern)
NOTIFY_CONFIG_PATH = Path.home() / "Desktop" / "REX" / "rex_notify_config.json"

# ── Victoria's call scripts ────────────────────────────────────────────────────
TOMORROW_CONFIRMATION_SCRIPT = """
Hello, this is Victoria calling from Garden of Joy Adult Day Care.
I'm calling to confirm that {client_name} will be attending tomorrow,
{tomorrow_date}. Please press 1 to confirm attendance or 2 if
{client_name} will not be attending. If you have any questions,
please call us during business hours. Thank you!
"""


AUTH_REMINDER_SCRIPT = """
Hello, this is Victoria calling from Garden of Joy Adult Day Care.
I'm reaching out because {client_name}'s authorization expires on {expiry_date}.
Please bring your renewal documents to the center as soon as possible.
If you have questions, please call us during business hours.
Thank you, and have a wonderful day.
"""

AUTH_EXPIRED_SCRIPT = """
Hello, this is Victoria calling from Garden of Joy Adult Day Care.
I'm calling about {client_name}'s participation in our program.
Unfortunately, {client_name}'s authorization has expired and we are
unable to schedule attendance until the authorization is renewed.
Please contact your Medicaid coordinator or call us for assistance.
Thank you.
"""

SICK_DAY_ACKNOWLEDGMENT_SCRIPT = """
Thank you for calling Garden of Joy. I've noted that {client_name}
will not be attending today. Your transportation and meal have been updated.
We hope {client_name} feels better soon. Have a good day.
"""

DRIVER_NOSHOW_SCRIPT = """
Hello, this is an automated alert from Garden of Joy Adult Day Care.
Driver {driver_name} has not started their route as of 7:45 AM.
You are the backup driver for today. Please call the office immediately
at your earliest convenience. Thank you.
"""


# ── Pydantic models ────────────────────────────────────────────────────────────

class AuthReminderRequest(BaseModel):
    client_id: int
    override_phone: Optional[str] = None  # for testing without DB


class DriverNoShowRequest(BaseModel):
    driver_name: str
    backup_driver_phone: str
    backup_driver_name: str


class RetellWebhookEvent(BaseModel):
    event: str  # "call_started" | "call_ended" | "call_analyzed"
    call: dict[str, Any]


class VictoriaCallLog(BaseModel):
    client_id: Optional[int]
    call_type: str
    phone_number: str
    retell_call_id: Optional[str]
    status: str
    notes: Optional[str] = None


# ── Router ─────────────────────────────────────────────────────────────────────
victoria_router = APIRouter(tags=["victoria"])


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_db_conn() -> sqlite3.Connection:
    """Open auth_tracker.db in read/write mode with row factory."""
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_call_log_table() -> None:
    """
    Idempotent migration — creates victoria_call_log if it doesn't exist.
    Safe to call on every startup.
    """
    with _get_db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS victoria_call_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   INTEGER,
                call_type   TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                retell_call_id TEXT,
                status      TEXT NOT NULL,
                notes       TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vcl_client
            ON victoria_call_log(client_id)
        """)
        conn.commit()


def _log_call(
    call_type: str,
    phone_number: str,
    retell_call_id: Optional[str],
    status: str,
    client_id: Optional[int] = None,
    notes: Optional[str] = None,
    transcript: Optional[str] = None,
    recording_url: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    sentiment: Optional[str] = None,
    call_summary: Optional[str] = None,
) -> int:
    """Write or update a row in victoria_call_log. Returns the row id.
    
    Uses retell_call_id as the key for upserts: call_started inserts,
    call_ended/call_analyzed update the existing row with full data.
    """
    _ensure_call_log_table()
    with _get_db_conn() as conn:
        if retell_call_id:
            existing = conn.execute(
                "SELECT id FROM victoria_call_log WHERE retell_call_id = ?",
                (retell_call_id,)
            ).fetchone()
        
        if retell_call_id and existing:
            # Update existing row with end-of-call data
            conn.execute("""
                UPDATE victoria_call_log SET
                    status = ?, notes = ?, transcript = ?,
                    recording_url = ?, duration_seconds = ?,
                    sentiment = ?, call_summary = ?,
                    completed_at = datetime('now')
                WHERE retell_call_id = ?
            """, (status, notes, transcript, recording_url,
                  duration_seconds, sentiment, call_summary, retell_call_id))
            conn.commit()
            return existing["id"]
        else:
            # Insert new row
            cur = conn.execute("""
                INSERT INTO victoria_call_log
                (client_id, call_type, phone_number, retell_call_id, status,
                 notes, transcript, recording_url, duration_seconds,
                 sentiment, call_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (client_id, call_type, phone_number, retell_call_id, status,
                  notes, transcript, recording_url, duration_seconds,
                  sentiment, call_summary))
            conn.commit()
            return cur.lastrowid


def _get_expiring_clients(days_ahead: int = 7) -> list[sqlite3.Row]:
    """
    Return clients whose auth expires within `days_ahead` days.
    Joins authorization → clients on client_name.
    """
    cutoff = (date.today() + timedelta(days=days_ahead)).isoformat()
    today = date.today().isoformat()

    with _get_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.client_id, c.name, c.phone,
                   a.service_end_date AS expiry_date,
                   a.status
            FROM authorization a
            JOIN clients c ON c.name = a.client_name
            WHERE a.status IN ('ACTIVE', 'PENDING RENEWAL')
              AND a.service_end_date BETWEEN ? AND ?
            ORDER BY a.service_end_date ASC
            """,
            (today, cutoff),
        ).fetchall()

    return rows


_WEEKDAY_MAP = {
    0: "M",   # Monday
    1: "T",   # Tuesday
    2: "W",   # Wednesday
    3: "TH",  # Thursday
    4: "F",   # Friday
    5: "SU",  # Saturday
    # Sunday (6) — GOJ closed, no schedule
}


def _get_tomorrow_clients() -> list[sqlite3.Row]:
    """
    Return clients scheduled for TOMORROW — the sign-in sheet.
    Queries client_schedule (canonical schedule table) joined to clients
    for phone numbers. Falls back to clients.day_*_actual columns.
    """
    tomorrow = date.today() + timedelta(days=1)
    day_code = _WEEKDAY_MAP.get(tomorrow.weekday())
    if not day_code:
        logger.info(f"Tomorrow is Sunday — GOJ closed, no calls")
        return []

    with _get_db_conn() as conn:
        # Try client_schedule first (canonical)
        rows = conn.execute(
            """
            SELECT c.client_id, c.name, c.phone, cs.day_of_week, cs.shift
            FROM client_schedule cs
            JOIN clients c ON c.name = cs.client_name
            WHERE cs.day_of_week = ?
              AND c.active = 1
            ORDER BY c.name
            """,
            (day_code,),
        ).fetchall()

        if rows:
            logger.info(
                f"Victoria tomorrow-clients from client_schedule: "
                f"{len(rows)} for {tomorrow.strftime('%A')} ({day_code})"
            )
            return rows

        # Fallback: clients table day_*_actual columns
        day_col = {
            "M": "day_M_actual", "T": "day_T_actual", "W": "day_W_actual",
            "TH": "day_TH_actual", "F": "day_F_actual", "SU": "day_Su_actual",
        }[day_code]
        rows = conn.execute(
            f"""
            SELECT client_id, name, phone
            FROM clients
            WHERE {day_col} = 1 AND active = 1
            ORDER BY name
            """
        ).fetchall()

        logger.info(
            f"Victoria tomorrow-clients from clients.{day_col}: "
            f"{len(rows)} for {tomorrow.strftime('%A')}"
        )
        return rows


def _get_client_by_id(client_id: int) -> Optional[sqlite3.Row]:
    """Fetch a single client row by primary key."""
    with _get_db_conn() as conn:
        return conn.execute(
            "SELECT * FROM clients WHERE client_id = ?", (client_id,)
        ).fetchone()


def _update_attendance_sick(client_id: int, note: str = "Sick — called in via Victoria") -> None:
    """
    Mark today's attendance as absent/sick.
    Writes to attendance_log if it exists, otherwise logs the gap.
    """
    today_str = date.today().isoformat()
    with _get_db_conn() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "attendance_log" in tables:
            conn.execute(
                """INSERT OR REPLACE INTO attendance_log
                   (client_id, log_date, status, notes)
                   VALUES (?, ?, 'ABSENT', ?)""",
                (client_id, today_str, note),
            )
            conn.commit()
            logger.info(f"✅ Attendance marked absent for client {client_id} on {today_str}")
        else:
            logger.warning(
                "attendance_log table not found — sick-day not persisted to DB. "
                "Create attendance_log(client_id, log_date, status, notes) to enable."
            )


# ── Retell SDK wrapper ─────────────────────────────────────────────────────────

def _retell_create_call(
    to_number: str,
    metadata: dict[str, Any],
    agent_id: Optional[str] = None,
    dynamic_variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Create an outbound phone call via Retell REST API.
    Uses urllib (no extra deps) to avoid import-time failures when Retell SDK
    is not installed. Falls back gracefully when RETELL_API_KEY is missing.

    dynamic_variables → injected into agent prompt via retell_llm_dynamic_variables
    so Victoria actually says the client's name, date, etc.
    """
    if not RETELL_API_KEY:
        raise RuntimeError(
            "RETELL_API_KEY is not set — Victoria is DEAD (key expired). "
            "Renew Retell subscription at retell.ai and update the key."
        )
    resolved_agent_id = agent_id or VICTORIA_AGENT_ID
    if not resolved_agent_id:
        raise RuntimeError(
            "VICTORIA_AGENT_ID is not set — check Retell dashboard after reactivation."
        )

    payload_dict = {
        "from_number": VICTORIA_PHONE_NUMBER,
        "to_number": to_number,
        "override_agent_id": resolved_agent_id,
        "ignore_e164_validation": True,
        "metadata": metadata,
    }
    if dynamic_variables:
        payload_dict["retell_llm_dynamic_variables"] = dynamic_variables
    
    payload = json.dumps(payload_dict).encode("utf-8")
    
    import http.client, ssl
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
    conn.request(
        "POST", "/v2/create-phone-call",
        body=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RETELL_API_KEY}",
        }
    )
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    if resp.status >= 400:
        raise RuntimeError(f"Retell API error {resp.status}: {body}")
    return json.loads(body)


def _send_telegram(message: str) -> None:
    """Fire-and-forget Telegram alert using the same config as RexNotify."""
    try:
        cfg_path = NOTIFY_CONFIG_PATH
        if not cfg_path.exists():
            logger.warning("Telegram notify config not found — skipping alert")
            return
        cfg = json.loads(cfg_path.read_text())
        token = cfg.get("telegram_token")
        chat_id = cfg.get("telegram_chat_id")
        if not token or not chat_id:
            logger.warning("Telegram not configured — skipping alert")
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps(
            {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                logger.error(f"Telegram error: {result}")
    except Exception as exc:
        logger.error(f"Telegram send failed: {exc}")


# ── Background task helpers ────────────────────────────────────────────────────

def _do_auth_reminder_call(client_id: int, phone_override: Optional[str]) -> None:
    """
    Blocking call placed in a BackgroundTask.
    Fetches client, dials via Retell, logs result.
    client_id=0 is a test mode: uses phone_override directly, skips DB lookup.
    """
    # TEST MODE: client_id=0 → use phone_override directly
    if client_id == 0 and phone_override:
        logger.info(f"Test call to {phone_override} — skipping DB lookup")
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%A, %B %d")
        result = _retell_create_call(
            to_number=phone_override,
            metadata={"test_call": True, "source": "auth_reminder_test"},
            dynamic_variables={"client_name": "Kato", "tomorrow_date": tomorrow_str},
        )
        # Log to victoria_call_log for database access
        try:
            with _get_db_conn() as conn:
                conn.execute(
                    "INSERT INTO victoria_call_log (client_id, call_type, phone_number, retell_call_id, status, created_at) "
                    "VALUES (0, 'test_call', ?, ?, 'registered', datetime('now'))",
                    (phone_override, result.get("call_id", ""))
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not log test call: {e}")
        return

    client = _get_client_by_id(client_id)
    if not client:
        logger.error(f"Client {client_id} not found for auth reminder call")
        return

    phone = phone_override or client["phone"] or client.get("emergency_contact_phone")
    if not phone:
        logger.warning(f"No phone number for client {client_id} — skipping reminder call")
        return

    client_name = client["name"]

    # Determine expiry date from auth table
    expiry_date = "your upcoming renewal date"
    try:
        with _get_db_conn() as conn:
            row = conn.execute(
                "SELECT service_end_date FROM authorization WHERE client_id = ? "
                "ORDER BY service_end_date ASC LIMIT 1",
                (client_id,),
            ).fetchone()
            if row:
                expiry_date = row["service_end_date"]
    except Exception as exc:
        logger.warning(f"Could not fetch expiry date for client {client_id}: {exc}")

    metadata = {
        "call_type": "auth_reminder",
        "client_id": client_id,
        "client_name": client_name,
        "expiry_date": expiry_date,
        "script_hint": AUTH_REMINDER_SCRIPT.format(
            client_name=client_name, expiry_date=expiry_date
        ).strip(),
    }

    try:
        call = _retell_create_call(to_number=phone, metadata=metadata,
                                     dynamic_variables={"client_name": client_name, "expiry_date": expiry_date})
        call_id = call.get("call_id", "unknown")
        _log_call(
            call_type="auth_reminder",
            phone_number=phone,
            retell_call_id=call_id,
            status="initiated",
            client_id=client_id,
            notes=f"expiry={expiry_date}",
        )
        logger.info(f"📞 Victoria auth reminder call initiated: client={client_id} call_id={call_id}")
        _send_telegram(
            f"📞 <b>Victoria</b> · auth reminder call initiated\n"
            f"Client: {client_name} (id={client_id})\n"
            f"Phone: {phone}\n"
            f"Expiry: {expiry_date}\n"
            f"Retell call_id: {call_id}"
        )
    except RuntimeError as exc:
        _log_call(
            call_type="auth_reminder",
            phone_number=phone,
            retell_call_id=None,
            status="failed",
            client_id=client_id,
            notes=str(exc),
        )
        logger.error(f"Victoria call failed for client {client_id}: {exc}")
        _send_telegram(
            f"⚠️ <b>Victoria</b> · auth reminder call FAILED\n"
            f"Client: {client_name} (id={client_id})\n"
            f"Error: {exc}"
        )


def _do_expired_auth_call(client_id: int) -> None:
    """Notify family that the client's auth has expired."""
    client = _get_client_by_id(client_id)
    if not client:
        logger.error(f"Client {client_id} not found for expired auth call")
        return

    phone = client.get("emergency_contact_phone") or client.get("phone")
    if not phone:
        logger.warning(f"No phone number for client {client_id} — cannot notify family")
        return

    client_name = client["name"]
    metadata = {
        "call_type": "auth_expired",
        "client_id": client_id,
        "client_name": client_name,
        "script_hint": AUTH_EXPIRED_SCRIPT.format(client_name=client_name).strip(),
    }

    try:
        call = _retell_create_call(to_number=phone, metadata=metadata,
                                     dynamic_variables={"client_name": client_name, "expiry_date": expiry_date})
        call_id = call.get("call_id", "unknown")
        _log_call(
            call_type="auth_expired",
            phone_number=phone,
            retell_call_id=call_id,
            status="initiated",
            client_id=client_id,
        )
        logger.info(f"📞 Victoria expired-auth call initiated: client={client_id}")
        _send_telegram(
            f"📞 <b>Victoria</b> · auth EXPIRED call sent\n"
            f"Client: {client_name} (id={client_id})\nPhone: {phone}"
        )
    except RuntimeError as exc:
        _log_call(
            call_type="auth_expired",
            phone_number=phone,
            retell_call_id=None,
            status="failed",
            client_id=client_id,
            notes=str(exc),
        )
        logger.error(f"Victoria expired-auth call failed: {exc}")


def _do_tomorrow_confirmation_call(client_id: int, phone_override: Optional[str]) -> None:
    """
    Call a client to confirm attendance for tomorrow.
    Blocking call placed in a BackgroundTask.
    """
    client = _get_client_by_id(client_id)
    if not client:
        logger.error(f"Client {client_id} not found for tomorrow confirmation call")
        return

    phone = phone_override or client["phone"]
    if not phone:
        logger.warning(f"No phone number for client {client_id} — skipping tomorrow call")
        return

    client_name = client["name"]
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%A, %B %d")

    metadata = {
        "call_type": "tomorrow_confirmation",
        "client_id": client_id,
        "client_name": client_name,
        "tomorrow_date": tomorrow.isoformat(),
        "script_hint": TOMORROW_CONFIRMATION_SCRIPT.format(
            client_name=client_name, tomorrow_date=tomorrow_str
        ).strip(),
    }

    try:
        call = _retell_create_call(to_number=phone, metadata=metadata,
                                     dynamic_variables={"client_name": client_name, "tomorrow_date": tomorrow_str})
        call_id = call.get("call_id", "unknown")
        _log_call(
            call_type="tomorrow_confirmation",
            phone_number=phone,
            retell_call_id=call_id,
            status="initiated",
            client_id=client_id,
            notes=f"confirming attendance for {tomorrow.isoformat()}",
        )
        logger.info(f"📞 Victoria tomorrow confirmation: client={client_id} call_id={call_id}")
        _send_telegram(
            f"📞 <b>Victoria</b> · tomorrow confirmation call initiated\n"
            f"Client: {client_name} (id={client_id})\n"
            f"Phone: {phone}\n"
            f"For: {tomorrow_str}\n"
            f"Retell call_id: {call_id}"
        )
    except RuntimeError as exc:
        _log_call(
            call_type="tomorrow_confirmation",
            phone_number=phone,
            retell_call_id=None,
            status="failed",
            client_id=client_id,
            notes=str(exc),
        )
        logger.error(f"Victoria tomorrow call failed for client {client_id}: {exc}")
        _send_telegram(
            f"⚠️ <b>Victoria</b> · tomorrow confirmation call FAILED\n"
            f"Client: {client_name} (id={client_id})\n"
            f"Error: {exc}"
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@victoria_router.get("/preview-tomorrow")
async def preview_tomorrow_clients() -> dict[str, Any]:
    """
    Dry-run: returns the list of clients Victoria WOULD call tomorrow.
    No calls are placed. Use this to verify the sign-in sheet list.
    """
    tomorrow = date.today() + timedelta(days=1)
    clients = _get_tomorrow_clients()
    return {
        "dry_run": True,
        "date": tomorrow.isoformat(),
        "day": tomorrow.strftime("%A"),
        "count": len(clients),
        "clients": [
            {
                "client_id": r["client_id"],
                "name": r["name"],
                "phone": r["phone"],
            }
            for r in clients
        ],
    }


@victoria_router.get("/agent-info")
async def victoria_agent_info() -> dict[str, Any]:
    """
    Proxy to Retell API — returns the actual agent voice/language config.
    Uses REX's loaded RETELL_API_KEY so no credential handling needed here.
    """
    if not RETELL_API_KEY:
        return {"error": "RETELL_API_KEY not configured"}

    try:
        result = []
        # Try agent listing, then specific known agent
        for url in [
            "https://api.retellai.com/v1/list-agents",
            "https://api.retellai.com/agent",
        ]:
            try:
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {RETELL_API_KEY}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    agents = data if isinstance(data, list) else [data]
                    for a in agents:
                        reng = a.get("response_engine", {})
                        result.append({
                            "agent_name": a.get("agent_name"),
                            "agent_id": a.get("agent_id"),
                            "voice_id": a.get("voice_id"),
                            "language": a.get("language"),
                            "response_engine": {"type": reng.get("type"), "voice_id": reng.get("voice_id")} if reng else None,
                        })
                    if result:
                        return {"api_url": url, "agents": result}
            except urllib.error.HTTPError as e:
                logger.info(f"Retell {url}: HTTP {e.code}")
                continue

        # Fallback: get specific agent
        agent_id = VICTORIA_AGENT_ID or "agent_8a326510567e7dc3e2dc5221df"
        try:
            req = urllib.request.Request(
                f"https://api.retellai.com/get-agent/{agent_id}",
                headers={"Authorization": f"Bearer {RETELL_API_KEY}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                a = json.loads(resp.read())
                reng = a.get("response_engine", {})
                result.append({
                    "agent_name": a.get("agent_name"),
                    "agent_id": a.get("agent_id"),
                    "voice_id": a.get("voice_id"),
                    "language": a.get("language"),
                    "response_engine": {"type": reng.get("type"), "voice_id": reng.get("voice_id")} if reng else None,
                })
                return {"api_url": f"v2/get-agent/{agent_id}", "agents": result}
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            return {"error": f"Get agent HTTP {e.code}: {body}"}

        return {"error": "All endpoints failed", "agents": result}
    except Exception as exc:
        return {"error": str(exc)}


@victoria_router.get("/status")
async def victoria_status() -> dict[str, Any]:
    """
    Current call queue and Retell connection status.
    Returns live queue from victoria_call_log (last 50 rows).
    """
    _ensure_call_log_table()
    retell_live = bool(RETELL_API_KEY and VICTORIA_AGENT_ID)
    try:
        with _get_db_conn() as conn:
            recent_calls = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM victoria_call_log ORDER BY id DESC LIMIT 50"
                ).fetchall()
            ]
            pending = [c for c in recent_calls if c["status"] == "initiated"]
    except Exception as exc:
        logger.error(f"Status query failed: {exc}")
        recent_calls = []
        pending = []

    expiring_soon = []
    try:
        expiring_soon = [
            {
                "client_id": row["client_id"],
                "name": row["name"],
                "expiry": row["expiry_date"],
                "status": row["status"],
            }
            for row in _get_expiring_clients(days_ahead=7)
        ]
    except Exception as exc:
        logger.warning(f"Could not fetch expiring clients: {exc}")

    return {
        "agent": "victoria",
        "retell_configured": retell_live,
        "retell_blocked": not bool(RETELL_API_KEY),
        "block_reason": (
            "RETELL_API_KEY missing or expired — renew at retell.ai"
            if not retell_live
            else None
        ),
        "victoria_agent_id": VICTORIA_AGENT_ID or "NOT SET",
        "victoria_phone": VICTORIA_PHONE_NUMBER,
        "pending_calls": len(pending),
        "expiring_auths_7d": len(expiring_soon),
        "expiring_clients": expiring_soon,
        "recent_calls": recent_calls,
    }


@victoria_router.post("/call/auth-reminder")
async def trigger_auth_reminder(
    req: AuthReminderRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Trigger an outbound auth-expiry reminder call for a specific client.
    Call is placed asynchronously via BackgroundTasks.
    """
    background_tasks.add_task(
        _do_auth_reminder_call, req.client_id, req.override_phone
    )
    return {
        "queued": True,
        "client_id": req.client_id,
        "note": "Call placed in background. Check /victoria/status for result.",
    }


@victoria_router.post("/call/run-daily-reminders")
async def run_daily_reminders(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Call TOMORROW'S scheduled clients to confirm attendance.
    Reads the sign-in sheet (client_schedule + clients tables).
    Intended trigger: daily cron / n8n at 10:00 AM.

    n8n webhook node → POST http://localhost:8000/victoria/call/run-daily-reminders
    """
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_clients = _get_tomorrow_clients()
    if not tomorrow_clients:
        return {
            "queued": 0,
            "message": f"No clients scheduled for {tomorrow.strftime('%A')} ({tomorrow.isoformat()}).",
        }

    count = 0
    for row in tomorrow_clients:
        client_id = row["client_id"]
        client_name = row["name"]
        background_tasks.add_task(_do_tomorrow_confirmation_call, client_id, None)
        count += 1
        logger.info(
            f"Queued tomorrow-confirmation for client {client_id}: {client_name}"
        )

    _send_telegram(
        f"📞 <b>Victoria</b> · tomorrow confirmation run queued\n"
        f"{count} client(s) for {tomorrow.strftime('%A')} {tomorrow.isoformat()}\n"
        f"Calling to confirm attendance for tomorrow's sign-in sheet."
    )
    return {
        "queued": count,
        "date": tomorrow.isoformat(),
        "clients": [
            {"client_id": r["client_id"], "name": r["name"], "phone": r["phone"]}
            for r in tomorrow_clients
        ],
    }


@victoria_router.post("/call/auth-expired-notify")
async def auth_expired_notify(
    req: AuthReminderRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Notify family contact that client's authorization has expired.
    Trigger this endpoint when a client's status transitions to EXPIRED.
    """
    background_tasks.add_task(_do_expired_auth_call, req.client_id)
    return {
        "queued": True,
        "client_id": req.client_id,
        "note": "Family notification call queued.",
    }


@victoria_router.post("/test-sync-call")
async def test_sync_call(req: dict) -> dict[str, Any]:
    """Synchronous test call — bypasses background tasks."""
    phone = req.get("phone", "+134****2860")
    name = req.get("name", "Kato")
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    months_ru = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
    tomorrow_str = f"{tomorrow.day} {months_ru[tomorrow.month-1]} {tomorrow.year}"
    
    try:
        result = _retell_create_call(
            to_number=phone,
            metadata={"call_type": "test_sync", "client_name": name},
            dynamic_variables={"client_name": name, "tomorrow_date": tomorrow_str}
        )
        return {"success": True, "call_id": result.get("call_id"), "status": result.get("call_status")}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}


@victoria_router.post("/call/driver-noshow")
async def driver_noshow_alert(
    req: DriverNoShowRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Call the backup driver when primary driver has not started route by 7:45am.
    Trigger: n8n or scheduled task checks driver route status at 7:45am.
    """
    metadata = {
        "call_type": "driver_noshow",
        "driver_name": req.driver_name,
        "backup_driver_name": req.backup_driver_name,
        "script_hint": DRIVER_NOSHOW_SCRIPT.format(
            driver_name=req.driver_name
        ).strip(),
    }

    def _place_call() -> None:
        try:
            call = _retell_create_call(
                to_number=req.backup_driver_phone, metadata=metadata
            )
            call_id = call.get("call_id", "unknown")
            _log_call(
                call_type="driver_noshow",
                phone_number=req.backup_driver_phone,
                retell_call_id=call_id,
                status="initiated",
                notes=f"no-show={req.driver_name} backup={req.backup_driver_name}",
            )
            _send_telegram(
                f"🚗 <b>Victoria</b> · driver no-show alert\n"
                f"Primary driver: {req.driver_name} — not started by 7:45am\n"
                f"Calling backup: {req.backup_driver_name} ({req.backup_driver_phone})"
            )
        except RuntimeError as exc:
            logger.error(f"Driver no-show call failed: {exc}")
            _send_telegram(
                f"⚠️ <b>Victoria</b> · driver no-show call FAILED\n"
                f"Backup: {req.backup_driver_name}\nError: {exc}"
            )

    background_tasks.add_task(_place_call)
    return {
        "queued": True,
        "backup_driver": req.backup_driver_name,
        "note": "Backup driver call queued.",
    }


@victoria_router.post("/webhook/inbound")
async def victoria_inbound_webhook(request: Request) -> dict[str, Any]:
    """
    Retell webhook endpoint for inbound call events.
    Handles: call_started, call_ended (with transcript), call_analyzed.

    Configure in Retell dashboard:
        Webhook URL: https://<your-domain>/victoria/webhook/inbound

    SICK DAY FLOW:
        When caller says they're sick, Retell will include a
        'sick_day_reported' custom data field in the transcript summary.
        Victoria logs the call, updates attendance_log, notifies kitchen
        and driver via Telegram.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = body.get("event", "")
    call_data = body.get("call", {})
    call_id = call_data.get("call_id", "unknown")
    from_number = call_data.get("from_number", "unknown")
    metadata = call_data.get("metadata", {})

    logger.info(f"Victoria inbound webhook: event={event} call_id={call_id}")

    if event == "call_started":
        _log_call(
            call_type="inbound_call_started",
            phone_number=from_number,
            retell_call_id=call_id,
            status="in_progress",
        )

    elif event == "call_ended":
        duration_ms = call_data.get("duration_ms", 0)
        duration_sec = duration_ms / 1000 if duration_ms else 0
        transcript = call_data.get("transcript", "") or call_data.get("transcript_object", [])
        if isinstance(transcript, list):
            transcript = "\n".join(
                f"[{t.get('role','?')}]: {t.get('content','')}" for t in transcript
            )
        recording_url = call_data.get("recording_url", "") or call_data.get("recording", "")
        custom_data = call_data.get("custom_data", {})

        _log_call(
            call_type="inbound_call_ended",
            phone_number=from_number,
            retell_call_id=call_id,
            status="completed",
            notes=f"duration_ms={duration_ms}",
            transcript=transcript,
            recording_url=recording_url,
            duration_seconds=duration_sec,
        )

        # ── Sick-day detection ────────────────────────────────────────────────
        # Retell can extract structured data from the call.
        # When sick_day_reported is present, Victoria logs and notifies.
        sick_day = custom_data.get("sick_day_reported") or _detect_sick_day(transcript)
        if sick_day:
            client_id = metadata.get("client_id") or custom_data.get("client_id")
            client_name = metadata.get("client_name") or custom_data.get("client_name", "Unknown client")

            if client_id:
                _update_attendance_sick(
                    client_id=int(client_id),
                    note=f"Sick — called in via Victoria inbound call_id={call_id}",
                )

            _send_telegram(
                f"🤒 <b>Victoria · Sick Day Callout</b>\n"
                f"Client: {client_name}"
                + (f" (id={client_id})" if client_id else "")
                + f"\nPhone: {from_number}\n"
                f"⚠️ Update kitchen list and driver route.\n"
                f"call_id: {call_id}"
            )
            logger.info(f"Sick day reported via Victoria: client={client_name} phone={from_number}")

        # ── Coming-confirmed detection (T2.1 Option C voice present-mark) ───
        # Direct DB write (not HTTP to /present-mark) because uvicorn is
        # single-worker and we'd deadlock calling our own endpoint synchronously.
        # Same upsert logic as the /goj-live/present-mark handler.
        coming = custom_data.get("coming_confirmed") or _detect_coming(transcript)
        if coming and not sick_day:
            cname = metadata.get("client_name") or custom_data.get("client_name")
            shift = int(metadata.get("shift") or custom_data.get("shift") or 1)
            if cname:
                try:
                    import sqlite3 as _sql
                    from datetime import date as _date
                    name = " ".join(w.capitalize() for w in cname.strip().split())
                    today = _date.today().isoformat()
                    note = f"source=voice · by=victoria:{call_id} · phone={from_number}"
                    with _sql.connect(str(AUTH_DB_PATH)) as conn:
                        existing = conn.execute(
                            "SELECT rowid FROM attendance_log "
                            "WHERE log_date=? AND shift=? AND LOWER(client_name)=LOWER(?)",
                            (today, shift, name),
                        ).fetchone()
                        if existing:
                            conn.execute(
                                "UPDATE attendance_log SET status='present', "
                                "reason = COALESCE(NULLIF(?, ''), reason) WHERE rowid=?",
                                (note, existing[0]),
                            )
                        else:
                            cols = {row[1] for row in conn.execute("PRAGMA table_info(attendance_log)")}
                            ic, iv = ["log_date","shift","client_name","status"], [today, shift, name, "present"]
                            if "reason" in cols: ic.append("reason"); iv.append(note)
                            if "source" in cols: ic.append("source"); iv.append("voice")
                            if "day_key" in cols:
                                from datetime import datetime as _dt
                                ic.append("day_key"); iv.append(_dt.now().strftime("%a")[:3].lower())
                            ph = ",".join("?" * len(ic))
                            conn.execute(
                                f"INSERT INTO attendance_log ({','.join(ic)}) VALUES ({ph})", iv,
                            )
                        conn.commit()
                    logger.info(f"Voice present-mark written: {name} shift={shift} call_id={call_id}")
                    _send_telegram(
                        f"✅ <b>Victoria · Coming Confirmed</b>\n"
                        f"Client: {cname}\nShift: {shift}\ncall_id: {call_id}"
                    )
                except Exception as e:
                    logger.warning(f"Voice present-mark DB write failed: {e}")

    elif event == "call_analyzed":
        analysis = call_data.get("call_analysis", {})
        summary = analysis.get("call_summary", "")
        sentiment = analysis.get("user_sentiment", "")
        transcript_full = call_data.get("transcript", "") or call_data.get("transcript_object", [])
        if isinstance(transcript_full, list):
            transcript_full = "\n".join(
                f"[{t.get('role','?')}]: {t.get('content','')}" for t in transcript_full
            )
        
        if summary or sentiment:
            _log_call(
                call_type="inbound_analyzed",
                phone_number=from_number,
                retell_call_id=call_id,
                status="analyzed",
                notes=summary[:500] if summary else None,
                call_summary=summary,
                sentiment=sentiment,
                transcript=transcript_full or None,
            )

    return {"received": True, "event": event, "call_id": call_id}


# ── Report Generation ──────────────────────────────────────────────────────────

@victoria_router.get("/report")
async def victoria_report(date: str = "") -> dict[str, Any]:
    """
    Generate a consolidated HTML report of all Victoria calls for a given date.
    Query: GET /victoria/report?date=2026-06-11
    
    Produces: ~/Desktop/REX/CC_victoria_report.html
    Returns:  JSON with path + summary stats
    """
    from datetime import date as _date, datetime as _dt
    
    if not date:
        date = _date.today().isoformat()
    
    _ensure_call_log_table()
    with _get_db_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM victoria_call_log 
               WHERE date(created_at) = ? 
               ORDER BY id ASC""",
            (date,)
        ).fetchall()
    
    calls = [dict(r) for r in rows]
    
    # Stats
    total = len(calls)
    completed = sum(1 for c in calls if c["status"] == "completed")
    initiated = sum(1 for c in calls if c["status"] == "initiated")
    failed = sum(1 for c in calls if c["status"] == "failed")
    confirmed = sum(1 for c in calls if c.get("transcript") and 
                    _detect_coming(c["transcript"] or ""))
    sick = sum(1 for c in calls if c.get("transcript") and 
               _detect_sick_day(c["transcript"] or ""))
    
    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Victoria Call Report — {date}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0f172a; color:#e2e8f0; padding:2rem; }}
  .header {{ text-align:center; margin-bottom:2rem; }}
  .header h1 {{ font-size:2rem; color:#38bdf8; }}
  .header p {{ color:#94a3b8; margin-top:.5rem; }}
  .stats {{ display:flex; gap:1rem; justify-content:center; flex-wrap:wrap; margin-bottom:2rem; }}
  .stat {{ background:#1e293b; border-radius:12px; padding:1.2rem 1.8rem; text-align:center; min-width:120px; }}
  .stat .num {{ font-size:2rem; font-weight:700; }}
  .stat .label {{ font-size:.8rem; color:#94a3b8; margin-top:.3rem; text-transform:uppercase; }}
  .stat.total .num {{ color:#38bdf8; }}
  .stat.ok .num {{ color:#22c55e; }}
  .stat.fail .num {{ color:#ef4444; }}
  .stat.confirm .num {{ color:#a78bfa; }}
  .stat.sick .num {{ color:#f59e0b; }}
  table {{ width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }}
  th {{ background:#334155; padding:.75rem 1rem; text-align:left; font-size:.8rem; text-transform:uppercase; color:#94a3b8; }}
  td {{ padding:.75rem 1rem; border-bottom:1px solid #334155; font-size:.9rem; }}
  tr:last-child td {{ border-bottom:none; }}
  .status-ok {{ color:#22c55e; font-weight:600; }}
  .status-fail {{ color:#ef4444; font-weight:600; }}
  .status-pending {{ color:#f59e0b; font-weight:600; }}
  .transcript {{ max-width:300px; white-space:pre-wrap; font-size:.8rem; color:#94a3b8; max-height:60px; overflow:hidden; }}
  .footer {{ text-align:center; margin-top:2rem; color:#64748b; font-size:.8rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>📞 Victoria Call Report</h1>
  <p>Garden of Joy Adult Day Care · {date}</p>
</div>
<div class="stats">
  <div class="stat total"><div class="num">{total}</div><div class="label">Total Calls</div></div>
  <div class="stat ok"><div class="num">{completed}</div><div class="label">Completed</div></div>
  <div class="stat fail"><div class="num">{failed}</div><div class="label">Failed</div></div>
  <div class="stat confirm"><div class="num">{confirmed}</div><div class="label">Confirmed ✓</div></div>
  <div class="stat sick"><div class="num">{sick}</div><div class="label">Sick Day 🤒</div></div>
</div>
<table>
<thead>
<tr><th>#</th><th>Client</th><th>Phone</th><th>Type</th><th>Status</th><th>Transcript / Notes</th></tr>
</thead>
<tbody>
"""
    for i, c in enumerate(calls, 1):
        status_class = "status-ok" if c["status"] == "completed" else ("status-fail" if c["status"] == "failed" else "status-pending")
        client_name = ""
        phone = c.get("phone_number", "")
        if c.get("client_id"):
            try:
                cl = _get_client_by_id(c["client_id"])
                if cl:
                    client_name = cl.get("name", "")
            except Exception:
                pass
        
        display = f"<strong>{client_name}</strong>" if client_name else f"ID:{c.get('client_id','?')}"
        notes = c.get("transcript") or c.get("notes") or c.get("call_summary") or "—"
        
        html += f"""<tr>
  <td>{i}</td>
  <td>{display}</td>
  <td>{phone}</td>
  <td>{c.get('call_type','')}</td>
  <td class="{status_class}">{c.get('status','')}</td>
  <td class="transcript">{notes[:300]}</td>
</tr>
"""
    
    html += f"""</tbody></table>
<div class="footer">Generated {_dt.now().strftime('%Y-%m-%d %H:%M')} · Victoria Voice Agent · Gold Health Systems</div>
</body></html>"""
    
    # Write report
    from pathlib import Path as _Path
    report_path = _Path.home() / "Desktop" / "REX" / "CC_victoria_report.html"
    report_path.write_text(html)
    
    return {
        "report_path": str(report_path),
        "date": date,
        "stats": {
            "total": total,
            "completed": completed,
            "initiated": initiated,
            "failed": failed,
            "confirmed_coming": confirmed,
            "sick_day": sick,
        },
        "calls": calls,
    }


def _detect_sick_day(transcript: str) -> bool:
    """
    Lightweight keyword heuristic to detect a sick-day report from transcript text.
    Retell custom data extraction is preferred; this is a fallback.
    """
    if not transcript:
        return False
    lower = transcript.lower()
    sick_phrases = [
        "not coming in", "staying home", "feeling sick", "not feeling well",
        "won't be in", "can't come", "sick today", "not attending",
    ]
    return any(phrase in lower for phrase in sick_phrases)


def _detect_coming(transcript: str) -> bool:
    """
    Heuristic to detect 'yes, coming' from a confirmation call transcript.
    Retell custom_data.coming_confirmed is preferred; this is a fallback.
    """
    if not transcript:
        return False
    lower = transcript.lower()
    coming_phrases = [
        "yes she's coming", "yes he's coming", "she will be there",
        "he will be there", "she's coming", "he's coming", "coming today",
        "coming in", "she'll be in", "he'll be in", "we'll be there",
        "yes attending", "will attend", "will be coming",
    ]
    return any(phrase in lower for phrase in coming_phrases)
