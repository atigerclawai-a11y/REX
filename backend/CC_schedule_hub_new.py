"""
CC_schedule_hub.py — GHS Schedule Hub: Carecenta-powered operations dashboard
=============================================================================
FastAPI router serving the complete schedule ecosystem from ghs_schedule.db.
Mounts to REX at /schedule-hub.

Phase B (2026-07-24): client detail cards, flag engine, mobile, PDF packs.
Phase A+ (2026-07-24): payer analytics, auth-expiration alerts, gap analysis,
  attendance reconciliation + history (auth_tracker = reference only,
  Carecenta stays source of truth), theme toggle, autocomplete, print CSS,
  input validation, loading/error states.

Rolling week convention: DB week 30 = CURRENT week, 31 = NEXT week. Always.
week_bounds() is dynamic (anchored to the current calendar week's Sunday) so it
always agrees with carecenta_weekly_refresh.py. Never store absolute week numbers.
"""
from __future__ import annotations

import re
import json
import hmac
import secrets
import sqlite3
import logging
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Request, Depends, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse, RedirectResponse, JSONResponse

logger = logging.getLogger(__name__)

# ── Auth gate (domain traffic only) ─────────────────────────────────────────
# Requests arriving via the Cloudflare tunnel carry cf-* headers; direct
# localhost traffic does not. Rule: cf-ray present → require session cookie.
# Local scripts (daily pack, smoke tests, REX integration) are unaffected.
AUTH_FILE = Path.home() / ".ghs_schedule_auth.json"
SECRET_FILE = Path.home() / ".ghs_schedule_secret"
COOKIE_NAME = "ghs_sched_session"
SESSION_TTL = 7 * 86400  # 7 days


def _load_or_make_secret() -> bytes:
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes().strip()
    SECRET_FILE.write_text(secrets.token_hex(32))
    SECRET_FILE.chmod(0o600)
    return SECRET_FILE.read_bytes().strip()


def _load_or_make_auth() -> dict:
    """Salted SHA256 password store. Default = unified ecosystem standard;
    overwrite this file to change the password (same pattern as portal-auth)."""
    if AUTH_FILE.exists():
        return json.loads(AUTH_FILE.read_text())
    salt = secrets.token_hex(16)
    pw = "TigerClaw30$"  # unified Hub/portal standard — Kato knows it
    h = hashlib.sha256(f"{salt}:{pw}".encode()).hexdigest()
    AUTH_FILE.write_text(json.dumps({"salt": salt, "hash": h}))
    AUTH_FILE.chmod(0o600)
    return {"salt": salt, "hash": h}


_SECRET = _load_or_make_secret()
_AUTH = _load_or_make_auth()


def _check_password(pw: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(f"{_AUTH['salt']}:{pw}".encode()).hexdigest(), _AUTH["hash"])


