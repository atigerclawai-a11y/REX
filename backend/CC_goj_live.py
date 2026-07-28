"""
CC_goj_live.py — GOJ Live: Real-time Operations Dashboard
v1.0 · June 2026

FastAPI router + SSE endpoint. Mounts to REX at /goj-live.
Streams: attendance counts, schedule changes, menu updates, client statuses.
Frontend at CC_goj_live.html.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goj-live", tags=["GOJ Live"])

# ── Config ─────────────────────────────────────────────────────────────────────
AUTH_DB = Path(os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db"))
STATE_PATH = Path(os.path.expanduser("~/Desktop/REX/state/goj_live_state.json"))
PROPOSALS_PATH = Path(os.path.expanduser("~/Desktop/REX/state/goj_live_proposals.json"))

# ── Models ─────────────────────────────────────────────────────────────────────

class Proposal(BaseModel):
    action: str          # "update_attendance", "schedule_change", "menu_update"
    client_id: Optional[str] = None
    description: str
    data: dict = {}

class RevertRequest(BaseModel):
    proposal_id: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_db():
    """Connect to auth_tracker.db (read-only)."""
    if not AUTH_DB.exists():
        return None
    conn = sqlite3.connect(str(AUTH_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _snapshot() -> dict:
    """Take a live snapshot of GOJ operations."""
    snap = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "attendance": {"active": 0, "scheduled_today": 0, "expiring": 0, "date": None, "is_today": False},
        "menus": {"total": 0, "this_week": 0},
        "schedules": {"changes_today": 0},
        "clients": {"total": 0, "active": 0, "expired": 0, "pending_renewal": 0, "no_auth": 0},
    }

    conn = _get_db()
    if not conn:
        snap["error"] = "Database not accessible"
        return snap

    try:
        c = conn.cursor()

        # Client counts — bucket each client by status from their latest authorization.
        # Sums to total clients; "NO AUTH" catches clients with zero auth rows.
        c.execute("SELECT COUNT(*) FROM clients")
        snap["clients"]["total"] = c.fetchone()[0]

        c.execute("""
            SELECT COALESCE(latest_status, 'NO AUTH') AS bucket, COUNT(*) AS n
            FROM (
                SELECT c.name,
                       (SELECT a.status FROM authorization a
                        WHERE a.client_name = c.name
                        ORDER BY a.service_end_date DESC, a.auth_id DESC
                        LIMIT 1) AS latest_status
                FROM clients c
            )
            GROUP BY COALESCE(latest_status, 'NO AUTH')
        """)
        buckets = dict(c.fetchall())
        snap["clients"]["active"] = buckets.get("ACTIVE", 0)
        snap["clients"]["expired"] = buckets.get("EXPIRED", 0)
        snap["clients"]["pending_renewal"] = buckets.get("PENDING RENEWAL", 0)
        snap["clients"]["no_auth"] = buckets.get("NO AUTH", 0)

        # Attendance — today, falling back to most recent day with data
        today_total = c.execute(
            "SELECT COUNT(*) FROM attendance_log WHERE log_date = date('now')"
        ).fetchone()[0]
        if today_total > 0:
            target_date = datetime.now().strftime("%Y-%m-%d")
            snap["attendance"]["is_today"] = True
        else:
            target_date = c.execute(
                "SELECT MAX(log_date) FROM attendance_log"
            ).fetchone()[0]
            snap["attendance"]["is_today"] = False
        snap["attendance"]["date"] = target_date
        if target_date:
            snap["attendance"]["scheduled_today"] = c.execute(
                "SELECT COUNT(*) FROM attendance_log WHERE log_date = ?", (target_date,)
            ).fetchone()[0]
            snap["attendance"]["active"] = c.execute(
                "SELECT COUNT(*) FROM attendance_log WHERE log_date = ? AND status = 'present'",
                (target_date,)
            ).fetchone()[0]

        # Menus
        c.execute("SELECT COUNT(*) FROM menus")
        snap["menus"]["total"] = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM menus WHERE menu_date = date('now')")
        snap["menus"]["this_week"] = c.fetchone()[0]

        conn.close()
    except Exception as e:
        snap["error"] = str(e)
        try:
            conn.close()
        except Exception:
            pass

    return snap


def _load_proposals() -> dict:
    """Load pending proposals."""
    if PROPOSALS_PATH.exists():
        try:
            return json.loads(PROPOSALS_PATH.read_text())
        except Exception:
            pass
    return {"proposals": {}}


def _save_proposals(store: dict) -> None:
    PROPOSALS_PATH.write_text(json.dumps(store, indent=2))


# ── Live change-feed (additive table; powers SSE row-level deltas) ──────────────

def _ensure_change_log() -> None:
    """Create the additive live_change_log table if absent. Does NOT touch any
    existing table. Safe to call repeatedly (CREATE TABLE IF NOT EXISTS)."""
    if not AUTH_DB.exists():
        return
    try:
        with sqlite3.connect(str(AUTH_DB)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS live_change_log("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts TEXT, table_name TEXT, op TEXT, row_summary TEXT, payload TEXT)"
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"live_change_log ensure failed: {e}")


def log_change(conn, table_name: str, op: str, row_summary: str, payload=None) -> None:
    """Append one display-safe row to live_change_log for the SSE delta channel.

    row_summary/payload MUST be display-safe — first name + last initial only,
    no SSN/DOB. This text is streamed to the browser.

    `conn` is an open sqlite3 connection used by the calling writer; the append
    rides on the caller's transaction so it commits atomically with the write."""
    try:
        payload_txt = None
        if payload is not None:
            payload_txt = payload if isinstance(payload, str) else json.dumps(payload)
        conn.execute(
            "INSERT INTO live_change_log(ts, table_name, op, row_summary, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), table_name, op, row_summary, payload_txt),
        )
    except Exception as e:
        # Never let the change-feed break a real write.
        logger.warning(f"log_change failed ({table_name}/{op}): {e}")


