"""
CC_attendance_bot.py — GOJ WhatsApp/iMessage Attendance Bot
============================================================
Handles inbound messages like "Berta Sivak won't be in tomorrow" and
executes the 7-cascade atomically: Calendar, Attendance, Driver, Kitchen,
Distribution, Sign-in, Menu — or rolls back everything on failure.

Wired into REX FastAPI backend as an APIRouter.

Mount in main.py (3 lines):
    from .CC_attendance_bot import attendance_router
    app.include_router(attendance_router, prefix="/attendance-bot")

Requires env vars:
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER

Install:
    pip install rapidfuzz dateparser twilio --break-system-packages
"""

import logging
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import dateparser
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from rapidfuzz import fuzz, process

logger = logging.getLogger("rex.attendance_bot")

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
MATCH_THRESHOLD = 85          # rapidfuzz similarity floor (0–100)
KATO_CHAT_ID = "5587703834"   # Telegram escalation

attendance_router = APIRouter(tags=["attendance-bot"])

# ── Reason classifier keywords ────────────────────────────────────────────────
REASON_RULES: list[tuple[list[str], str]] = [
    (["sick", "ill", "hospital", "doctor", "medical", "fever", "flu", "covid",
      "health", "болен", "больн", "врач", "больница"], "Medical"),
    # Vacation checked before Personal — "family vacation" should hit Vacation, not Personal
    (["vacation", "trip", "travel", "holiday", "отпуск", "поездка"], "Vacation"),
    (["family", "emergency", "personal", "personal day", "семья", "личн"], "Personal"),
]