def _make_token() -> str:
    exp = str(int(datetime.now().timestamp()) + SESSION_TTL)
    sig = hmac.new(_SECRET, exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _valid_token(token: str) -> bool:
    try:
        exp, sig = token.split(".", 1)
        want = hmac.new(_SECRET, exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, want) and int(exp) > int(datetime.now().timestamp())
    except Exception:
        return False


class LoginRedirect(HTTPException):
    def __init__(self):
        super().__init__(status_code=303, detail="login",
                         headers={"Location": "/schedule-hub/login"})


async def gate(request: Request):
    if not request.headers.get("cf-ray"):
        return
    if request.url.path.endswith("/login"):
        return
    if _valid_token(request.cookies.get(COOKIE_NAME, "")):
        return
    if "/api/" in request.url.path or request.url.path.endswith("/health"):
        raise HTTPException(status_code=401, detail="authentication required")
    raise LoginRedirect()


router = APIRouter(prefix="/schedule-hub", tags=["Schedule Hub"],
                   dependencies=[Depends(gate)])


# ── Login (only reachable path without a session on domain traffic) ─────────

_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GHS Schedule Hub — Sign In</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0a0a0f;font-family:-apple-system,BlinkMacSystemFont,sans-serif}
.card{background:#141420;border:1px solid #252540;border-radius:14px;padding:36px;width:320px;text-align:center}
h1{color:#4fc3f7;font-size:1.15em;margin:0 0 4px}
.sub{color:#888;font-size:.78em;margin-bottom:22px}
input{width:100%;padding:12px;border-radius:8px;border:1px solid #252540;background:#0a0a0f;
color:#e0e0e0;font-size:.95em;box-sizing:border-box;margin-bottom:12px}
button{width:100%;padding:12px;border-radius:8px;border:none;background:#4fc3f7;color:#0a0a0f;
font-weight:700;font-size:.95em;cursor:pointer}
.err{color:#ef5350;font-size:.78em;min-height:1em;margin-bottom:8px}
</style></head><body>
<div class="card">
<h1>📋 GHS Schedule Hub</h1>
<div class="sub">Gold Health Systems · Authorized access only</div>
<div class="err">__ERR__</div>
<form method="post" action="/schedule-hub/login">
<input type="password" name="password" placeholder="Password" autofocus required>
<button type="submit">Sign In</button>
</form></div></body></html>"""


@router.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(_LOGIN_PAGE.replace("__ERR__", ""))


@router.post("/login")
async def login_submit(password: str = Form(...)):
    if not _check_password(password):
        return HTMLResponse(_LOGIN_PAGE.replace("__ERR__", "Incorrect password."),
                            status_code=401)
    resp = RedirectResponse(url="/schedule-hub/", status_code=303)
    resp.set_cookie(COOKIE_NAME, _make_token(), max_age=SESSION_TTL,
                    httponly=True, secure=True, samesite="lax")
    return resp

# ── Config ──────────────────────────────────────────────────────────────────
SCHEDULE_DB = Path.home() / "Desktop" / "REX" / "signin_lists" / "ghs_schedule.db"
AUTH_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
PDF_OUT_DIR = Path.home() / "Desktop" / "REX" / "signin_lists" / "daily_packs"
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DAY_CODES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

# ── Fonts (GOJ rule: DejaVu Sans only — Cyrillic-capable) ───────────────────
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS_DIR = Path.home() / "Documents" / "goj files" / "fonts"
FONT_REG = "DejaVu"
FONT_BOLD = "DejaVuBold"
try:
    pdfmetrics.registerFont(TTFont(FONT_REG, str(FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONTS_DIR / "DejaVuSans-Bold.ttf")))
except Exception:
    FONT_REG = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"

# ── DB helpers ───────────────────────────────────────────────────────────────

def get_db():
    """Connection to the schedule database."""
    conn = sqlite3.connect(str(SCHEDULE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def auth_db_ro():
    """Read-only connection to auth_tracker (PHI — local only, never leaves machine)."""
    conn = sqlite3.connect(f"file:{AUTH_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Week math (rolling 30/31) ────────────────────────────────────────────────

def current_sunday() -> date:
    """Sunday of the current calendar week (GOJ weeks run Sun-Sat)."""
    today = date.today()
    return today - timedelta(days=today.isoweekday() % 7)


def week_bounds(week: int) -> tuple[date, date]:
    """(sunday, saturday) for a DB week number. Rolling: 30=current, 31=next."""
    sunday = current_sunday() + timedelta(days=(week - 30) * 7)
    return sunday, sunday + timedelta(days=6)


def get_today_day_code() -> str:
    """Today's day code (sun..sat). isoweekday: Mon=1..Sun=7 → %7 gives Sun=0."""
    return DAY_CODES[datetime.now().isoweekday() % 7]


def get_monday_date() -> str:
    """Next Monday's date."""
    today = date.today()
    d = (7 - today.weekday()) % 7
    if d == 0:
        d = 7
    return (today + timedelta(days=d)).isoformat()


# ── Validation ───────────────────────────────────────────────────────────────

def day_index(day: str) -> int:
    try:
        return DAY_CODES.index(day)
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"Invalid day '{day}'. Use: {', '.join(DAY_CODES)}")


def valid_week(week: int) -> int:
    if week not in (30, 31):
        raise HTTPException(status_code=400,
                            detail="Invalid week. Rolling weeks: 30 (current), 31 (next)")
    return week


# ── Flag engine ──────────────────────────────────────────────────────────────

def norm_payer(p: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (p or "").upper())


def payers_match(a: Optional[str], b: Optional[str]) -> bool:
    """Fuzzy payer match — 'ANTHEM HP' vs 'ANTHEM HP, LLC', 'AETNA' vs 'AETNA transport'."""
    na, nb = norm_payer(a), norm_payer(b)
    if not na or not nb or na == "UNKNOWN" or nb == "UNKNOWN":
        return True  # can't verify → don't flag
    return na.startswith(nb) or nb.startswith(na) or na[:6] == nb[:6]


def compute_flags(sched_payer, has_transport, auths, week_sat: date) -> list[dict]:
    """
    Shared flag engine (flags.md spec). EXPIRING threshold: auth ends before
    (viewed week's Saturday + 14 days) — the established convention.
    Returns list of {code, label, sev}.
    """
    threshold = (week_sat + timedelta(days=14)).isoformat()
    active = [a for a in auths if a["status"] == "ACTIVE"]
    flags = []
    if not active:
        flags.append({"code": "NO_AUTH", "label": "🔴 NO AUTH", "sev": "red"})
    else:
        best_end = max((a["service_end"] or "" for a in active), default="")
        if best_end and best_end < threshold:
            flags.append({"code": "EXPIRING", "label": "⚠️ EXPIRING", "sev": "yellow",
                          "detail": best_end})
        if sched_payer and not any(payers_match(a["payer"], sched_payer) for a in active):
            flags.append({"code": "PAYER_MISMATCH", "label": "🔄 PAYER MISMATCH", "sev": "orange"})
    if not has_transport:
        flags.append({"code": "NO_TRANSPORT", "label": "🚫 NO TRANSPORT", "sev": "blue"})
    if not flags:
        flags.append({"code": "CLEAN", "label": "✅ CLEAN", "sev": "green"})
    return flags


def get_auths_map(db, client_ids: list[int]) -> dict[int, list[dict]]:
    """ACTIVE/PENDING auths for many clients in one query."""
    if not client_ids:
        return {}
    q = ",".join("?" * len(client_ids))
    rows = db.execute(
        f"""SELECT client_id, payer, auth_number, service_start, service_end, status
            FROM authorizations WHERE client_id IN ({q})
            ORDER BY service_end DESC""",
        client_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["client_id"], []).append(dict(r))
    return out


def token_key(s: str) -> str:
    """Order-insensitive alpha-token key — matches 'Last, First <id>' to 'Last First'."""
    return " ".join(sorted(re.findall(r"[a-z]+", (s or "").lower())))


def routes_by_client(db) -> dict[str, list[dict]]:
    """All driver routes keyed by normalized client-name token set."""
    rows = db.execute(
        """SELECT day_of_week, shift, client_name, client_address, client_phone,
                  driver_name, driver_phone FROM driver_routes"""
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(token_key(r["client_name"]), []).append(dict(r))
    return out


def get_day_rows(db, week: int, day_idx: int) -> list[dict]:
    """Schedule rows for a day + computed flags. Single source for API + PDF."""
    _, week_sat = week_bounds(week)
    rows = db.execute(
        """SELECT c.id AS client_id, c.full_name, c.first_name, c.last_name,
                  s.time_slot, s.shift, s.payer, s.has_transport, s.is_cancelled
           FROM schedule s JOIN clients c ON c.id = s.client_id
           WHERE s.week_number = ? AND s.day_of_week = ? AND s.is_cancelled = 0
           ORDER BY s.shift, c.last_name""",
        (week, day_idx),
    ).fetchall()
    auths_map = get_auths_map(db, [r["client_id"] for r in rows])
    results = []
    for r in rows:
        auths = auths_map.get(r["client_id"], [])
        flags = compute_flags(r["payer"], r["has_transport"], auths, week_sat)
        active = [a for a in auths if a["status"] == "ACTIVE"]
        best_end = max((a["service_end"] or "" for a in active), default=None)
        auth_payer = active[0]["payer"] if active else None
        results.append({
            "client_id": r["client_id"],
            "name": r["full_name"],
            "time": r["time_slot"],
            "shift": r["shift"],
            "payer": r["payer"],
            "transport": bool(r["has_transport"]),
            "flags": [f["label"] for f in flags],
            "flag_objs": flags,
            "issues": any(f["sev"] in ("red", "yellow", "orange") for f in flags),
            "auth_expires": best_end,
            "auth_payer": auth_payer,
        })
    return results


# ── API: sign-in ─────────────────────────────────────────────────────────────

@router.get("/api/signin")
async def api_signin(
    day: str = Query(default=None, description="Day code: mon, tue, wed, etc."),
    week: int = Query(default=31, description="Week: 30 (current) or 31 (next)"),
    shift: Optional[str] = Query(default=None, description="MORNING or AFTERNOON"),
    transport_only: bool = Query(default=False),
    issues_only: bool = Query(default=False),
    payer: Optional[str] = Query(default=None),
):
    """Sign-in list for a day, with the full flag engine."""
    day_idx = day_index(day) if day else day_index(get_today_day_code())
    valid_week(week)

    db = get_db()
    results = get_day_rows(db, week, day_idx)
    db.close()

    if shift:
        results = [r for r in results if r["shift"] == shift]
    if transport_only:
        results = [r for r in results if r["transport"]]
    if issues_only:
        results = [r for r in results if r["issues"]]
    if payer:
        results = [r for r in results if payer.upper() in (r["payer"] or "").upper()]

    sunday, saturday = week_bounds(week)
    return {
        "day": DAY_NAMES[day_idx],
        "day_code": DAY_CODES[day_idx],
        "day_date": (sunday + timedelta(days=day_idx)).isoformat(),
        "week": week,
        "week_start": sunday.isoformat(),
        "week_end": saturday.isoformat(),
        "total": len(results),
        "morning": len([x for x in results if x["shift"] == "MORNING"]),
        "afternoon": len([x for x in results if x["shift"] == "AFTERNOON"]),
        "issues": len([x for x in results if x["issues"]]),
        "clients": results,
    }


# ── API: client profile ─────────────────────────────────────────────────────

@router.get("/api/client/{client_id}")
async def api_client(client_id: int):
    """Client detail card: profile, both week grids, auth history, transport."""
    db = get_db()
    c = db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not c:
        db.close()
        raise HTTPException(status_code=404, detail="Client not found")

    sched = db.execute(
        """SELECT week_number, day_of_week, time_slot, shift, payer,
                  has_transport, is_cancelled
           FROM schedule WHERE client_id = ? ORDER BY week_number, day_of_week""",
        (client_id,),
    ).fetchall()

    auths = [dict(r) for r in db.execute(
        """SELECT payer, auth_number, service_start, service_end, status, synced_at
           FROM authorizations WHERE client_id = ? ORDER BY service_end DESC""",
        (client_id,),
    ).fetchall()]

    routes = routes_by_client(db).get(token_key(f"{c['first_name']} {c['last_name']}"), [])
    db.close()

    weeks: dict[str, dict] = {}
    for wk in (30, 31):
        _, wk_sat = week_bounds(wk)
        grid: dict[str, dict] = {}
        for r in sched:
            if r["week_number"] != wk:
                continue
            flags = compute_flags(r["payer"], r["has_transport"], auths, wk_sat)
            grid[DAY_CODES[r["day_of_week"]]] = {
                "time": r["time_slot"], "shift": r["shift"], "payer": r["payer"],
                "transport": bool(r["has_transport"]), "cancelled": bool(r["is_cancelled"]),
                "flags": [f["label"] for f in flags],
            }
        sunday, saturday = week_bounds(wk)
        weeks[str(wk)] = {"start": sunday.isoformat(), "end": saturday.isoformat(), "days": grid}

    _, sat31 = week_bounds(31)
    overall = compute_flags(None, 1, auths, sat31)

    return {
        "id": c["id"],
        "carecenta_id": c["carecenta_id"],
        "full_name": c["full_name"],
        "first_name": c["first_name"],
        "last_name": c["last_name"],
        "status": c["status"],
        "weeks": weeks,
        "authorizations": auths,
        "transport_routes": routes,
        "overall_flags": [f["label"] for f in overall],
    }


@router.get("/api/client/{client_id}/attendance")
async def api_client_attendance(client_id: int, limit: int = Query(default=60)):
    """Attendance history for one client (reference: auth_tracker.attendance_log)."""
    db = get_db()
    c = db.execute("SELECT id, first_name, last_name FROM clients WHERE id = ?",
                   (client_id,)).fetchone()
    db.close()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    key = token_key(f"{c['first_name']} {c['last_name']}")

    adb = auth_db_ro()
    rows = adb.execute(
        """SELECT log_date, day_key, shift, status, source, note, client_name
           FROM attendance_log
           WHERE log_date >= date('now', '-120 days')
           ORDER BY log_date DESC LIMIT 20000""",
    ).fetchall()
    adb.close()

    hist = []
    for r in rows:
        if token_key(r["client_name"]) == key:
            hist.append({k: r[k] for k in ("log_date", "day_key", "shift", "status", "source", "note")})
        if len(hist) >= limit:
            break

    attended = len([h for h in hist if (h["status"] or "").lower() in ("attended", "present")])
    return {
        "client_id": client_id,
        "records": len(hist),
        "attended": attended,
        "other": len(hist) - attended,
        "history": hist,
    }


# ── API: lookup / search ────────────────────────────────────────────────────

@router.get("/api/clients/lookup")
async def api_clients_lookup(q: str = Query(..., min_length=1), limit: int = Query(default=8)):
    """Fast autocomplete lookup — id + name only."""
    db = get_db()
    rows = db.execute(
        "SELECT id, full_name FROM clients WHERE full_name LIKE ? ORDER BY last_name LIMIT ?",
        (f"%{q}%", limit),
    ).fetchall()
    db.close()
    return {"results": [{"id": r["id"], "name": r["full_name"]} for r in rows]}


@router.get("/api/search")
async def api_search(q: str = Query(..., min_length=2), week: int = Query(default=31)):
    """Search clients by name (schedule-scoped)."""
    valid_week(week)
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT c.id AS client_id, c.full_name, s.day_name, s.time_slot, s.shift, s.payer
           FROM schedule s JOIN clients c ON c.id = s.client_id
           WHERE s.week_number = ? AND c.full_name LIKE ?
           ORDER BY s.day_of_week, s.shift""",
        (week, f"%{q}%"),
    ).fetchall()
    nosched = db.execute(
        """SELECT id AS client_id, full_name, NULL AS day_name, NULL AS time_slot,
                  NULL AS shift, NULL AS payer
           FROM clients WHERE full_name LIKE ?
           AND id NOT IN (SELECT client_id FROM schedule WHERE week_number = ?)
           ORDER BY last_name LIMIT 20""",
        (f"%{q}%", week),
    ).fetchall()
    db.close()
    return {"query": q, "results": [dict(r) for r in rows] + [dict(r) for r in nosched]}


# ── API: alerts / analytics / gaps / reconciliation ─────────────────────────

@router.get("/api/auth-alerts")
async def api_auth_alerts():
    """Renewals due — ACTIVE auths expiring within the operational horizon
    (next week's Saturday + 14 days, the established EXPIRING convention)."""
    _, sat31 = week_bounds(31)
    horizon = sat31 + timedelta(days=14)
    today = date.today()

    db = get_db()
    rows = db.execute(
        """SELECT c.id AS client_id, c.full_name, a.payer, a.auth_number, a.service_end
           FROM authorizations a JOIN clients c ON c.id = a.client_id
           WHERE a.status = 'ACTIVE' AND a.service_end IS NOT NULL AND a.service_end != ''
             AND a.service_end < ?
           ORDER BY a.service_end""",
        (horizon.isoformat(),),
    ).fetchall()
    db.close()

    alerts = []
    # Dedupe per client — keep the BEST (latest-ending) ACTIVE auth, matching
    # compute_flags semantics: a client covered past the horizon is not an alert.
    best: dict[int, dict] = {}
    for r in rows:
        cur = best.get(r["client_id"])
        if cur is None or (r["service_end"] or "") > (cur["service_end"] or ""):
            best[r["client_id"]] = dict(r)
    for r in best.values():
        try:
            end = date.fromisoformat(r["service_end"][:10])
        except ValueError:
            continue
        days_left = (end - today).days
        sev = "critical" if days_left <= 7 else ("warning" if days_left <= 14 else "watch")
        alerts.append({"client_id": r["client_id"], "name": r["full_name"],
                       "payer": r["payer"], "auth_number": r["auth_number"],
                       "service_end": r["service_end"], "days_left": days_left, "severity": sev})
    alerts.sort(key=lambda a: a["days_left"])

    return {
        "horizon": horizon.isoformat(),
        "total": len(alerts),
        "critical": len([a for a in alerts if a["severity"] == "critical"]),
        "warning": len([a for a in alerts if a["severity"] == "warning"]),
        "watch": len([a for a in alerts if a["severity"] == "watch"]),
        "alerts": alerts,
    }


@router.get("/api/analytics/payers")
async def api_payer_analytics(week: int = Query(default=31)):
    """Payer distribution + auth coverage + transport + expiring, per payer."""
    valid_week(week)
    _, week_sat = week_bounds(week)
    threshold = (week_sat + timedelta(days=14)).isoformat()

    db = get_db()
    payers = db.execute(
        """SELECT s.payer, COUNT(DISTINCT s.client_id) AS clients,
                  SUM(s.has_transport) AS transport_rows,
                  COUNT(*) AS schedule_rows
           FROM schedule s
           WHERE s.week_number = ? AND s.is_cancelled = 0
           GROUP BY s.payer ORDER BY clients DESC""",
        (week,),
    ).fetchall()

    out = []
    for p in payers:
        client_ids = [r[0] for r in db.execute(
            """SELECT DISTINCT client_id FROM schedule
               WHERE week_number = ? AND is_cancelled = 0 AND payer IS ?""",
            (week, p["payer"])).fetchall()]
        auths_map = get_auths_map(db, client_ids)
        with_auth = sum(1 for cid in client_ids
                        if any(a["status"] == "ACTIVE" for a in auths_map.get(cid, [])))
        expiring = sum(1 for cid in client_ids
                       if any(a["status"] == "ACTIVE" and a["service_end"] and a["service_end"] < threshold
                              for a in auths_map.get(cid, [])))
        out.append({
            "payer": p["payer"] or "(unknown)",
            "clients": p["clients"],
            "schedule_rows": p["schedule_rows"],
            "transport_rows": p["transport_rows"] or 0,
            "with_auth": with_auth,
            "no_auth": p["clients"] - with_auth,
            "expiring": expiring,
        })
    db.close()
    total = sum(x["clients"] for x in out)
    return {"week": week, "total_clients": total, "payers": out}


@router.get("/api/gaps")
async def api_gaps():
    """Gap analysis — clients with a future ACTIVE auth in auth_tracker who have
    NO schedule in Carecenta (reference only; Carecenta stays source of truth)."""
    today = date.today().isoformat()

    adb = auth_db_ro()
    auth_rows = adb.execute(
        """SELECT client_name, payer_raw, service_end_date
           FROM authorization WHERE status = 'ACTIVE' AND service_end_date >= ?
           ORDER BY client_name""",
        (today,),
    ).fetchall()
    adb.close()

    db = get_db()
    known = {token_key(f"{first} {last}") for last, first in
             db.execute("SELECT last_name, first_name FROM clients")}
    db.close()

    gaps, seen = [], set()
    for r in auth_rows:
        key = token_key(r["client_name"])
        if key and key not in known and key not in seen:
            seen.add(key)
            gaps.append({"client_name": r["client_name"], "payer": r["payer_raw"],
                         "auth_expires": r["service_end_date"]})

    return {"total": len(gaps), "gaps": gaps}


@router.get("/api/reconciliation")
async def api_reconciliation(date_str: str = Query(default=None, alias="date")):
    """Carecenta expected vs actual attendance (auth_tracker.attendance_log)
    for a date within the loaded weeks. Reference-only actuals."""
    try:
        target = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad date. Use YYYY-MM-DD.")

    delta_weeks = (target - current_sunday()).days // 7
    week = 30 + delta_weeks
    if week not in (30, 31):
        raise HTTPException(status_code=400,
                            detail="Date outside loaded weeks (current=30, next=31)")
    wk_sun, _ = week_bounds(week)
    day_idx = (target - wk_sun).days

    db = get_db()
    expected = get_day_rows(db, week, day_idx)
    db.close()

    adb = auth_db_ro()
    actual_rows = adb.execute(
        "SELECT client_name, status, shift, note FROM attendance_log WHERE log_date = ?",
        (target.isoformat(),),
    ).fetchall()
    adb.close()

    actual: dict[str, dict] = {}
    for r in actual_rows:
        k = token_key(r["client_name"])
        attended = (r["status"] or "").lower() in ("attended", "present")
        if k not in actual or attended:
            actual[k] = {"status": r["status"], "attended": attended}

    attended_keys = {k for k, v in actual.items() if v["attended"]}
    expected_keys = {token_key(e["name"]) for e in expected}

    no_show = [e for e in expected if token_key(e["name"]) not in attended_keys]
    walk_in = sorted(attended_keys - expected_keys)
    matched = expected_keys & attended_keys

    return {
        "date": target.isoformat(),
        "expected": len(expected),
        "logged_actual": len(actual_rows),
        "attended": len(attended_keys),
        "matched": len(matched),
        "no_show": [{"name": e["name"], "time": e["time"], "shift": e["shift"]} for e in no_show],
        "attended_not_scheduled": walk_in,
        "match_rate": round(100 * len(matched) / len(expected), 1) if expected else None,
    }


# ── API: weekly / kitchen / drivers / summary ───────────────────────────────

@router.get("/api/weekly")
async def api_weekly(week: int = Query(default=31)):
    valid_week(week)
    db = get_db()
    rows = db.execute("SELECT * FROM v_weekly").fetchall()
    db.close()
    sunday, saturday = week_bounds(week)
    return {"week": week, "week_start": sunday.isoformat(),
            "week_end": saturday.isoformat(), "clients": [dict(r) for r in rows]}


@router.get("/api/kitchen")
async def api_kitchen(week: int = Query(default=31)):
    valid_week(week)
    db = get_db()
    rows = db.execute("SELECT * FROM v_kitchen").fetchall()
    db.close()
    return {"week": week, "counts": [dict(r) for r in rows]}


@router.get("/api/drivers")
async def api_drivers(day: Optional[str] = Query(default=None),
                      week: int = Query(default=31)):
    """Transport-authorized clients."""
    valid_week(week)
    db = get_db()
    if day:
        rows = db.execute(
            """SELECT c.id AS client_id, c.full_name, s.time_slot, s.shift, s.payer
               FROM schedule s JOIN clients c ON c.id = s.client_id
               WHERE s.week_number = ? AND s.day_of_week = ?
               AND s.has_transport = 1 AND s.is_cancelled = 0
               ORDER BY s.shift, c.last_name""",
            (week, day_index(day)),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM v_drivers WHERE week_number = ?", (week,)).fetchall()
    db.close()
    return {"day": day, "clients": [dict(r) for r in rows]}


@router.get("/api/driver-list")
async def api_driver_list(day: Optional[str] = Query(default=None)):
    """Driver route assignments (from Drive TR tabs)."""
    db = get_db()
    if day:
        day_index(day)
        rows = db.execute(
            "SELECT * FROM driver_routes WHERE day_of_week = ? ORDER BY shift, driver_name, client_name",
            (day,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM driver_routes ORDER BY day_of_week, shift, driver_name, client_name"
        ).fetchall()
    db.close()

    drivers: dict[str, list] = {}
    for r in rows:
        r = dict(r)
        drivers.setdefault(r.get("driver_name") or "UNASSIGNED", []).append(r)

    return {"day": day, "total_clients": len(rows), "drivers": drivers}


@router.get("/api/summary")
async def api_summary():
    """Daily attendance summary + DB freshness."""
    db = get_db()
    rows = db.execute("SELECT * FROM v_daily_summary").fetchall()
    gaps = db.execute(
        "SELECT COUNT(DISTINCT full_name) FROM v_auth_gaps WHERE day_name = 'MON'"
    ).fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM clients").fetchone()[0]

    _, sat31 = week_bounds(31)
    threshold = (sat31 + timedelta(days=14)).isoformat()
    expiring = db.execute(
        "SELECT COUNT(DISTINCT client_id) FROM authorizations WHERE status='ACTIVE' AND service_end < ?",
        (threshold,),
    ).fetchone()[0]
    db.close()

    mtime = datetime.fromtimestamp(SCHEDULE_DB.stat().st_mtime) if SCHEDULE_DB.exists() else None
    age_h = round((datetime.now() - mtime).total_seconds() / 3600, 1) if mtime else None

    return {
        "total_clients": total,
        "auth_gaps": gaps,
        "auth_expiring": expiring,
        "daily": [dict(r) for r in rows],
        "next_monday": get_monday_date(),
        "db_updated": mtime.isoformat() if mtime else None,
        "db_age_hours": age_h,
    }


# ── API: exports ─────────────────────────────────────────────────────────────

@router.get("/api/export/signin")
async def export_signin(day: str = Query(default="mon"),
                        week: int = Query(default=31),
                        format: str = Query(default="csv")):
    """Sign-in sheet as CSV or plain text."""
    day_idx = day_index(day)
    valid_week(week)
    db = get_db()
    rows = get_day_rows(db, week, day_idx)
    db.close()
    sunday, _ = week_bounds(week)
    day_date = (sunday + timedelta(days=day_idx)).isoformat()

    if format == "csv":
        lines = ["Name,Time,Shift,Payer,Transport,Auth,Flags"]
        for r in rows:
            auth = "Active" if not any(f["code"] == "NO_AUTH" for f in r["flag_objs"]) else "None"
            lines.append(
                f'"{r["name"]}",{r["time"]},{r["shift"]},{r["payer"]},'
                f'{"Yes" if r["transport"] else "No"},{auth},"{" ".join(r["flags"])}"'
            )
        return PlainTextResponse("\n".join(lines), media_type="text/csv")
    else:
        lines = [f"GOJ SIGN-IN — {DAY_NAMES[day_idx].upper()} {day_date} — Week {week}"]
        lines.append("=" * 50)
        for r in rows:
            tr = "🚗" if r["transport"] else "✗"
            lines.append(f'[ ] {r["name"]} — {r["time"]} — {r["payer"]} {tr}  {" ".join(r["flags"])}')
        return PlainTextResponse("\n".join(lines))


# ── PDF generation ───────────────────────────────────────────────────────────

PDF_OUT_DIR.mkdir(parents=True, exist_ok=True)

CELL = ParagraphStyle("cell", fontSize=11, fontName=FONT_REG, leading=13, alignment=TA_LEFT)
TITLE = ParagraphStyle("title", fontSize=14, fontName=FONT_BOLD, alignment=TA_CENTER, spaceAfter=6)
SUB = ParagraphStyle("sub", fontSize=12, fontName=FONT_REG, alignment=TA_CENTER, spaceAfter=8)
SECT = ParagraphStyle("sect", fontSize=13, fontName=FONT_BOLD, alignment=TA_LEFT,
                      textColor=colors.HexColor("#204080"), spaceAfter=4)


def _pdf_flag_text(row: dict) -> str:
    """Text-only flags for PDF (DejaVu has no emoji glyphs). CLEAN omitted."""
    return " ".join(f"[{f['code'].replace('_', ' ')}]"
                    for f in row["flag_objs"] if f["code"] != "CLEAN")


def _signin_pages(story, week: int, day_idx: int, rows: list[dict]):
    """Sign-in section: 7-col template (No|Name|Plan|TR|Time In|Time Out|Signature)."""
    sunday, _ = week_bounds(week)
    day_date = sunday + timedelta(days=day_idx)

    story.append(Paragraph("GARDEN OF JOY ADULT DAY CARE CENTER — SIGN-IN SHEET", TITLE))
    story.append(Paragraph(f"{DAY_NAMES[day_idx]}, {day_date.isoformat()}  ·  Week {week} "
                           f"({sunday.isoformat()} – {(sunday + timedelta(days=6)).isoformat()})", SUB))

    col_widths = [0.4 * inch, 2.5 * inch, 1.5 * inch, 0.45 * inch, 0.9 * inch, 0.9 * inch, 1.85 * inch]

    for shift_label, shift_rows in (("MORNING SHIFT", [r for r in rows if r["shift"] == "MORNING"]),
                                    ("AFTERNOON SHIFT", [r for r in rows if r["shift"] != "MORNING"])):
        if not shift_rows:
            continue
        story.append(Paragraph(f"{shift_label} — {len(shift_rows)} clients", SECT))
        data = [["No", "Name", "Plan", "TR", "Time In", "Time Out", "Signature"]]
        for i, r in enumerate(shift_rows, 1):
            flag_txt = _pdf_flag_text(r)
            name_html = r["name"] + (f"<br/><font size=8 color='#aa3333'>{flag_txt}</font>" if flag_txt else "")
            data.append([str(i), Paragraph(name_html, CELL), Paragraph(r["payer"] or "?", CELL),
                         "Yes" if r["transport"] else "—", "", "", ""])
        row_heights = [22] + [30] * (len(data) - 1)
        tbl = Table(data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("FONTNAME", (0, 1), (-1, -1), FONT_REG),
            ("FONTSIZE", (0, 1), (-1, -1), 11),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#204080")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F5FF")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(
        "Total present: ______   Staff signature: ___________________________   Date: __________",
        SUB))


def _driver_pages(story, day_code: str, day_idx: int):
    """Driver routes section (Drive TR tab assignments)."""
    db = get_db()
    rows = db.execute(
        """SELECT * FROM driver_routes WHERE day_of_week = ?
           ORDER BY shift, driver_name, client_name""",
        (day_code,),
    ).fetchall()
    db.close()

    story.append(Paragraph(f"GARDEN OF JOY — DRIVER ROUTES — {DAY_NAMES[day_idx].upper()}", TITLE))
    if not rows:
        story.append(Paragraph("No route assignments on file for this day.", SUB))
        return

    col_widths = [0.4 * inch, 2.3 * inch, 3.1 * inch, 1.5 * inch, 1.2 * inch]
    current = None
    data = None

    def flush():
        nonlocal data
        if data and len(data) > 1:
            row_heights = [22] + [28] * (len(data) - 1)
            tbl = Table(data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("FONTNAME", (0, 1), (-1, -1), FONT_REG),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F8F0")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.12 * inch))

    n = 0
    for r in rows:
        group = f"{r['shift']} · {r['driver_name']}"
        if group != current:
            flush()
            current = group
            n = 0
            phone = r["driver_phone"] or ""
            story.append(Paragraph(f"{r['shift']} — DRIVER: {r['driver_name']}"
                                   + (f"  ·  {phone}" if phone else ""), SECT))
            data = [["No", "Client Name", "Address", "Phone", "Notes"]]
        n += 1
        data.append([str(n), Paragraph(r["client_name"], CELL),
                     Paragraph(r["client_address"] or "", CELL),
                     Paragraph(r["client_phone"] or "", CELL), ""])
    flush()
    story.append(Paragraph(f"Total clients: {len(rows)}   Driver signature: _______________", SUB))


def _kitchen_pages(story, week: int, day_idx: int, rows: list[dict]):
    """Kitchen meal-count section (counts from schedule; menus live in goj_proprietary.db)."""
    sunday, _ = week_bounds(week)
    day_date = sunday + timedelta(days=day_idx)
    story.append(Paragraph("GARDEN OF JOY — KITCHEN MEAL COUNT", TITLE))
    story.append(Paragraph(f"{DAY_NAMES[day_idx]}, {day_date.isoformat()}", SUB))

    am = len([r for r in rows if r["shift"] == "MORNING"])
    pm = len([r for r in rows if r["shift"] != "MORNING"])
    tr = len([r for r in rows if r["transport"]])
    data = [["Shift", "Meals", "Transport"],
            ["Morning (9AM-1PM)", str(am), str(len([r for r in rows if r["shift"] == "MORNING" and r["transport"]]))],
            ["Afternoon (1PM-5PM)", str(pm), str(len([r for r in rows if r["shift"] != "MORNING" and r["transport"]]))],
            ["TOTAL", str(am + pm), str(tr)]]
    tbl = Table(data, colWidths=[3.2 * inch, 1.4 * inch, 1.4 * inch], rowHeights=[24, 26, 26, 28])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REG),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#204080")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8EEF9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "Counts from Carecenta schedule. Per-client menu/diet detail: goj_proprietary.db "
        "(goj_kitchen_paired.py).", SUB))


def _build_pack_pdf(days: list[int], week: int) -> Path:
    """Multi-day (or single-day) operations pack PDF."""
    sunday, _ = week_bounds(week)
    if len(days) == 1:
        fname = f"daily_pack_{DAY_CODES[days[0]]}_{(sunday + timedelta(days=days[0])).isoformat()}.pdf"
    else:
        fname = f"weekly_pack_week{week}_{sunday.isoformat()}.pdf"
    out = PDF_OUT_DIR / fname

    doc = SimpleDocTemplate(str(out), pagesize=letter,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            title=f"GOJ Pack Week {week}")
    story: list = []
    db = get_db()
    for i, day_idx in enumerate(days):
        rows = get_day_rows(db, week, day_idx)
        if i > 0:
            story.append(PageBreak())
        _signin_pages(story, week, day_idx, rows)
        story.append(PageBreak())
        _driver_pages(story, DAY_CODES[day_idx], day_idx)
        story.append(PageBreak())
        _kitchen_pages(story, week, day_idx, rows)
    db.close()
    doc.build(story)
    return out


@router.get("/api/export/daily-pdf")
async def export_daily_pdf(day: str = Query(default="mon"), week: int = Query(default=31)):
    """Single-day operations pack PDF: sign-in + driver routes + kitchen count."""
    out = _build_pack_pdf([day_index(day)], valid_week(week))
    return FileResponse(str(out), media_type="application/pdf", filename=out.name)


@router.get("/api/export/weekly-pack")
async def export_weekly_pack(week: int = Query(default=31)):
    """Bulk PDF: every day's sign-in + driver + kitchen sheets in one file."""
    valid_week(week)
    db = get_db()
    days = [r[0] for r in db.execute(
        "SELECT DISTINCT day_of_week FROM schedule WHERE week_number = ? ORDER BY day_of_week",
        (week,),
    ).fetchall()]
    db.close()
    if not days:
        raise HTTPException(status_code=404, detail=f"No schedule data for week {week}")
    out = _build_pack_pdf(days, week)
    return FileResponse(str(out), media_type="application/pdf", filename=out.name)


# ── HTML Dashboard ───────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the Schedule Hub dashboard."""
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>GHS Schedule Hub — DataRex</title>
<style>
:root, :root[data-theme='dark'] {
  --bg: #0a0a0f; --surface: #141420; --border: #252540;
  --text: #e0e0e0; --dim: #888; --accent: #4fc3f7;
  --green: #66bb6a; --red: #ef5350; --yellow: #ffa726;
  --orange: #ff7043; --blue: #64b5f6;
  --morning: #ffcc80; --afternoon: #90caf9;
  --hover: rgba(79,195,247,.05);
}
:root[data-theme='light'] {
  --bg: #f5f6fa; --surface: #ffffff; --border: #d8dce6;
  --text: #1a1d26; --dim: #667; --accent: #0277bd;
  --green: #2e7d32; --red: #c62828; --yellow: #f9a825;
  --orange: #e64a19; --blue: #1565c0;
  --morning: #e65100; --afternoon: #1565c0;
  --hover: rgba(2,119,189,.06);
}
* { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,sans-serif; transition:background .2s,color .2s; }
.header { background:var(--surface); border-bottom:1px solid var(--border); padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; }
.header h1 { font-size:1.3em; color:var(--accent); }
.header .stats { display:flex; gap:14px; font-size:.8em; color:var(--dim); flex-wrap:wrap; align-items:center; }
.hdr-btns { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.hdr-btns button { padding:7px 12px; border-radius:6px; border:1px solid var(--border); background:var(--bg); color:var(--dim); cursor:pointer; font-size:.8em; min-height:36px; }
.hdr-btns button.active { background:var(--accent); color:var(--bg); border-color:var(--accent); }
.controls { padding:10px 20px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; background:var(--surface); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:50; }
.controls button, .controls select, .controls input { padding:8px 13px; border-radius:6px; border:1px solid var(--border); background:var(--bg); color:var(--text); cursor:pointer; font-size:.85em; min-height:38px; }
.controls button:hover { background:var(--hover); }
.controls button.active { background:var(--accent); color:var(--bg); border-color:var(--accent); }
.search-wrap { position:relative; min-width:170px; }
.controls input { min-width:160px; width:100%; }
.ac-drop { position:absolute; top:42px; left:0; right:0; background:var(--surface); border:1px solid var(--border); border-radius:8px; box-shadow:0 8px 24px rgba(0,0,0,.35); z-index:60; overflow:hidden; }
.ac-drop:empty { display:none; }
.ac-item { padding:10px 12px; font-size:.85em; cursor:pointer; border-bottom:1px solid var(--border); }
.ac-item:last-child { border-bottom:none; }
.ac-item:hover { background:var(--hover); color:var(--accent); }
.content { padding:14px 20px; max-width:1400px; margin:0 auto; }
.view-tabs { display:flex; gap:6px; margin-bottom:12px; flex-wrap:wrap; }
.view-tab { padding:9px 16px; border-radius:6px; border:1px solid var(--border); cursor:pointer; font-size:.85em; background:var(--bg); color:var(--dim); min-height:40px; }
.view-tab.active { background:var(--accent); color:var(--bg); border-color:var(--accent); }
.day-tabs { display:flex; gap:6px; margin-bottom:14px; overflow-x:auto; padding-bottom:4px; }
.day-tab { padding:9px 16px; border-radius:6px; border:1px solid var(--border); cursor:pointer; font-size:.85em; background:var(--bg); color:var(--dim); white-space:nowrap; min-height:40px; }
.day-tab.active { background:var(--accent); color:var(--bg); border-color:var(--accent); }
table { width:100%; border-collapse:collapse; font-size:.88em; }
th { text-align:left; padding:10px 12px; border-bottom:2px solid var(--border); color:var(--dim); font-weight:500; position:sticky; top:0; background:var(--bg); }
td { padding:9px 12px; border-bottom:1px solid var(--border); }
tr:hover td { background:var(--hover); }
.name-btn { background:none; border:none; color:var(--accent); cursor:pointer; font-size:1em; text-align:left; padding:4px 0; text-decoration:underline dotted; }
.name-btn:hover { filter:brightness(1.3); }
.badge { padding:2px 8px; border-radius:10px; font-size:.75em; white-space:nowrap; }
.badge-morning { background:rgba(255,204,128,.15); color:var(--morning); }
.badge-afternoon { background:rgba(144,202,249,.15); color:var(--afternoon); }
.badge-transport { background:rgba(102,187,106,.15); color:var(--green); }
.chip { display:inline-block; padding:2px 8px; border-radius:10px; font-size:.72em; margin:1px 2px; white-space:nowrap; }
.chip-red { background:rgba(239,83,80,.18); color:var(--red); }
.chip-yellow { background:rgba(255,167,38,.18); color:var(--yellow); }
.chip-orange { background:rgba(255,112,67,.18); color:var(--orange); }
.chip-blue { background:rgba(100,181,246,.15); color:var(--blue); }
.chip-green { background:rgba(102,187,106,.15); color:var(--green); }
.summary-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:16px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:13px; }
.card .value { font-size:1.7em; font-weight:700; }
.card .label { font-size:.75em; color:var(--dim); margin-top:4px; }
.card.morning .value { color:var(--morning); }
.card.afternoon .value { color:var(--afternoon); }
.card.warn .value { color:var(--red); }
.loading { text-align:center; padding:40px; color:var(--dim); }
.error-box { text-align:center; padding:30px; color:var(--red); }
.error-box button { margin-top:10px; padding:8px 16px; border-radius:6px; border:1px solid var(--border); background:var(--surface); color:var(--text); cursor:pointer; }
.alert-banner { background:rgba(239,83,80,.12); border:1px solid var(--red); border-radius:8px; padding:10px 14px; margin-bottom:14px; font-size:.85em; cursor:pointer; }
.alert-banner .ab-head { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
.alert-banner .ab-body { margin-top:8px; display:none; }
.alert-banner.open .ab-body { display:block; }
.alert-item { padding:5px 0; border-top:1px solid var(--border); display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.sev-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.sev-critical { background:var(--red); }
.sev-warning { background:var(--yellow); }
.sev-watch { background:var(--blue); }
.bar-row { display:flex; align-items:center; gap:10px; margin-bottom:8px; font-size:.85em; }
.bar-label { width:160px; text-align:right; color:var(--dim); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { flex:1; background:var(--surface); border:1px solid var(--border); border-radius:4px; height:22px; overflow:hidden; }
.bar-fill { height:100%; background:var(--accent); opacity:.8; }
.bar-val { width:150px; font-size:.8em; color:var(--dim); }
.k-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }
.k-day { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:12px; text-align:center; }
.k-day .dl { font-size:.78em; color:var(--dim); }
.k-day .ct { font-size:1.5em; font-weight:700; margin:6px 0; }
.k-day .dt { font-size:.72em; color:var(--dim); }
.drv-group { background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:10px; padding:12px 14px; }
.drv-head { font-weight:600; color:var(--green); margin-bottom:6px; font-size:.92em; }
.drv-row { font-size:.82em; padding:5px 0; border-top:1px solid var(--border); }
.drv-row .ad { color:var(--dim); }
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.7); z-index:100; display:flex; align-items:center; justify-content:center; padding:20px; }
.modal { background:var(--surface); border:1px solid var(--border); border-radius:12px; max-width:880px; width:100%; max-height:90vh; overflow-y:auto; padding:22px; }
.modal h2 { color:var(--accent); font-size:1.25em; margin-bottom:4px; }
.modal .sub { color:var(--dim); font-size:.8em; margin-bottom:14px; }
.modal .close-x { float:right; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:6px; padding:6px 12px; cursor:pointer; font-size:.9em; }
.modal h3 { font-size:.95em; margin:16px 0 8px; border-bottom:1px solid var(--border); padding-bottom:5px; }
.wk-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:6px; }
.wk-cell { background:var(--bg); border:1px solid var(--border); border-radius:6px; padding:7px; min-height:64px; font-size:.72em; }
.wk-cell .d { color:var(--dim); font-size:.9em; margin-bottom:3px; }
.wk-cell .t { color:var(--morning); font-weight:600; }
.wk-cell.off { opacity:.35; }
.auth-row { background:var(--bg); border:1px solid var(--border); border-radius:6px; padding:9px 12px; margin-bottom:6px; font-size:.82em; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.auth-active { border-left:3px solid var(--green); }
.auth-other { border-left:3px solid var(--dim); opacity:.75; }
.route-row { font-size:.82em; padding:7px 10px; background:var(--bg); border:1px solid var(--border); border-radius:6px; margin-bottom:5px; }
.att-row { font-size:.8em; padding:5px 8px; border-bottom:1px solid var(--border); display:flex; gap:10px; flex-wrap:wrap; }
.att-ok { color:var(--green); }
.att-no { color:var(--yellow); }
@media(max-width:820px) {
  .header h1 { font-size:1.1em; }
  .controls { gap:6px; padding:8px 12px; }
  .controls button, .controls select, .controls input { font-size:.8em; padding:8px 10px; }
  .search-wrap { flex:1; min-width:130px; }
  .content { padding:10px 12px; }
  .summary-cards { grid-template-columns:repeat(2,1fr); }
  thead { display:none; }
  table.t-main, table.t-main tbody, table.t-main tr, table.t-main td { display:block; width:100%; }
  table.t-main tr { background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:8px; padding:6px 10px; }
  table.t-main tr:hover td { background:none; }
  table.t-main td { border:none; padding:4px 0; }
  table.t-main td::before { content:attr(data-l); color:var(--dim); font-size:.72em; display:inline-block; width:86px; }
  table.t-main td.no-l::before { content:none; }
  .wk-grid { grid-template-columns:repeat(4,1fr); }
  .modal-overlay { padding:0; }
  .modal { max-height:100vh; border-radius:0; padding:16px; }
  .bar-label { width:96px; font-size:.78em; }
  .bar-val { width:100px; }
}
@media print {
  .header, .controls, .day-tabs, .view-tabs, .summary-cards, .alert-banner, .modal-overlay { display:none !important; }
  body { background:#fff; color:#000; }
  .content { padding:0; max-width:none; }
  th { background:#fff; color:#333; }
  td, th { border-color:#999 !important; }
  .name-btn { color:#000; text-decoration:none; }
  .chip { border:1px solid #999; color:#000; background:none; }
  table { font-size:9.5pt; }
}
</style>
</head>
<body>

<nav style="background:#06060c;border-bottom:1px solid #1a1a2e;display:flex;align-items:center;overflow-x:auto;font-family:'SF Mono',monospace;">
  <a href="https://hermestigerclaw.com" style="color:#0ff;font-weight:700;font-size:0.72em;padding:8px 16px;text-decoration:none;letter-spacing:1px;border-right:1px solid #1a1a2e;">🐯 Tiger Claw</a>
  <a href="https://hub.hermestigerclaw.com/command" style="color:#6b7d99;font-size:0.68em;padding:8px 12px;text-decoration:none;">🧠 Command</a>
  <a href="https://rex.hermestigerclaw.com/goj-live/" style="color:#6b7d99;font-size:0.68em;padding:8px 12px;text-decoration:none;">🌿 GOJ Live</a>
  <a href="https://goj.hermestigerclaw.com" style="color:#6b7d99;font-size:0.68em;padding:8px 12px;text-decoration:none;">🌻 GOJ Ops</a>
  <a href="/schedule-hub/" style="color:#0ff;font-size:0.68em;padding:8px 12px;text-decoration:none;border-bottom:2px solid #0ff;">📋 Schedules</a>
  <a href="https://ui.hermestigerclaw.com" style="color:#6b7d99;font-size:0.68em;padding:8px 12px;text-decoration:none;">🤖 WebUI</a>
  <a href="https://chat.hermestigerclaw.com" style="color:#6b7d99;font-size:0.68em;padding:8px 12px;text-decoration:none;">💬 Chat</a>
</nav>

<div class="header">
  <h1>📋 GHS Schedule Hub</h1>
  <div class="hdr-btns">
    <button id="wk30" onclick="setWeek(30)">This Week</button>
    <button id="wk31" class="active" onclick="setWeek(31)">Next Week</button>
    <button id="themeBtn" onclick="toggleTheme()" title="Toggle theme">🌓</button>
  </div>
  <div class="stats" id="headerStats"></div>
</div>

<div class="controls">
  <select id="shiftFilter" onchange="loadDay()">
    <option value="">All Shifts</option>
    <option value="MORNING">☀️ Morning</option>
    <option value="AFTERNOON">🌤️ Afternoon</option>
  </select>
  <button id="transportBtn" onclick="toggleTransport()">🚗 Transport</button>
  <button id="issuesBtn" onclick="toggleIssues()">⚠️ Issues</button>
  <div class="search-wrap">
    <input type="text" id="searchInput" placeholder="🔍 Search client..." autocomplete="off">
    <div class="ac-drop" id="acDrop"></div>
  </div>
  <button onclick="exportCSV()">📥 CSV</button>
  <button onclick="exportDayPDF()">📄 Day PDF</button>
  <button onclick="exportWeeklyPDF()">📦 Weekly Pack</button>
  <button onclick="window.print()">🖨️</button>
</div>

<div class="content">
  <div class="view-tabs" id="viewTabs"></div>
  <div id="alertHost"></div>
  <div class="day-tabs" id="dayTabs"></div>
  <div class="summary-cards" id="summaryCards"></div>
  <div id="tableContainer"><div class="loading">Loading…</div></div>
</div>

<div id="modalHost"></div>

<script>
const DAYS = ['sun','mon','tue','wed','thu','fri','sat'];
const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const VIEWS = [['signin','📝 Sign-in'],['payers','💳 Payers'],['kitchen','🍽️ Kitchen'],['drivers','🚗 Drivers']];
let state = { day: DAYS[new Date().getDay()], week: 31, view: 'signin', transport: false, issues: false };
let debounceT = null, acT = null;

function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('ghs-theme', t); } catch(e) {}
}
function toggleTheme() {
  applyTheme(document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light');
}
try { applyTheme(localStorage.getItem('ghs-theme') || 'dark'); } catch(e) {}

async function jfetch(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
function chipHTML(f) { return `<span class="chip chip-${f.sev}">${f.label}</span>`; }
function esc(s) { return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

async function init() {
  renderWeekToggle(); renderViewTabs(); renderDayTabs();
  bindSearch();
  await Promise.all([loadDay(), loadSummary(), loadAlerts()]);
}

function renderWeekToggle() {
  document.getElementById('wk30').classList.toggle('active', state.week===30);
  document.getElementById('wk31').classList.toggle('active', state.week===31);
}
function renderViewTabs() {
  document.getElementById('viewTabs').innerHTML = VIEWS.map(([v,l]) =>
    `<span class="view-tab${v===state.view?' active':''}" onclick="setView('${v}')">${l}</span>`).join('');
}
function renderDayTabs() {
  document.getElementById('dayTabs').innerHTML = DAYS.map((d,i) =>
    `<span class="day-tab${d===state.day?' active':''}" onclick="switchDay('${d}',this)">${DAY_NAMES[i]}</span>`).join('');
}

async function setWeek(w) { state.week = w; renderWeekToggle(); await loadView(); }
async function setView(v) { state.view = v; renderViewTabs(); await loadView(); }
async function switchDay(day, el) {
  state.day = day;
  document.querySelectorAll('.day-tab').forEach((t,i) => t.classList.toggle('active', DAYS[i]===day));
  await loadView();
}
async function toggleTransport() {
  state.transport = !state.transport;
  document.getElementById('transportBtn').classList.toggle('active', state.transport);
  await loadDay();
}
async function toggleIssues() {
  state.issues = !state.issues;
  document.getElementById('issuesBtn').classList.toggle('active', state.issues);
  await loadDay();
}

async function loadView() {
  document.getElementById('dayTabs').style.display =
    (state.view === 'signin' || state.view === 'drivers') ? '' : 'none';
  if (state.view === 'signin') return loadDay();
  if (state.view === 'payers') return loadPayers();
  if (state.view === 'kitchen') return loadKitchen();
  if (state.view === 'drivers') return loadDrivers();
}

async function loadDay() {
  const el = document.getElementById('tableContainer');
  el.innerHTML = '<div class="loading">Loading…</div>';
  const shift = document.getElementById('shiftFilter').value;
  const search = document.getElementById('searchInput').value.trim();
  try {
    if (search.length >= 2) {
      const data = await jfetch(`/schedule-hub/api/search?q=${encodeURIComponent(search)}&week=${state.week}`);
      return renderSearchResults(data);
    }
    let url = `/schedule-hub/api/signin?day=${state.day}&week=${state.week}`;
    if (shift) url += `&shift=${shift}`;
    if (state.transport) url += '&transport_only=true';
    if (state.issues) url += '&issues_only=true';
    renderSignIn(await jfetch(url));
  } catch(e) {
    el.innerHTML = `<div class="error-box">Failed to load — ${esc(e.message)}<br><button onclick="loadDay()">↻ Retry</button></div>`;
  }
}

function renderSignIn(data) {
  const clients = data.clients || [];
  let html = `<table class="t-main"><thead><tr>
    <th>#</th><th>Client</th><th>Time</th><th>Payer</th><th>TR</th><th>Auth Exp</th><th>Flags</th>
  </tr></thead><tbody>`;
  clients.forEach((c,i) => {
    const sb = c.shift === 'MORNING' ? 'badge-morning' : 'badge-afternoon';
    html += `<tr>
      <td class="no-l">${i+1}</td>
      <td data-l="Client"><button class="name-btn" onclick="openClient(${c.client_id})">${esc(c.name)}</button></td>
      <td data-l="Time"><span class="badge ${sb}">${esc(c.time)}</span></td>
      <td data-l="Payer">${esc(c.payer)||'?'}</td>
      <td data-l="TR">${c.transport ? '<span class="badge badge-transport">🚗</span>' : '—'}</td>
      <td data-l="Auth Exp">${c.auth_expires || '—'}</td>
      <td data-l="Flags">${(c.flag_objs||[]).map(chipHTML).join('')}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  if (!clients.length) html = '<div class="loading">No clients for this filter.</div>';
  document.getElementById('tableContainer').innerHTML = html;
  document.getElementById('summaryCards').innerHTML = `
    <div class="card morning"><div class="value">${data.morning||0}</div><div class="label">☀️ Morning</div></div>
    <div class="card afternoon"><div class="value">${data.afternoon||0}</div><div class="label">🌤️ Afternoon</div></div>
    <div class="card"><div class="value">${data.total||0}</div><div class="label">Total ${data.day||''} · ${data.day_date||''}</div></div>
    <div class="card warn"><div class="value">${data.issues||0}</div><div class="label">⚠️ Auth/Payer Issues</div></div>`;
}

function renderSearchResults(data) {
  const results = data.results || [];
  let html = `<table class="t-main"><thead><tr><th>Client</th><th>Day</th><th>Time</th><th>Payer</th></tr></thead><tbody>`;
  results.forEach(r => {
    html += `<tr>
      <td data-l="Client"><button class="name-btn" onclick="openClient(${r.client_id})">${esc(r.full_name)}</button></td>
      <td data-l="Day">${r.day_name||'—'}</td>
      <td data-l="Time">${r.time_slot||'no schedule'}</td>
      <td data-l="Payer">${r.payer||'?'}</td></tr>`;
  });
  html += '</tbody></table>';
  if (!results.length) html = '<div class="loading">No matches.</div>';
  document.getElementById('tableContainer').innerHTML = html;
  document.getElementById('summaryCards').innerHTML =
    `<div class="card"><div class="value">${results.length}</div><div class="label">Search results</div></div>`;
}

async function loadPayers() {
  const el = document.getElementById('tableContainer');
  el.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const d = await jfetch(`/schedule-hub/api/analytics/payers?week=${state.week}`);
    const max = Math.max(...d.payers.map(p => p.clients), 1);
    let html = '';
    d.payers.forEach(p => {
      const pct = Math.round(100*p.clients/max);
      const authPct = p.clients ? Math.round(100*p.with_auth/p.clients) : 0;
      html += `<div class="bar-row">
        <div class="bar-label" title="${esc(p.payer)}">${esc(p.payer)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-val">${p.clients} clients · ${authPct}% auth${p.expiring?` · <span style="color:var(--yellow)">${p.expiring} exp</span>`:''}</div>
      </div>`;
    });
    html += `<table style="margin-top:18px"><thead><tr><th>Payer</th><th>Clients</th><th>Sched rows</th><th>Transport</th><th>With auth</th><th>No auth</th><th>Expiring</th></tr></thead><tbody>`;
    d.payers.forEach(p => {
      html += `<tr><td>${esc(p.payer)}</td><td>${p.clients}</td><td>${p.schedule_rows}</td><td>${p.transport_rows}</td>
        <td>${p.with_auth}</td><td style="color:${p.no_auth?'var(--red)':'inherit'}">${p.no_auth}</td>
        <td style="color:${p.expiring?'var(--yellow)':'inherit'}">${p.expiring}</td></tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
    document.getElementById('summaryCards').innerHTML =
      `<div class="card"><div class="value">${d.total_clients}</div><div class="label">Clients w/ schedules</div></div>
       <div class="card"><div class="value">${d.payers.length}</div><div class="label">Payers</div></div>`;
  } catch(e) {
    el.innerHTML = `<div class="error-box">Failed — ${esc(e.message)}<br><button onclick="loadPayers()">↻ Retry</button></div>`;
  }
}

async function loadKitchen() {
  const el = document.getElementById('tableContainer');
  el.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const d = await jfetch(`/schedule-hub/api/kitchen?week=${state.week}`);
    const byDay = {};
    d.counts.forEach(c => { (byDay[c.day] = byDay[c.day] || {})[c.shift] = c.meal_count; });
    let html = '<div class="k-grid">';
    ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(day => {
      const v = byDay[day];
      if (!v) return;
      const total = Object.values(v).reduce((a,b)=>a+b,0);
      html += `<div class="k-day"><div class="dl">${day}</div><div class="ct">${total}</div>
        <div class="dt">☀ ${v.MORNING||0} · 🌤 ${v.AFTERNOON||0}</div></div>`;
    });
    html += '</div>';
    el.innerHTML = html;
    document.getElementById('summaryCards').innerHTML =
      `<div class="card"><div class="value">${d.counts.reduce((a,c)=>a+c.meal_count,0)}</div><div class="label">Meals this week</div></div>`;
  } catch(e) {
    el.innerHTML = `<div class="error-box">Failed — ${esc(e.message)}<br><button onclick="loadKitchen()">↻ Retry</button></div>`;
  }
}

async function loadDrivers() {
  const el = document.getElementById('tableContainer');
  el.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const d = await jfetch(`/schedule-hub/api/driver-list?day=${state.day}`);
    let html = '';
    Object.entries(d.drivers).forEach(([drv, rows]) => {
      html += `<div class="drv-group"><div class="drv-head">🚗 ${esc(drv)} — ${rows.length} clients</div>`;
      rows.forEach(r => {
        html += `<div class="drv-row"><b>${esc(r.client_name)}</b> <span style="color:var(--dim)">${r.shift}</span><br>
          <span class="ad">${esc(r.client_address)||''} ${r.client_phone?'· '+esc(r.client_phone):''}</span></div>`;
      });
      html += '</div>';
    });
    if (!html) html = '<div class="loading">No route assignments for this day.</div>';
    el.innerHTML = html;
    document.getElementById('summaryCards').innerHTML =
      `<div class="card"><div class="value">${d.total_clients}</div><div class="label">Route clients ${state.day.toUpperCase()}</div></div>
       <div class="card"><div class="value">${Object.keys(d.drivers).length}</div><div class="label">Drivers</div></div>`;
  } catch(e) {
    el.innerHTML = `<div class="error-box">Failed — ${esc(e.message)}<br><button onclick="loadDrivers()">↻ Retry</button></div>`;
  }
}

async function loadSummary() {
  try {
    const d = await jfetch('/schedule-hub/api/summary');
    const stale = d.db_age_hours != null && d.db_age_hours > 168;
    document.getElementById('headerStats').innerHTML =
      `${d.total_clients} clients · Next Mon: ${d.next_monday} · ` +
      `<span style="color:var(--red)">${d.auth_gaps} no-auth Mon</span> · ` +
      `<span style="color:var(--yellow)">${d.auth_expiring} expiring</span> · ` +
      `<span style="color:${stale?'var(--red)':'var(--dim)'}">data ${d.db_age_hours}h old</span>`;
  } catch(e) {}
}

async function loadAlerts() {
  try {
    const d = await jfetch('/schedule-hub/api/auth-alerts');
    const host = document.getElementById('alertHost');
    if (!d.total) { host.innerHTML = ''; return; }
    const items = d.alerts.map(a => `
      <div class="alert-item">
        <span class="sev-dot sev-${a.severity}"></span>
        <button class="name-btn" onclick="openClient(${a.client_id})">${esc(a.name)}</button>
        <span>${esc(a.payer)||''}</span>
        <span style="color:var(--dim)">ends ${a.service_end} (${a.days_left}d)</span>
      </div>`).join('');
    host.innerHTML = `<div class="alert-banner${d.critical?' open':''}" onclick="this.classList.toggle('open')">
      <div class="ab-head"><span>⚠️ <b>${d.total}</b> auths expiring — <span style="color:var(--red)">${d.critical} critical</span> · ${d.warning} warning · ${d.watch} watch</span>
      <span style="color:var(--dim)">click to expand</span></div>
      <div class="ab-body">${items}</div></div>`;
  } catch(e) {}
}

function bindSearch() {
  const inp = document.getElementById('searchInput');
  const drop = document.getElementById('acDrop');
  inp.addEventListener('input', () => {
    clearTimeout(debounceT); clearTimeout(acT);
    const q = inp.value.trim();
    if (q.length < 2) { drop.innerHTML=''; debounceT = setTimeout(loadDay, 250); return; }
    acT = setTimeout(async () => {
      try {
        const d = await jfetch(`/schedule-hub/api/clients/lookup?q=${encodeURIComponent(q)}`);
        drop.innerHTML = d.results.map(r =>
          `<div class="ac-item" onclick="pickClient(${r.id})">${esc(r.name)}</div>`).join('');
      } catch(e) { drop.innerHTML=''; }
    }, 180);
    debounceT = setTimeout(() => { drop.innerHTML=''; loadDay(); }, 700);
  });
  inp.addEventListener('keydown', e => { if (e.key === 'Escape') { drop.innerHTML=''; inp.value=''; loadDay(); } });
  document.addEventListener('click', e => { if (!e.target.closest('.search-wrap')) drop.innerHTML=''; });
}
function pickClient(id) {
  document.getElementById('acDrop').innerHTML = '';
  openClient(id);
}

async function openClient(id) {
  let c;
  try { c = await jfetch(`/schedule-hub/api/client/${id}`); } catch(e) { return; }

  const gridHTML = (wkdata, label) => `
    <h3>${label} <span style="color:var(--dim);font-weight:400">${wkdata.start} → ${wkdata.end}</span></h3>
    <div class="wk-grid">
      ${DAYS.map(d => {
        const cell = wkdata.days[d];
        if (!cell) return `<div class="wk-cell off"><div class="d">${d.toUpperCase()}</div>—</div>`;
        return `<div class="wk-cell"><div class="d">${d.toUpperCase()}</div>
          <div class="t">${esc(cell.time)}</div>
          <div>${esc(cell.payer)||'?'} ${cell.transport?'🚗':''}</div>
          <div style="margin-top:2px">${cell.flags.join(' ')}</div></div>`;
      }).join('')}
    </div>`;

  const authHTML = c.authorizations.length ? c.authorizations.map(a => `
    <div class="auth-row ${a.status==='ACTIVE'?'auth-active':'auth-other'}">
      <span style="font-weight:600">${esc(a.payer)||'Unknown payer'}</span>
      <span>Auth: ${esc(a.auth_number)||'—'}</span>
      <span>${a.service_start||'?'} → <b>${a.service_end||'?'}</b></span>
      <span>${a.status}</span>
    </div>`).join('') : '<div style="color:var(--red);font-size:.85em">🔴 No authorization on file — client attends, submit auth ASAP.</div>';

  const routeHTML = c.transport_routes.length ? c.transport_routes.map(t => `
    <div class="route-row">🚗 <b>${t.day_of_week.toUpperCase()}</b> ${t.shift} · Driver: <b>${esc(t.driver_name)}</b>${t.driver_phone?' · '+esc(t.driver_phone):''}<br>
    <span style="color:var(--dim)">${esc(t.client_address)||''} ${t.client_phone?'· '+esc(t.client_phone):''}</span></div>`).join('')
    : '<div style="color:var(--dim);font-size:.85em">No route assignment on file.</div>';

  document.getElementById('modalHost').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <button class="close-x" onclick="closeModal()">✕ Close</button>
        <h2>${esc(c.full_name)}</h2>
        <div class="sub">Carecenta ID ${c.carecenta_id} · ${c.status} · ${c.overall_flags.join(' ')}</div>
        ${gridHTML(c.weeks['31'], 'Next Week')}
        ${gridHTML(c.weeks['30'], 'This Week')}
        <h3>Authorizations (${c.authorizations.length})</h3>
        ${authHTML}
        <h3>Transport / Routes</h3>
        ${routeHTML}
        <h3>Attendance History <span style="color:var(--dim);font-weight:400" id="attSub">loading…</span></h3>
        <div id="attHost"><div class="loading" style="padding:12px">…</div></div>
      </div>
    </div>`;
  document.body.style.overflow = 'hidden';
  loadAttendance(id);
}

async function loadAttendance(id) {
  try {
    const d = await jfetch(`/schedule-hub/api/client/${id}/attendance?limit=40`);
    document.getElementById('attSub').textContent =
      `${d.records} records · ${d.attended} attended · ${d.other} other`;
    document.getElementById('attHost').innerHTML = d.history.length ? d.history.map(h => {
      const ok = (h.status||'').toLowerCase();
      const cls = (ok==='attended'||ok==='present') ? 'att-ok' : 'att-no';
      return `<div class="att-row"><span style="width:92px;color:var(--dim)">${h.log_date}</span>
        <span class="${cls}">${esc(h.status)}</span>
        <span style="color:var(--dim)">S${h.shift} · ${esc(h.source||'')}</span>
        <span>${esc(h.note||'')}</span></div>`;
    }).join('') : '<div style="color:var(--dim);font-size:.85em">No attendance records found.</div>';
  } catch(e) {
    const ah = document.getElementById('attHost');
    if (ah) ah.innerHTML = '<div style="color:var(--dim);font-size:.85em">Attendance unavailable.</div>';
  }
}

function closeModal() {
  document.getElementById('modalHost').innerHTML = '';
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

function exportCSV() { window.open(`/schedule-hub/api/export/signin?day=${state.day}&week=${state.week}&format=csv`); }
function exportDayPDF() { window.open(`/schedule-hub/api/export/daily-pdf?day=${state.day}&week=${state.week}`); }
function exportWeeklyPDF() { window.open(`/schedule-hub/api/export/weekly-pack?week=${state.week}`); }

init();
</script>
</body>
</html>
""")


@router.get("/health")
async def health():
    return {"status": "ok", "db": str(SCHEDULE_DB), "db_exists": SCHEDULE_DB.exists()}