def _display_safe_name(name: str) -> str:
    """Reduce a full name to 'First L.' for the delta feed (no full surname)."""
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "client"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


# Ensure the change-log table exists at import time (startup).
_ensure_change_log()


# ── SSE Stream ─────────────────────────────────────────────────────────────────

def _new_change_rows(after_id: int) -> "tuple[list[dict], int]":
    """Return (rows, max_id) from live_change_log with id > after_id.
    Display-safe rows only (the table is written that way by log_change)."""
    if not AUTH_DB.exists():
        return [], after_id
    rows: list[dict] = []
    max_id = after_id
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, ts, table_name, op, row_summary, payload "
            "FROM live_change_log WHERE id > ? ORDER BY id ASC LIMIT 100",
            (after_id,),
        )
        for r in cur.fetchall():
            rows.append({
                "id": r["id"], "ts": r["ts"], "table": r["table_name"],
                "op": r["op"], "summary": r["row_summary"], "payload": r["payload"],
            })
            if r["id"] > max_id:
                max_id = r["id"]
        conn.close()
    except Exception as e:
        logger.warning(f"_new_change_rows failed: {e}")
    return rows, max_id


@router.get("/stream")
async def goj_stream(request: Request):
    """Server-Sent Events stream. Emits two named channels off one connection:
      • event: snapshot — full KPI snapshot every ~15s (existing behavior).
      • event: delta    — new live_change_log rows, polled every ~3s.
    A bare `data:` (default 'message') snapshot is also emitted alongside the
    first snapshot for backward-compat with any onmessage-only client."""
    async def event_generator():
        # Start the delta cursor at the current max id so we only stream
        # changes that happen AFTER this client connects.
        _, last_id = _new_change_rows(0)
        last_snapshot = 0.0
        SNAPSHOT_EVERY = 15.0
        POLL_EVERY = 3.0
        first = True
        while True:
            if await request.is_disconnected():
                break
            now = time.monotonic()
            # Snapshot channel (~15s, plus an immediate one on connect)
            if first or (now - last_snapshot) >= SNAPSHOT_EVERY:
                try:
                    snap = _snapshot()
                    proposals = _load_proposals()
                    snap["pending_proposals"] = len(proposals.get("proposals", {}))
                    payload = json.dumps(snap)
                    yield f"event: snapshot\ndata: {payload}\n\n"
                    # Back-compat: also emit as default 'message' so an
                    # onmessage-only client keeps rendering KPI tiles.
                    yield f"data: {payload}\n\n"
                except Exception as e:
                    yield f"event: snapshot\ndata: {{\"error\": \"{str(e)}\"}}\n\n"
                last_snapshot = now
                first = False
            # Delta channel (~3s)
            try:
                rows, last_id = _new_change_rows(last_id)
                if rows:
                    yield f"event: delta\ndata: {json.dumps(rows)}\n\n"
            except Exception as e:
                logger.warning(f"delta emit failed: {e}")
            await asyncio.sleep(POLL_EVERY)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Snapshot API ───────────────────────────────────────────────────────────────