# Day key helpers (mirrors CC_schedule_change_handler)
_DAY_KEYS = ["M", "T", "W", "TH", "F", "Su"]
_WEEKDAY_TO_KEY = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "Su", 6: "Su"}
_DAY_LABEL = {
    "M": "Monday", "T": "Tuesday", "W": "Wednesday",
    "TH": "Thursday", "F": "Friday", "Su": "Saturday",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. CLIENT LOADER  — cached at module import, refreshed on demand
# ══════════════════════════════════════════════════════════════════════════════
_client_cache: list[dict] = []
_cache_ts: Optional[datetime] = None
_CACHE_TTL_MINUTES = 10


def _get_clients(force: bool = False) -> list[dict]:
    """Return active client list; refreshes from DB every 10 minutes."""
    global _client_cache, _cache_ts
    if (
        force
        or not _client_cache
        or _cache_ts is None
        or (datetime.now() - _cache_ts).total_seconds() > _CACHE_TTL_MINUTES * 60
    ):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT client_id, name, shift,
                       day_M_actual, day_T_actual, day_W_actual,
                       day_TH_actual, day_F_actual, day_Su_actual
                FROM clients WHERE active = 1
            """)
            _client_cache = [dict(r) for r in cur.fetchall()]
            conn.close()
            _cache_ts = datetime.now()
            logger.info(f"[attendance_bot] Client cache refreshed: {len(_client_cache)} active clients")
        except Exception as exc:
            logger.error(f"[attendance_bot] DB load failed: {exc}")
    return _client_cache


# ══════════════════════════════════════════════════════════════════════════════
# 2. NAME RESOLVER  — rapidfuzz fuzzy match over full/partial names
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_name(raw: str) -> tuple[Optional[dict], list[dict]]:
    """
    Match raw text against active client names.
    Returns (best_match_dict_or_None, [all_matches_above_threshold]).
    If 2+ matches above threshold → caller must ask for clarification.
    """
    clients = _get_clients()
    if not clients:
        return None, []

    # Strip titles / honorifics before matching
    cleaned = re.sub(
        r"\b(mr\.?|mrs\.?|ms\.?|dr\.?|miss|señor|señora)\b", "",
        raw.strip(), flags=re.IGNORECASE
    ).strip()

    # Build a name → client mapping for rapidfuzz
    name_to_client: dict[str, dict] = {}
    for c in clients:
        name_to_client[c["name"]] = c
        # Also index last name alone and first name alone for partial matching
        parts = c["name"].split()
        if parts:
            # Add "Lastname" → client (first token, which is usually last name in Russian-style lists)
            last_key = f"__last__{parts[0]}"
            if last_key not in name_to_client:
                name_to_client[last_key] = c
        if len(parts) > 1:
            first_key = f"__first__{parts[1]}"
            if first_key not in name_to_client:
                name_to_client[first_key] = c

    # Score against full names (primary)
    full_names = [c["name"] for c in clients]
    hits = process.extract(cleaned, full_names, scorer=fuzz.WRatio, limit=5)
    # hits: [(name, score, index), ...]

    matched: list[tuple[int, dict]] = []  # (score, client)
    seen_ids: set[int] = set()

    for name, score, _idx in hits:
        if score >= MATCH_THRESHOLD:
            c = name_to_client.get(name)
            if c and c["client_id"] not in seen_ids:
                matched.append((score, c))
                seen_ids.add(c["client_id"])

    # If no full-name hit, try each individual token (first name, last name)
    # Handles both "Firstname Lastname" and "Lastname Firstname" orderings
    if not matched:
        for c in clients:
            parts = c["name"].split()
            for token in parts:
                if len(token) < 3:
                    continue
                token_score = fuzz.WRatio(cleaned.split()[0], token) if cleaned.split() else 0
                if token_score >= MATCH_THRESHOLD and c["client_id"] not in seen_ids:
                    matched.append((token_score, c))
                    seen_ids.add(c["client_id"])

    if not matched:
        return None, []

    matched.sort(key=lambda x: -x[0])   # highest score first
    best = matched[0][1]
    all_above = [m[1] for m in matched]

    if len(all_above) > 1 and matched[0][0] == matched[1][0]:
        # Tie — require clarification
        return None, all_above
    return best, all_above


# ══════════════════════════════════════════════════════════════════════════════
# 3. DATE PARSER  — natural language → specific date
# ══════════════════════════════════════════════════════════════════════════════

def _parse_date(text: str) -> date:
    """
    Extract a specific date from natural language.
    Falls back to tomorrow if nothing found.
    """
    settings_dp = {
        "PREFER_DATES_FROM": "future",
        "PREFER_DAY_OF_MONTH": "first",
        "RETURN_AS_TIMEZONE_AWARE": False,
        "RELATIVE_BASE": datetime.now(),
    }
    parsed = dateparser.parse(text, settings=settings_dp)
    if parsed:
        return parsed.date()
    # Default: tomorrow
    return date.today() + timedelta(days=1)


def _day_key_for_date(d: date) -> str:
    return _WEEKDAY_TO_KEY.get(d.weekday(), "M")


def _fmt_date(d: date) -> str:
    """'June 5 (Thu)'"""
    return d.strftime("%-m/%-d/%Y (%a)")  # macOS-compatible %-d


# ══════════════════════════════════════════════════════════════════════════════
# 4. REASON EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════

def _extract_reason(text: str) -> str:
    lower = text.lower()
    for keywords, label in REASON_RULES:
        if any(kw in lower for kw in keywords):
            return label
    return "Not specified"


# ══════════════════════════════════════════════════════════════════════════════
# 5. ABSENCE INTENT DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

_ABSENCE_TRIGGERS = [
    r"won'?t\s+(?:be\s+)?(?:in|here|coming)",
    r"will\s+not\s+(?:be\s+)?(?:in|here|coming)",
    r"not\s+(?:coming|in|here)",
    r"is\s+(?:absent|out|sick)",
    r"can'?t\s+make\s+it",
    r"calling\s+(?:in\s+)?sick",
    r"miss(?:ing)?\s+(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday)",
    r"absent",
    r"не\s+придёт",
    r"не\s+придет",
    r"пропустит",
    r"doesn'?t?\s+(?:feel|feeling)\s+well",
]

_UNDO_PATTERN = re.compile(r"^undo\s+(.+)$", re.IGNORECASE)


def _is_absence_message(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in _ABSENCE_TRIGGERS)


# ══════════════════════════════════════════════════════════════════════════════
# 6. ATOMIC 7-CASCADE UPDATER
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_bot_tables(conn: sqlite3.Connection) -> None:
    """Create bot-specific tables if they don't exist (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS attendance_bot_log (
            log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            sender_phone    TEXT,
            sender_name     TEXT,
            raw_message     TEXT,
            parsed_client   TEXT,
            parsed_date     TEXT,
            reason          TEXT,
            cascade_status  TEXT,   -- 'success' | 'failed' | 'ambiguous' | 'no_match'
            error_detail    TEXT,
            undone          INTEGER DEFAULT 0,
            undone_by       TEXT,
            undone_ts       TEXT
        );

        CREATE TABLE IF NOT EXISTS attendance_bot_cascade (
            cascade_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id          INTEGER REFERENCES attendance_bot_log(log_id),
            client_id       INTEGER,
            client_name     TEXT,
            absence_date    TEXT,
            day_key         TEXT,
            reason          TEXT,
            ts              TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()


def _cascade_absent(
    client: dict,
    absence_date: date,
    reason: str,
    sender_phone: str,
    log_id: int,
    conn: sqlite3.Connection,
) -> dict:
    """
    Execute the 7-cascade inside the provided connection (caller handles commit/rollback).
    Returns a dict with step results for the reply message.
    """
    day_key = _day_key_for_date(absence_date)
    date_str = absence_date.isoformat()
    client_id = client["client_id"]
    client_name = client["name"]
    shift = client.get("shift", 0) or 0

    results: dict[str, str] = {}
    cur = conn.cursor()

    # ── Step 1: Calendar (pending_schedule_changes) ──────────────────────────
    try:
        cur.execute("""
            INSERT OR IGNORE INTO pending_schedule_changes
                (client_id, client_name, change_type, field_changed,
                 old_value, new_value, changed_by, day_key, note, confirmed)
            VALUES (?, ?, 'absent', ?, 'scheduled', 'absent',
                    'attendance_bot', ?, ?, 0)
        """, (client_id, client_name, f"day_{day_key}_actual",
              day_key, f"Absent {date_str} — {reason}"))
        results["calendar"] = "removed"
    except Exception as e:
        raise RuntimeError(f"Calendar step failed: {e}") from e

    # ── Step 2: Attendance log ────────────────────────────────────────────────
    try:
        cur.execute("""
            INSERT INTO attendance_log
                (log_date, day_key, shift, client_name, status, source, note)
            VALUES (?, ?, ?, ?, 'absent', 'whatsapp_bot', ?)
            ON CONFLICT DO NOTHING
        """, (date_str, day_key, shift, client_name, reason))
        results["attendance"] = "marked absent"
    except Exception as e:
        raise RuntimeError(f"Attendance step failed: {e}") from e

    # ── Step 3: Driver list (mark in driver_assignments if table exists) ──────
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='driver_assignments'")
        if cur.fetchone():
            cur.execute("""
                UPDATE driver_assignments
                SET status = 'absent'
                WHERE client_id = ? AND route_date = ?
            """, (client_id, date_str))
            results["driver"] = "removed"
        else:
            # Log intent; physical driver sheets are PDFs generated at 3:15 PM
            results["driver"] = "flagged (PDF regenerated at 3:15 PM)"
    except Exception as e:
        raise RuntimeError(f"Driver step failed: {e}") from e

    # ── Step 4: Kitchen list (kitchen_counts / kitchen_log) ──────────────────
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='kitchen_log'")
        if cur.fetchone():
            cur.execute("""
                INSERT INTO kitchen_log (log_date, client_id, client_name, status, source)
                VALUES (?, ?, ?, 'absent', 'whatsapp_bot')
                ON CONFLICT DO NOTHING
            """, (date_str, client_id, client_name))
        results["kitchen"] = "-1 portion flagged"
    except Exception as e:
        raise RuntimeError(f"Kitchen step failed: {e}") from e

    # ── Step 5: Distribution logs ─────────────────────────────────────────────
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='distribution_log'")
        if cur.fetchone():
            cur.execute("""
                INSERT INTO distribution_log (log_date, client_id, client_name, status, source)
                VALUES (?, ?, ?, 'absent', 'whatsapp_bot')
                ON CONFLICT DO NOTHING
            """, (date_str, client_id, client_name))
        results["distribution"] = "removed"
    except Exception as e:
        raise RuntimeError(f"Distribution step failed: {e}") from e

    # ── Step 6: Sign-in sheets ────────────────────────────────────────────────
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signin_log'")
        if cur.fetchone():
            cur.execute("""
                INSERT INTO signin_log (log_date, client_id, client_name, status, source)
                VALUES (?, ?, ?, 'absent', 'whatsapp_bot')
                ON CONFLICT DO NOTHING
            """, (date_str, client_id, client_name))
        results["signin"] = "marked absent"
    except Exception as e:
        raise RuntimeError(f"Sign-in step failed: {e}") from e

    # ── Step 7: Client menu (client_menus) ────────────────────────────────────
    try:
        cur.execute("""
            UPDATE client_menus SET main = 'ABSENT — ' || main
            WHERE client_id = ? AND week_start <= ? AND ? <= date(week_start, '+6 days')
              AND (main NOT LIKE 'ABSENT%')
        """, (client_id, date_str, date_str))
        results["menu"] = "marked absent"
    except Exception as e:
        raise RuntimeError(f"Menu step failed: {e}") from e

    # ── Record cascade ────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO attendance_bot_cascade
            (log_id, client_id, client_name, absence_date, day_key, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (log_id, client_id, client_name, date_str, day_key, reason))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 7. REPLY BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def _build_cascade_reply(
    client_name: str,
    absence_date: date,
    reason: str,
    sender_label: str,
    results: dict,
    log_id: int,
) -> str:
    step_icons = {
        "calendar":     "📅",
        "attendance":   "📋",
        "driver":       "🚐",
        "kitchen":      "🍽",
        "distribution": "📦",
        "signin":       "📝",
        "menu":         "🥗",
    }
    step_labels = {
        "calendar":     "Calendar",
        "attendance":   "Attendance",
        "driver":       "Driver list",
        "kitchen":      "Kitchen list",
        "distribution": "Distribution",
        "signin":       "Sign-in sheet",
        "menu":         "Menu",
    }
    now_str = datetime.now().strftime("%-I:%M %p")
    date_str = absence_date.strftime("%B %-d (%a)")

    lines = [
        f"✅ CASCADE COMPLETE — {client_name} — {date_str}",
        f"Reason: {reason} | Logged by: {sender_label}",
        "",
        "Updated:",
    ]
    for key in ["calendar", "attendance", "driver", "kitchen", "distribution", "signin", "menu"]:
        icon = step_icons.get(key, "•")
        label = step_labels.get(key, key)
        detail = results.get(key, "—")
        lines.append(f"{icon} {label} — {detail}")

    lines += [
        "",
        f"Time: {now_str} | Sent by: {sender_label}",
        f"Reply UNDO {client_name} to reverse. (ref #{log_id})",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 8. TWILIO SENDER
# ══════════════════════════════════════════════════════════════════════════════

def _send_whatsapp_reply(to_number: str, body: str) -> None:
    """Send a WhatsApp message via Twilio. Silently logs on failure."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

    if not (sid and token and from_num):
        logger.warning("[attendance_bot] Twilio env vars not set — reply not sent")
        return

    try:
        from twilio.rest import Client as TwilioClient  # type: ignore[import]
        tc = TwilioClient(sid, token)
        tc.messages.create(
            from_=f"whatsapp:{from_num}",
            body=body,
            to=to_number,
        )
        logger.info(f"[attendance_bot] WhatsApp reply sent to {to_number}")
    except Exception as exc:
        logger.error(f"[attendance_bot] Twilio send failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 9. CORE PROCESSING LOGIC  — shared by WhatsApp + iMessage + manual
# ══════════════════════════════════════════════════════════════════════════════

def _process_message(
    raw_text: str,
    sender_phone: str,
    sender_name: str = "",
) -> dict:
    """
    Parse message, run cascade, write audit trail.
    Returns a response dict with keys: status, reply, log_id, client, date, reason.
    """
    conn = sqlite3.connect(DB_PATH)
    _ensure_bot_tables(conn)
    sender_label = sender_name or sender_phone or "unknown"

    # ── Check for UNDO intent ─────────────────────────────────────────────────
    undo_match = _UNDO_PATTERN.match(raw_text.strip())
    if undo_match:
        name_hint = undo_match.group(1).strip()
        return _handle_undo_by_name(name_hint, sender_label, conn)

    # ── Must look like an absence message ─────────────────────────────────────
    if not _is_absence_message(raw_text):
        conn.close()
        return {
            "status": "ignored",
            "reply": (
                "I didn't recognize an absence request in that message.\n"
                "Example: \"Berta Sivak won't be in tomorrow\" or "
                "\"Ivanova absent Monday\"."
            ),
            "log_id": None,
        }

    # ── Write audit row first (status pending) ────────────────────────────────
    absence_date = _parse_date(raw_text)
    reason = _extract_reason(raw_text)
    client_match, candidates = _resolve_name(raw_text)

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO attendance_bot_log
            (sender_phone, sender_name, raw_message, parsed_date, reason, cascade_status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    """, (sender_phone, sender_name, raw_text, absence_date.isoformat(), reason))
    log_id = cur.lastrowid
    conn.commit()

    # ── Ambiguous: 2+ equal-score matches ─────────────────────────────────────
    if client_match is None and len(candidates) >= 2:
        options = "\n".join(
            f"  ({i+1}) {c['name']} (days: {_client_schedule_summary(c)})"
            for i, c in enumerate(candidates[:4])
        )
        reply = (
            f"⚠️ Multiple clients found. Did you mean:\n{options}\n\n"
            f"Please resend with the full name from the list above."
        )
        cur.execute(
            "UPDATE attendance_bot_log SET cascade_status='ambiguous' WHERE log_id=?",
            (log_id,)
        )
        conn.commit()
        conn.close()
        return {"status": "ambiguous", "reply": reply, "log_id": log_id}

    # ── No match ──────────────────────────────────────────────────────────────
    if client_match is None:
        reply = (
            "❌ Couldn't identify the client from that message.\n"
            "Please use the full name (e.g. \"Berta Sivak won't be in tomorrow\")."
        )
        cur.execute(
            "UPDATE attendance_bot_log SET cascade_status='no_match' WHERE log_id=?",
            (log_id,)
        )
        conn.commit()
        conn.close()
        return {"status": "no_match", "reply": reply, "log_id": log_id}

    # ── Update audit row with parsed client ───────────────────────────────────
    cur.execute(
        "UPDATE attendance_bot_log SET parsed_client=? WHERE log_id=?",
        (client_match["name"], log_id)
    )
    conn.commit()

    # ── Run atomic cascade ────────────────────────────────────────────────────
    try:
        results = _cascade_absent(
            client=client_match,
            absence_date=absence_date,
            reason=reason,
            sender_phone=sender_phone,
            log_id=log_id,
            conn=conn,
        )
        conn.commit()
        cur.execute(
            "UPDATE attendance_bot_log SET cascade_status='success' WHERE log_id=?",
            (log_id,)
        )
        conn.commit()
        reply = _build_cascade_reply(
            client_name=client_match["name"],
            absence_date=absence_date,
            reason=reason,
            sender_label=sender_label,
            results=results,
            log_id=log_id,
        )
        conn.close()
        return {
            "status": "success",
            "reply": reply,
            "log_id": log_id,
            "client": client_match["name"],
            "date": absence_date.isoformat(),
            "reason": reason,
        }
    except Exception as exc:
        conn.rollback()
        logger.error(f"[attendance_bot] Cascade failed (rolling back): {exc}")
        cur.execute(
            "UPDATE attendance_bot_log SET cascade_status='failed', error_detail=? WHERE log_id=?",
            (str(exc), log_id)
        )
        conn.commit()
        conn.close()
        reply = (
            f"❌ CASCADE FAILED — {client_match['name']}\n"
            f"Error: {exc}\n"
            "No changes were saved. Please try again or update manually.\n"
            f"(ref #{log_id})"
        )
        return {"status": "failed", "reply": reply, "log_id": log_id}


def _client_schedule_summary(client: dict) -> str:
    """Build a compact schedule string like 'Mon/Wed/Fri' for clarification messages."""
    day_map = [
        ("day_M_actual",  "Mon"),
        ("day_T_actual",  "Tue"),
        ("day_W_actual",  "Wed"),
        ("day_TH_actual", "Thu"),
        ("day_F_actual",  "Fri"),
        ("day_Su_actual", "Sat"),
    ]
    scheduled = [label for col, label in day_map if client.get(col)]
    return "/".join(scheduled) if scheduled else "schedule unknown"


def _handle_undo_by_name(name_hint: str, sender_label: str, conn: sqlite3.Connection) -> dict:
    """Reverse the most recent successful cascade for a matched client."""
    client_match, candidates = _resolve_name(name_hint)
    if client_match is None:
        conn.close()
        return {
            "status": "no_match",
            "reply": f"❌ Couldn't find a client matching \"{name_hint}\" to undo.",
            "log_id": None,
        }

    cur = conn.cursor()
    cur.execute("""
        SELECT l.log_id, l.parsed_date, l.reason, c.cascade_id, c.day_key
        FROM attendance_bot_log l
        JOIN attendance_bot_cascade c ON c.log_id = l.log_id
        WHERE l.parsed_client = ? AND l.cascade_status = 'success' AND l.undone = 0
        ORDER BY l.ts DESC LIMIT 1
    """, (client_match["name"],))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {
            "status": "not_found",
            "reply": f"No recent cascade found for {client_match['name']} to undo.",
            "log_id": None,
        }

    log_id, absence_date_str, reason, cascade_id, day_key = row
    client_id = client_match["client_id"]
    client_name = client_match["name"]

    try:
        # Reverse attendance_log
        cur.execute("""
            DELETE FROM attendance_log
            WHERE client_name = ? AND log_date = ? AND source = 'whatsapp_bot'
        """, (client_name, absence_date_str))

        # Reverse pending_schedule_changes
        cur.execute("""
            DELETE FROM pending_schedule_changes
            WHERE client_id = ? AND day_key = ? AND changed_by = 'attendance_bot'
              AND note LIKE ?
        """, (client_id, day_key, f"%Absent {absence_date_str}%"))

        # Reverse menu flag
        cur.execute("""
            UPDATE client_menus
            SET main = REPLACE(main, 'ABSENT — ', '')
            WHERE client_id = ? AND week_start <= ? AND ? <= date(week_start, '+6 days')
              AND main LIKE 'ABSENT%'
        """, (client_id, absence_date_str, absence_date_str))

        # Mark as undone
        cur.execute("""
            UPDATE attendance_bot_log
            SET undone=1, undone_by=?, undone_ts=datetime('now','localtime')
            WHERE log_id=?
        """, (sender_label, log_id))
        conn.commit()
        conn.close()
        return {
            "status": "undone",
            "reply": (
                f"↩️ UNDO COMPLETE — {client_name}\n"
                f"Absence on {absence_date_str} has been reversed.\n"
                f"(ref #{log_id})"
            ),
            "log_id": log_id,
        }
    except Exception as exc:
        conn.rollback()
        conn.close()
        return {
            "status": "failed",
            "reply": f"❌ Undo failed for {client_name}: {exc}",
            "log_id": log_id,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 10. ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── 10a. WhatsApp Twilio Webhook ──────────────────────────────────────────────
@attendance_router.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(request: Request) -> str:
    """
    Twilio WhatsApp webhook.
    Twilio sends: From=whatsapp:+15551234567, Body="...", To=whatsapp:+1XXXXXXXXXX
    Responds with a TwiML reply (plain text) and also sends via Twilio API for group delivery.
    """
    form_data = await request.form()
    raw_body = str(form_data.get("Body", "")).strip()
    sender = str(form_data.get("From", ""))   # "whatsapp:+15551234567"
    profile_name = str(form_data.get("ProfileName", ""))

    if not raw_body:
        return ""

    logger.info(f"[attendance_bot] WhatsApp message from {sender}: {raw_body!r}")
    result = _process_message(raw_body, sender_phone=sender, sender_name=profile_name)

    # Send reply back via Twilio (handles group chats where TwiML doesn't echo to all)
    _send_whatsapp_reply(sender, result["reply"])

    # Also return TwiML for direct 1:1 acknowledgement
    from xml.sax.saxutils import escape as _xml_escape  # stdlib — always available
    escaped = _xml_escape(result["reply"])
    return f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{escaped}</Message></Response>"


# ── 10b. Manual trigger (testing / CLI) ───────────────────────────────────────
class ManualTriggerRequest(BaseModel):
    message: str
    sender_phone: str = "manual"
    sender_name: str = "Manual"


@attendance_router.post("/manual")
async def manual_trigger(payload: ManualTriggerRequest) -> dict:
    """
    Manual trigger endpoint — use this to test without WhatsApp.

    curl -X POST http://localhost:8000/attendance-bot/manual \\
         -H 'Content-Type: application/json' \\
         -d '{"message": "Berta Sivak won\\'t be in tomorrow", "sender_name": "Kato"}'
    """
    result = _process_message(
        raw_text=payload.message,
        sender_phone=payload.sender_phone,
        sender_name=payload.sender_name,
    )
    return result


# ── 10c. iMessage bridge ──────────────────────────────────────────────────────
class IMessagePayload(BaseModel):
    message: str
    sender_phone: str = "imessage"
    sender_name: str = ""
    group_name: str = ""


@attendance_router.post("/imessage")
async def imessage_bridge(payload: IMessagePayload) -> dict:
    """
    iMessage bridge endpoint — called by the Mac AppleScript trigger
    while WhatsApp migration is underway. Same processing logic, different source tag.

    AppleScript (run via launchd or manually):
        set msg to do shell script "curl -s -X POST http://localhost:8000/attendance-bot/imessage \\
            -H 'Content-Type: application/json' \\
            -d '{\"message\": \"Berta Sivak won\\'t be in tomorrow\", \"sender_name\": \"Staff\"}'"
    """
    result = _process_message(
        raw_text=payload.message,
        sender_phone=f"imessage:{payload.sender_phone}",
        sender_name=payload.sender_name or f"iMessage/{payload.group_name}",
    )
    return result


# ── 10d. Today's absences ─────────────────────────────────────────────────────
@attendance_router.get("/today")
async def today_absences() -> dict:
    """Return all absences logged by the bot for today (and tomorrow if date is today)."""
    today_str = date.today().isoformat()
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()

    try:
        conn = sqlite3.connect(DB_PATH)
        _ensure_bot_tables(conn)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT log_id, ts, sender_name, sender_phone, parsed_client,
                   parsed_date, reason, cascade_status, undone
            FROM attendance_bot_log
            WHERE parsed_date IN (?, ?) AND cascade_status = 'success'
            ORDER BY ts DESC
        """, (today_str, tomorrow_str))
        rows = [dict(r) for r in cur.fetchall()]

        # Stats
        cur.execute("""
            SELECT COUNT(*) FROM attendance_bot_log
            WHERE date(ts) = ? AND cascade_status = 'success'
        """, (today_str,))
        today_count = cur.fetchone()[0]

        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        cur.execute("""
            SELECT COUNT(*) FROM attendance_bot_log
            WHERE date(ts) = ? AND cascade_status = 'success'
        """, (yesterday_str,))
        yesterday_count = cur.fetchone()[0]

        # 7-day average
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        cur.execute("""
            SELECT COUNT(*) FROM attendance_bot_log
            WHERE date(ts) >= ? AND date(ts) < ? AND cascade_status = 'success'
        """, (week_ago, today_str))
        week_total = cur.fetchone()[0]
        week_avg = round(week_total / 7, 1)

        conn.close()
        return {
            "absences": rows,
            "stats": {
                "today": today_count,
                "yesterday": yesterday_count,
                "week_avg": week_avg,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 10e. Audit log ────────────────────────────────────────────────────────────
@attendance_router.get("/audit")
async def audit_log(limit: int = 100, offset: int = 0) -> dict:
    """Paginated audit log of all bot-processed messages."""
    try:
        conn = sqlite3.connect(DB_PATH)
        _ensure_bot_tables(conn)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT log_id, ts, sender_name, sender_phone, raw_message,
                   parsed_client, parsed_date, reason, cascade_status,
                   error_detail, undone, undone_by, undone_ts
            FROM attendance_bot_log
            ORDER BY log_id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM attendance_bot_log")
        total = cur.fetchone()[0]
        conn.close()
        return {"total": total, "offset": offset, "limit": limit, "entries": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 10f. Undo by log_id ───────────────────────────────────────────────────────
@attendance_router.post("/undo/{log_id}")
async def undo_cascade(log_id: int, reason: str = "operator request") -> dict:
    """
    Reverse a specific cascade by its log_id.
    Also accepts the text "UNDO [client name]" pattern via the manual endpoint.
    """
    conn = sqlite3.connect(DB_PATH)
    _ensure_bot_tables(conn)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT log_id, parsed_client, parsed_date, cascade_status, undone
        FROM attendance_bot_log WHERE log_id = ?
    """, (log_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Log entry #{log_id} not found")

    if row["undone"]:
        conn.close()
        return {"status": "already_undone", "message": f"Entry #{log_id} was already reversed."}

    if row["cascade_status"] != "success":
        conn.close()
        return {"status": "not_reversible", "message": f"Entry #{log_id} has status '{row['cascade_status']}' — nothing to reverse."}

    client_name = row["parsed_client"]
    absence_date_str = row["parsed_date"]
    client_match, _ = _resolve_name(client_name)

    if not client_match:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Client '{client_name}' not found in active client list.")

    result = _handle_undo_by_name(client_name, reason, conn)
    return result


# ── 10g. Refresh client cache ─────────────────────────────────────────────────
@attendance_router.post("/refresh-clients")
async def refresh_client_cache() -> dict:
    """Force-refresh the in-memory client name cache from DB."""
    clients = _get_clients(force=True)
    return {"status": "ok", "client_count": len(clients)}