@router.get("/snapshot")
async def get_snapshot():
    """Get current GOJ snapshot (polling fallback)."""
    snap = _snapshot()
    proposals = _load_proposals()
    snap["pending_proposals"] = len(proposals.get("proposals", {}))
    # Include live Drive data if available
    try:
        snap["drive"] = _drive_live_snapshot()
    except Exception:
        snap["drive"] = None
    return snap


# ── Drive Data API ─────────────────────────────────────────────────────────────

def _normalize_plan(plan_raw: str) -> str:
    """Normalize insurance plan names from Drive sign-in sheets.
    Maps CPHL variants → Anthem (Centers Plan for Healthy Living rebranded)."""
    p = (plan_raw or "").strip()
    if not p:
        return "Unknown"
    upper = p.upper()
    if "CPHL" in upper or "CENTERS PLAN" in upper or "HEALTHY LIVING" in upper:
        return "Anthem"
    if "ANTHEM" in upper:
        return "Anthem"
    if "ELD" in upper or "ELDER" in upper:
        return "Eld Serve"
    if "VCM" in upper:
        return "VCM"
    if "SWH" in upper:
        return "SWH"
    if "VNS" in upper:
        return "VNS"
    if "AETNA" in upper:
        return "Aetna"
    if "METRO" in upper:
        return "Metro Plus"
    if "PRIVATE" in upper or "PAY" in upper:
        return "Private Pay"
    if "EMPIRE" in upper:
        return "Empire"
    return p  # Keep as-is if no match


def _drive_live_snapshot(target_date=None) -> dict:
    """Read live Drive sign-in sheet and return snapshot counts."""
    from pathlib import Path as _P
    import sys as _sys
    from collections import Counter

    REX_DIR = _P.home() / "Desktop" / "REX"
    if str(REX_DIR) not in _sys.path:
        _sys.path.insert(0, str(REX_DIR))
    from CC_drive_lists import read_sign_in_sheet, get_day_info

    if target_date is None:
        from datetime import date as _date
        target_date = _date.today()
    elif isinstance(target_date, str):
        from datetime import date as _date
        target_date = _date.fromisoformat(target_date)

    day_code, day_name = get_day_info(target_date)

    s1 = read_sign_in_sheet(day_code, 1)
    s2 = read_sign_in_sheet(day_code, 2)

    # Transport counts
    s1_tr = sum(1 for c in s1 if c.get("transport", "") == "TR")
    s1_ntr = sum(1 for c in s1 if c.get("transport", "") == "N/TR")
    s2_tr = sum(1 for c in s2 if c.get("transport", "") == "TR")
    s2_ntr = sum(1 for c in s2 if c.get("transport", "") == "N/TR")

    # Insurance breakdown
    plans = Counter()
    for c in s1 + s2:
        plan = _normalize_plan(c.get("plan", ""))
        plans[plan] += 1

    return {
        "s1_count": len(s1),
        "s2_count": len(s2),
        "total": len(s1) + len(s2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "day": day_name,
        "date": target_date.isoformat(),
        "insurance_breakdown": dict(plans),
        "transport": {
            "s1_tr": s1_tr,
            "s1_ntr": s1_ntr,
            "s2_tr": s2_tr,
            "s2_ntr": s2_ntr,
        },
    }


@router.get("/drive-snapshot")
async def get_drive_snapshot():
    """Get live attendance counts directly from Google Drive sign-in sheet."""
    try:
        return _drive_live_snapshot()
    except Exception as e:
        raise HTTPException(503, f"Drive snapshot failed: {e}")


@router.get("/drive-attendance")
async def get_drive_attendance(date: str = None):
    """Get full client lists from Drive sign-in sheet for a given date.

    Query params:
        date: YYYY-MM-DD (defaults to today)
    Returns:
        {date, day, code, s1: [{name, plan, transport}], s2: [...], total}
    """
    try:
        from pathlib import Path as _P
        import sys as _sys

        REX_DIR = _P.home() / "Desktop" / "REX"
        if str(REX_DIR) not in _sys.path:
            _sys.path.insert(0, str(REX_DIR))
        from CC_drive_lists import read_sign_in_sheet, get_day_info

        if date is None:
            from datetime import date as _date
            target_date = _date.today()
        else:
            from datetime import date as _date
            target_date = _date.fromisoformat(date)

        day_code, day_name = get_day_info(target_date)

        s1 = read_sign_in_sheet(day_code, 1)
        s2 = read_sign_in_sheet(day_code, 2)

        s1_clean = [
            {
                "name": c["name"],
                "plan": _normalize_plan(c.get("plan", "")),
                "transport": c.get("transport", ""),
            }
            for c in s1
        ]
        s2_clean = [
            {
                "name": c["name"],
                "plan": _normalize_plan(c.get("plan", "")),
                "transport": c.get("transport", ""),
            }
            for c in s2
        ]

        return {
            "date": target_date.isoformat(),
            "day": day_name,
            "code": day_code,
            "s1": s1_clean,
            "s2": s2_clean,
            "total": len(s1_clean) + len(s2_clean),
        }
    except Exception as e:
        raise HTTPException(503, f"Drive attendance failed: {e}")


# ── Build Monitor ─────────────────────────────────────────────────────────────

@router.get("/build-status")
async def get_build_status():
    """Live build/ingestion monitor — reports daemon state, code activity,
    service health, and DB freshness. Backed by CC_build_monitor.py."""
    import importlib.util
    monitor_path = Path(os.path.expanduser("~/Desktop/REX/CC_build_monitor.py"))
    if not monitor_path.exists():
        raise HTTPException(404, "CC_build_monitor.py not found")
    spec = importlib.util.spec_from_file_location("build_monitor", monitor_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.snapshot()


# ── Present-mark API (T2.1 — all four sources converge here) ─────────────────

class PresentMark(BaseModel):
    client_name: str
    log_date:    Optional[str] = None        # defaults to today
    shift:       int = 1                      # 1 or 2
    source:      str = "ui"                   # ui | telegram | voice | mobile_ocr
    marker_id:   Optional[str] = None         # who marked it (audit trail)
    confidence:  Optional[float] = None       # for mobile_ocr / voice
    reason:      Optional[str] = None         # optional context


@router.post("/present-mark")
async def present_mark(mark: PresentMark):
    """Mark a client present. Accepts entries from all four channels:
    UI button (D), Telegram bot (B), voice agent (C), mobile sign-in OCR (A).
    Writes to attendance_log with status='present'. Idempotent on
    (log_date, shift, client_name) — upserts to 'present' even if the row
    already has 'absent' (Drive ingest)."""
    from datetime import date as _date
    log_date = mark.log_date or _date.today().isoformat()
    if mark.shift not in (1, 2):
        raise HTTPException(400, "shift must be 1 or 2")
    if not mark.client_name.strip():
        raise HTTPException(400, "client_name required")

    note_parts = [f"source={mark.source}"]
    if mark.marker_id:  note_parts.append(f"by={mark.marker_id}")
    if mark.confidence is not None: note_parts.append(f"conf={mark.confidence:.0%}")
    if mark.reason:     note_parts.append(f"note={mark.reason}")
    note = " · ".join(note_parts)

    name = " ".join(w.capitalize() for w in mark.client_name.strip().split())

    if not AUTH_DB.exists():
        raise HTTPException(503, "auth_tracker.db not accessible")
    with sqlite3.connect(str(AUTH_DB)) as conn:
        # Try matching existing row by (log_date, shift, client_name) case-insensitive
        existing = conn.execute(
            "SELECT rowid, status FROM attendance_log "
            "WHERE log_date = ? AND shift = ? AND LOWER(client_name) = LOWER(?)",
            (log_date, mark.shift, name),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE attendance_log SET status = 'present', "
                "reason = COALESCE(NULLIF(?, ''), reason) WHERE rowid = ?",
                (note, existing[0]),
            )
            action = "updated"
        else:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(attendance_log)")}
            insert_cols = ["log_date", "shift", "client_name", "status"]
            insert_vals = [log_date, mark.shift, name, "present"]
            if "reason" in cols:
                insert_cols.append("reason"); insert_vals.append(note)
            if "source" in cols:
                insert_cols.append("source"); insert_vals.append(mark.source)
            if "day_key" in cols:
                day_key = datetime.fromisoformat(log_date).strftime("%a")[:3].lower()
                insert_cols.append("day_key"); insert_vals.append(day_key)
            placeholders = ",".join("?" * len(insert_cols))
            conn.execute(
                f"INSERT INTO attendance_log ({','.join(insert_cols)}) VALUES ({placeholders})",
                insert_vals,
            )
            action = "inserted"
        # Append a display-safe delta describing this present-mark write.
        # Rides on this connection's transaction → commits atomically below.
        summary = (
            f"{_display_safe_name(name)} — present · "
            f"{log_date} · shift {mark.shift} · {mark.source}"
        )
        log_change(
            conn, "attendance_log", action, summary,
            payload={"log_date": log_date, "shift": mark.shift, "source": mark.source},
        )
        conn.commit()
    return {"ok": True, "action": action, "client_name": name,
            "log_date": log_date, "shift": mark.shift, "source": mark.source}


# ── Mobile sign-in OCR → present-mark (T2.1 Option A) ────────────────────────

def _resolve_client_name(typed: str) -> "tuple[Optional[str], list[str]]":
    """Match a typed/OCR'd name against the clients table. Returns
    (canonical_name, suggestions). Used by mobile OCR + the Telegram bot."""
    raw = " ".join((typed or "").strip().split())
    if not raw or len(raw) < 3:
        return None, []
    with sqlite3.connect(str(AUTH_DB)) as conn:
        row = conn.execute(
            "SELECT name FROM clients WHERE LOWER(name) = LOWER(?) LIMIT 1",
            (raw,),
        ).fetchone()
        if row:
            return row[0], []
        sub = conn.execute(
            "SELECT name FROM clients WHERE LOWER(name) LIKE LOWER(?) LIMIT 5",
            (f"%{raw}%",),
        ).fetchall()
        if len(sub) == 1:
            return sub[0][0], []
        if len(sub) > 1:
            return None, [r[0] for r in sub]
        words = raw.split()
        if len(words) == 1:
            last = conn.execute(
                "SELECT name FROM clients WHERE LOWER(name) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?) LIMIT 5",
                (f"% {raw}", f"{raw} %"),
            ).fetchall()
            if len(last) == 1:
                return last[0][0], []
            if len(last) > 1:
                return None, [r[0] for r in last]
    return None, []


def _ocr_image_to_names(image_path: Path) -> "tuple[list[str], str]":
    """Run Tesseract on an image and return (candidate_names, raw_text).
    Names heuristic: lines with 2+ capitalized words look like 'First Last'."""
    import subprocess
    import re as _re
    try:
        result = subprocess.run(
            ["tesseract", str(image_path), "-", "-l", "eng", "--psm", "6"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        return [], f"tesseract crashed: {e}"
    if result.returncode != 0:
        return [], f"tesseract exit {result.returncode}: {result.stderr[:200]}"
    text = result.stdout
    NAME_RE = _re.compile(r"^([A-Z][a-zA-Zа-яА-ЯёЁ'\-]{1,}(?:\s+[A-Z][a-zA-Zа-яА-ЯёЁ'\-]{1,}){1,2})\s*$")
    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = NAME_RE.match(line)
        if m:
            candidates.append(m.group(1))
    # Dedup preserving order
    seen, uniq = set(), []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower()); uniq.append(c)
    return uniq, text


@router.post("/mobile-signin")
async def mobile_signin(
    photo: UploadFile = File(..., description="JPG/PNG of the sign-in sheet"),
    shift: int = Form(1, description="1 or 2"),
    log_date: Optional[str] = Form(None, description="YYYY-MM-DD; defaults to today"),
    marker_id: str = Form("mobile-signin", description="who uploaded (audit)"),
):
    """T2.1 Option A — staff uploads a phone photo of the day's sign-in sheet.
    Runs Tesseract OCR, extracts candidate names, fuzzy-matches each against
    the clients table, marks high-confidence matches present via the unified
    /present-mark endpoint, and sends low-confidence rows to Kato via the
    OCR Telegram fallback for manual review.

    Returns: { processed, matched: [...], low_conf: [...], ocr_text_chars }
    """
    import tempfile
    from datetime import date as _date

    if shift not in (1, 2):
        raise HTTPException(400, "shift must be 1 or 2")
    if not log_date:
        log_date = _date.today().isoformat()

    # Save upload to a temp file
    tmp = Path(tempfile.mkdtemp(prefix="mobile_signin_")) / (photo.filename or "upload.jpg")
    tmp.write_bytes(await photo.read())

    candidates, raw_text = _ocr_image_to_names(tmp)
    if not candidates:
        return {
            "ok": False,
            "reason": "OCR found no candidate names",
            "ocr_text_chars": len(raw_text),
            "ocr_text_preview": raw_text[:400],
        }

    matched: list[dict] = []
    low_conf: list[dict] = []
    for cand in candidates:
        name, suggestions = _resolve_client_name(cand)
        if name:
            # POST to the unified present-mark endpoint
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.post(
                        "http://127.0.0.1:8000/goj-live/present-mark",
                        json={
                            "client_name": name,
                            "log_date":    log_date,
                            "shift":       shift,
                            "source":      "mobile_ocr",
                            "marker_id":   marker_id,
                            "confidence":  1.0,
                        },
                    )
                    matched.append({"raw": cand, "canonical": name, "ok": r.status_code == 200})
            except Exception as e:
                matched.append({"raw": cand, "canonical": name, "ok": False, "error": str(e)})
        else:
            low_conf.append({"raw": cand, "suggestions": suggestions[:3]})

    # If there are low-confidence rows, send the original photo to Telegram for review
    if low_conf:
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "ocr_fallback",
                str(Path.home() / "Desktop" / "REX" / "CC_ocr_telegram_fallback.py"),
            )
            _ocr_fb = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_ocr_fb)
            unrecognized = ", ".join(e["raw"] for e in low_conf[:5])
            _ocr_fb.flag_for_review(
                source=f"mobile_signin_{log_date}_shift{shift}",
                file_path=tmp,
                reason=f"OCR returned {len(candidates)} names · {len(matched)} matched · {len(low_conf)} unrecognized: {unrecognized}",
                partial={"matched_count": len(matched), "low_conf_count": len(low_conf), "shift": shift, "log_date": log_date},
                bot="goj_attendance",
            )
        except Exception as e:
            logger.warning(f"mobile-signin Telegram fallback failed: {e}")

    return {
        "ok":             True,
        "log_date":       log_date,
        "shift":          shift,
        "processed":      len(candidates),
        "matched":        matched,
        "low_conf":       low_conf,
        "ocr_text_chars": len(raw_text),
    }


@router.get("/mobile-signin", response_class=HTMLResponse)
async def mobile_signin_page():
    """Mobile-friendly upload page so staff can snap a photo and submit
    without needing a custom app. Pure HTML, no framework."""
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GOJ Mobile Sign-In</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0f1a;color:#c8d6e5;padding:24px;max-width:480px;margin:0 auto}
  h1{color:#0ff;font-size:1.4em;margin-bottom:24px}
  label{display:block;font-size:0.9em;color:#6b7d99;margin:16px 0 6px}
  input,select{width:100%;padding:14px;background:#0d1321;border:1px solid #1a2740;border-radius:6px;color:#c8d6e5;font-size:1em}
  input[type=file]{padding:8px}
  button{width:100%;padding:16px;background:#0f8;color:#0a0f1a;border:none;border-radius:6px;font-size:1.1em;font-weight:700;margin-top:24px;cursor:pointer}
  button:disabled{opacity:0.5;cursor:wait}
  #result{margin-top:24px;padding:16px;background:#0d1321;border:1px solid #1a2740;border-radius:6px;font-size:0.9em;display:none}
  .ok{color:#0f8}.warn{color:#ff0}.err{color:#f44}
  .row{margin:4px 0}
</style></head><body>
<h1>📸 GOJ Sign-In Upload</h1>
<form id="f" enctype="multipart/form-data">
  <label>Photo of sign-in sheet</label>
  <input type="file" name="photo" accept="image/*" capture="environment" required>
  <label>Shift</label>
  <select name="shift"><option value="1">Shift 1</option><option value="2">Shift 2</option></select>
  <label>Date (optional, defaults to today)</label>
  <input type="date" name="log_date">
  <button type="submit">Upload + Mark Present</button>
</form>
<div id="result"></div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  const result = document.getElementById('result');
  btn.disabled = true; btn.textContent = 'OCR + Matching…';
  result.style.display = 'block'; result.innerHTML = '<div>Uploading…</div>';
  const data = new FormData(e.target);
  data.append('marker_id', 'mobile:' + (navigator.userAgent.split(' ')[0] || 'unknown'));
  try {
    const r = await fetch('/goj-live/mobile-signin', { method: 'POST', body: data });
    const j = await r.json();
    if (j.ok) {
      const lines = [];
      lines.push(`<div class="ok">✓ Processed ${j.processed} names (${j.matched.length} matched, ${j.low_conf.length} need review)</div>`);
      for (const m of j.matched.slice(0, 20))
        lines.push(`<div class="row">  ✓ <b>${m.canonical}</b> ${m.raw !== m.canonical ? `(from "${m.raw}")` : ''}</div>`);
      for (const lc of j.low_conf.slice(0, 10))
        lines.push(`<div class="row warn">  ? <b>${lc.raw}</b>${lc.suggestions.length ? ' — did you mean: ' + lc.suggestions.join(' / ') : ''}</div>`);
      if (j.low_conf.length) lines.push('<div class="warn" style="margin-top:8px">📤 Photo sent to Telegram for review.</div>');
      result.innerHTML = lines.join('');
    } else {
      result.innerHTML = `<div class="err">✗ ${j.reason || 'failed'}</div>`;
    }
  } catch (err) {
    result.innerHTML = `<div class="err">✗ ${err.message}</div>`;
  }
  btn.disabled = false; btn.textContent = 'Upload Another';
});
</script></body></html>""")


@router.get("/present-mark/today")
async def present_today():
    """Convenience: list everyone marked present today (any source). Used by
    the dashboard UI to show running attendance during the day."""
    if not AUTH_DB.exists():
        raise HTTPException(503, "auth_tracker.db not accessible")
    with sqlite3.connect(str(AUTH_DB)) as conn:
        rows = conn.execute(
            "SELECT client_name, shift, reason FROM attendance_log "
            "WHERE log_date = date('now') AND status = 'present' "
            "ORDER BY shift, client_name"
        ).fetchall()
    return {
        "date":    datetime.now().strftime("%Y-%m-%d"),
        "total":   len(rows),
        "by_shift": {
            "1": [{"name": r[0], "note": r[2]} for r in rows if r[1] == 1],
            "2": [{"name": r[0], "note": r[2]} for r in rows if r[1] == 2],
        },
    }


# ── Proposals ──────────────────────────────────────────────────────────────────

@router.post("/propose")
async def propose_change(proposal: Proposal):
    """Propose a change — queued for Kato approval."""
    store = _load_proposals()
    pid = f"prop_{int(time.time() * 1000)}"
    store["proposals"][pid] = {
        "id": pid,
        "action": proposal.action,
        "client_id": proposal.client_id,
        "description": proposal.description,
        "data": proposal.data,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_proposals(store)
    return {"proposal_id": pid, "status": "pending"}


@router.get("/proposals")
async def list_proposals():
    """List all proposals."""
    store = _load_proposals()
    return store


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    """Approve a proposal (Chairman only)."""
    store = _load_proposals()
    if proposal_id not in store["proposals"]:
        raise HTTPException(404, "Proposal not found")
    store["proposals"][proposal_id]["status"] = "approved"
    store["proposals"][proposal_id]["approved_at"] = datetime.now(timezone.utc).isoformat()
    _save_proposals(store)
    return {"proposal_id": proposal_id, "status": "approved"}


@router.post("/revert/{proposal_id}")
async def revert_proposal(proposal_id: str):
    """Revert an approved proposal."""
    store = _load_proposals()
    if proposal_id not in store["proposals"]:
        raise HTTPException(404, "Proposal not found")
    store["proposals"][proposal_id]["status"] = "reverted"
    store["proposals"][proposal_id]["reverted_at"] = datetime.now(timezone.utc).isoformat()
    _save_proposals(store)
    return {"proposal_id": proposal_id, "status": "reverted"}


# ── Page ───────────────────────────────────────────────────────────────────────

FRONTEND_PATH = Path(os.path.expanduser("~/Desktop/REX/CC_goj_live.html"))


@router.get("/", response_class=HTMLResponse)
async def serve_goj_live():
    """Serve the GOJ Live frontend."""
    if FRONTEND_PATH.exists():
        return HTMLResponse(FRONTEND_PATH.read_text())
    return HTMLResponse("<h2 style='font-family:monospace;color:#0ff;background:#0a0f1a;padding:40px'>GOJ Live — frontend not found</h2>", status_code=404)
