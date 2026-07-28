"""
CC_schedule_hub.py — GHS Schedule Hub: Carecenta-powered operations dashboard
=============================================================================
FastAPI router serving the complete schedule ecosystem from ghs_schedule.db.
Mounts to REX at /schedule-hub.

Phase B (2026-07-24):
  • Client detail cards (click name → full profile modal)
  • Auth status indicators (shared flag engine: NO AUTH / EXPIRING /
    PAYER MISMATCH / NO TRANSPORT / CLEAN)
  • Mobile-responsive layout (cards < 820px, sticky controls)
  • Bulk PDF generation: per-day pack + full weekly pack
    (sign-in 7-col template + driver routes + kitchen count)
  • Week toggle (current week 30 / next week 31 — rolling convention,
    see carecenta_weekly_refresh.py)

Legacy features preserved:
  • Daily sign-in sheets, day tabs, shift/transport/payer filters
  • Driver list, kitchen counts, weekly grid, CSV/TXT export, search
"""
from __future__ import annotations

import io
import re
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule-hub", tags=["Schedule Hub"])

# ── Config ──────────────────────────────────────────────────────────────────
SCHEDULE_DB = Path.home() / "Desktop" / "REX" / "signin_lists" / "ghs_schedule.db"
PDF_OUT_DIR = Path.home() / "Desktop" / "REX" / "signin_lists" / "daily_packs"
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_CODES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
SHIFT_ORDER = {"MORNING": 0, "AFTERNOON": 1, "FULL_DAY": 2, "OTHER": 3}

# Rolling week convention: DB week 30 = CURRENT week, 31 = NEXT week.
# week_bounds is DYNAMIC — anchored to the current calendar week's Sunday —
# so it always agrees with what carecenta_weekly_refresh.py stores (current→30,
# next→31) no matter when the last refresh ran.

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

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_db():
    """Get a connection to the schedule database."""
    conn = sqlite3.connect(str(SCHEDULE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def current_sunday() -> date:
    """Sunday of the current calendar week (GOJ weeks run Sun-Sat)."""
    today = date.today()
    return today - timedelta(days=today.isoweekday() % 7)


def week_bounds(week: int) -> tuple[date, date]:
    """Return (sunday, saturday) for a DB week number. Rolling: 30=current, 31=next."""
    sunday = current_sunday() + timedelta(days=(week - 30) * 7)
    return sunday, sunday + timedelta(days=6)


def get_today_day_code() -> str:
    """Return today's day code (sun..sat). isoweekday: Mon=1..Sun=7 → %7 gives Sun=0."""
    return DAY_CODES[datetime.now().isoweekday() % 7]


def get_monday_date() -> str:
    """Return next Monday's date."""
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return (today + timedelta(days=days_until_monday)).isoformat()


def norm_payer(p: Optional[str]) -> str:
    """Normalize payer for comparison: uppercase, alnum only."""
    return re.sub(r"[^A-Z0-9]", "", (p or "").upper())


def payers_match(a: Optional[str], b: Optional[str]) -> bool:
    """Fuzzy payer match — handles 'ANTHEM HP' vs 'ANTHEM HP, LLC', 'AETNA' vs 'AETNA transport'."""
    na, nb = norm_payer(a), norm_payer(b)
    if not na or not nb or na == "UNKNOWN" or nb == "UNKNOWN":
        return True  # can't verify → don't flag
    return na.startswith(nb) or nb.startswith(na) or na[:6] == nb[:6]


def compute_flags(sched_payer, has_transport, auths, week_sat: date) -> list[dict]:
    """
    Shared flag engine (flags.md spec).
    auths: list of dicts with payer/service_end/status for the client.
    EXPIRING threshold: auth ends before (viewed week's Saturday + 14 days)
    — for week 31 that is 2026-08-15, matching the established convention.
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
    """Fetch ACTIVE/PENDING auths for many clients in one query."""
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


def name_key(first: str, last: str) -> str:
    """Order-insensitive alpha-token key. clients store 'Last, First <id>' and
    driver_routes.client_name is 'Last First' — sorted tokens match both."""
    return " ".join(sorted(re.findall(r"[a-z]+", f"{first} {last}".lower())))


def routes_by_client(db) -> dict[str, list[dict]]:
    """All driver routes keyed by normalized client-name token set."""
    rows = db.execute(
        """SELECT day_of_week, shift, client_name, client_address, client_phone,
                  driver_name, driver_phone FROM driver_routes"""
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        k = " ".join(sorted(re.findall(r"[a-z]+", (r["client_name"] or "").lower())))
        out.setdefault(k, []).append(dict(r))
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


# ── API Endpoints ────────────────────────────────────────────────────────────

@router.get("/api/signin")
async def api_signin(
    day: str = Query(default=None, description="Day code: mon, tue, wed, etc."),
    week: int = Query(default=31, description="Week number: 30 (current) or 31 (next)"),
    shift: Optional[str] = Query(default=None, description="MORNING or AFTERNOON"),
    transport_only: bool = Query(default=False),
    issues_only: bool = Query(default=False),
    payer: Optional[str] = Query(default=None),
):
    """Get sign-in list for a specific day, with full flag engine."""
    if day is None:
        day = get_today_day_code()
    day_idx = DAY_CODES.index(day)

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
        "day_code": day,
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

    key = name_key(c["first_name"], c["last_name"])
    routes = routes_by_client(db).get(key, [])
    db.close()

    # Build per-week day grids with flags
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

    # Overall flag state (based on next week)
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


@router.get("/api/weekly")
async def api_weekly(week: int = Query(default=31)):
    """Get full weekly overview grid."""
    db = get_db()
    rows = db.execute("SELECT * FROM v_weekly").fetchall()
    db.close()
    sunday, saturday = week_bounds(week)
    return {"week": week, "week_start": sunday.isoformat(),
            "week_end": saturday.isoformat(), "clients": [dict(r) for r in rows]}


@router.get("/api/kitchen")
async def api_kitchen(week: int = Query(default=31)):
    """Get kitchen meal counts."""
    db = get_db()
    rows = db.execute("SELECT * FROM v_kitchen").fetchall()
    db.close()
    return {"week": week, "counts": [dict(r) for r in rows]}


@router.get("/api/drivers")
async def api_drivers(day: Optional[str] = Query(default=None),
                      week: int = Query(default=31)):
    """Get driver list (transport-authorized clients)."""
    db = get_db()
    if day:
        day_idx = DAY_CODES.index(day)
        rows = db.execute(
            """SELECT c.id AS client_id, c.full_name, s.time_slot, s.shift, s.payer
               FROM schedule s JOIN clients c ON c.id = s.client_id
               WHERE s.week_number = ? AND s.day_of_week = ?
               AND s.has_transport = 1 AND s.is_cancelled = 0
               ORDER BY s.shift, c.last_name""",
            (week, day_idx),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM v_drivers WHERE week_number = ?", (week,)).fetchall()
    db.close()
    return {"day": day, "clients": [dict(r) for r in rows]}


@router.get("/api/driver-list")
async def api_driver_list(day: Optional[str] = Query(default=None)):
    """Get full driver list with transport assignments (from Drive TR tabs)."""
    db = get_db()
    if day:
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
        d = r.get("driver_name") or "UNASSIGNED"
        drivers.setdefault(d, []).append(r)

    return {"day": day, "total_clients": len(rows), "drivers": drivers}


@router.get("/api/search")
async def api_search(q: str = Query(..., min_length=2), week: int = Query(default=31)):
    """Search clients by name."""
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT c.id AS client_id, c.full_name, s.day_name, s.time_slot, s.shift, s.payer
           FROM schedule s JOIN clients c ON c.id = s.client_id
           WHERE s.week_number = ? AND c.full_name LIKE ?
           ORDER BY s.day_of_week, s.shift""",
        (week, f"%{q}%"),
    ).fetchall()
    # Also match clients with no schedule this week
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


@router.get("/api/summary")
async def api_summary():
    """Get daily attendance summary for next week."""
    db = get_db()
    rows = db.execute("SELECT * FROM v_daily_summary").fetchall()
    gaps = db.execute(
        "SELECT COUNT(DISTINCT full_name) FROM v_auth_gaps WHERE day_name = 'MON'"
    ).fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    db.close()

    sunday, _ = week_bounds(31)
    expiring = 0
    db = get_db()
    threshold = (sunday + timedelta(days=6 + 14)).isoformat()
    expiring = db.execute(
        "SELECT COUNT(DISTINCT client_id) FROM authorizations WHERE status='ACTIVE' AND service_end < ?",
        (threshold,),
    ).fetchone()[0]
    db.close()

    return {
        "total_clients": total,
        "auth_gaps": gaps,
        "auth_expiring": expiring,
        "daily": [dict(r) for r in rows],
        "next_monday": get_monday_date(),
    }


@router.get("/api/export/signin")
async def export_signin(day: str = Query(default="mon"),
                        week: int = Query(default=31),
                        format: str = Query(default="csv")):
    """Export sign-in sheet as CSV or plain text."""
    day_idx = DAY_CODES.index(day)
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


# ── PDF Generation ───────────────────────────────────────────────────────────

PDF_OUT_DIR.mkdir(parents=True, exist_ok=True)

CELL = ParagraphStyle("cell", fontSize=11, fontName=FONT_REG, leading=13, alignment=TA_LEFT)
CELL_B = ParagraphStyle("cellb", fontSize=11, fontName=FONT_BOLD, leading=13, alignment=TA_LEFT)
TITLE = ParagraphStyle("title", fontSize=14, fontName=FONT_BOLD, alignment=TA_CENTER, spaceAfter=6)
SUB = ParagraphStyle("sub", fontSize=12, fontName=FONT_REG, alignment=TA_CENTER, spaceAfter=8)
SECT = ParagraphStyle("sect", fontSize=13, fontName=FONT_BOLD, alignment=TA_LEFT,
                      textColor=colors.HexColor("#204080"), spaceAfter=4)


def _pdf_flag_text(row: dict) -> str:
    """Text-only flags for PDF (DejaVu has no emoji glyphs). CLEAN omitted."""
    out = []
    for f in row["flag_objs"]:
        if f["code"] == "CLEAN":
            continue
        out.append(f"[{f['code'].replace('_', ' ')}]")
    return " ".join(out)


def _signin_pages(story, week: int, day_idx: int, rows: list[dict]):
    """Sign-in sheet section: 7-col template (No|Name|Plan|TR|Time In|Time Out|Signature)."""
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
    """Driver route section from driver_routes (Drive TR tab assignments)."""
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
    """Kitchen meal-count section (counts from schedule — menus live in goj_proprietary.db)."""
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
    """Build a multi-day (or single-day) operations pack PDF."""
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
    day_idx = DAY_CODES.index(day)
    out = _build_pack_pdf([day_idx], week)
    return FileResponse(str(out), media_type="application/pdf", filename=out.name)


@router.get("/api/export/weekly-pack")
async def export_weekly_pack(week: int = Query(default=31)):
    """Bulk PDF: every day's sign-in + driver + kitchen sheets in one file."""
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
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>GHS Schedule Hub — DataRex</title>
<style>
:root {
  --bg: #0a0a0f; --surface: #141420; --border: #252540;
  --text: #e0e0e0; --dim: #888; --accent: #4fc3f7;
  --green: #66bb6a; --red: #ef5350; --yellow: #ffa726;
  --orange: #ff7043; --blue: #64b5f6;
  --morning: #ffcc80; --afternoon: #90caf9;
}
* { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,sans-serif; }
.header { background:var(--surface); border-bottom:1px solid var(--border); padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; }
.header h1 { font-size:1.3em; color:var(--accent); }
.header .stats { display:flex; gap:16px; font-size:.82em; color:var(--dim); flex-wrap:wrap; }
.week-toggle { display:flex; gap:4px; }
.week-toggle button { padding:7px 12px; border-radius:6px; border:1px solid var(--border); background:var(--bg); color:var(--dim); cursor:pointer; font-size:.8em; min-height:36px; }
.week-toggle button.active { background:var(--accent); color:#000; border-color:var(--accent); }
.controls { padding:10px 20px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; background:var(--surface); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:50; }
.controls button, .controls select, .controls input { padding:8px 13px; border-radius:6px; border:1px solid var(--border); background:var(--bg); color:var(--text); cursor:pointer; font-size:.85em; min-height:38px; }
.controls button:hover { background:#252540; }
.controls button.active { background:var(--accent); color:#000; border-color:var(--accent); }
.controls input { min-width:150px; }
.content { padding:14px 20px; }
.day-tabs { display:flex; gap:6px; margin-bottom:14px; overflow-x:auto; padding-bottom:4px; }
.day-tab { padding:9px 16px; border-radius:6px; border:1px solid var(--border); cursor:pointer; font-size:.85em; background:var(--bg); color:var(--dim); white-space:nowrap; min-height:40px; }
.day-tab:hover { border-color:var(--accent); color:var(--text); }
.day-tab.active { background:var(--accent); color:#000; border-color:var(--accent); }
.day-tab .cnt { font-size:.75em; opacity:.75; margin-left:4px; }
table { width:100%; border-collapse:collapse; font-size:.88em; }
th { text-align:left; padding:10px 12px; border-bottom:2px solid var(--border); color:var(--dim); font-weight:500; position:sticky; top:0; background:var(--bg); }
td { padding:9px 12px; border-bottom:1px solid var(--border); }
tr:hover td { background:rgba(79,195,247,.05); }
.name-btn { background:none; border:none; color:var(--accent); cursor:pointer; font-size:1em; text-align:left; padding:4px 0; text-decoration:underline dotted; }
.name-btn:hover { color:#fff; }
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
/* ── Client modal ── */
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.7); z-index:100; display:flex; align-items:center; justify-content:center; padding:20px; }
.modal { background:var(--surface); border:1px solid var(--border); border-radius:12px; max-width:860px; width:100%; max-height:90vh; overflow-y:auto; padding:22px; }
.modal h2 { color:var(--accent); font-size:1.25em; margin-bottom:4px; }
.modal .sub { color:var(--dim); font-size:.8em; margin-bottom:14px; }
.modal .close-x { float:right; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:6px; padding:6px 12px; cursor:pointer; font-size:.9em; }
.modal h3 { font-size:.95em; color:var(--text); margin:16px 0 8px; border-bottom:1px solid var(--border); padding-bottom:5px; }
.wk-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:6px; }
.wk-cell { background:var(--bg); border:1px solid var(--border); border-radius:6px; padding:7px; min-height:64px; font-size:.72em; }
.wk-cell .d { color:var(--dim); font-size:.9em; margin-bottom:3px; }
.wk-cell .t { color:var(--morning); font-weight:600; }
.wk-cell.off { opacity:.35; }
.auth-row { background:var(--bg); border:1px solid var(--border); border-radius:6px; padding:9px 12px; margin-bottom:6px; font-size:.82em; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.auth-row .pn { font-weight:600; }
.auth-active { border-left:3px solid var(--green); }
.auth-other { border-left:3px solid var(--dim); opacity:.75; }
.route-row { font-size:.82em; padding:7px 10px; background:var(--bg); border:1px solid var(--border); border-radius:6px; margin-bottom:5px; }
/* ── Mobile ── */
@media(max-width:820px) {
  .header h1 { font-size:1.1em; }
  .controls { gap:6px; padding:8px 12px; }
  .controls button, .controls select, .controls input { font-size:.8em; padding:8px 10px; }
  .controls input { flex:1; min-width:110px; }
  .content { padding:10px 12px; }
  .summary-cards { grid-template-columns:repeat(2,1fr); }
  thead { display:none; }
  table, tbody, tr, td { display:block; width:100%; }
  tr { background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:8px; padding:6px 10px; }
  tr:hover td { background:none; }
  td { border:none; padding:4px 0; }
  td::before { content:attr(data-l); color:var(--dim); font-size:.72em; display:inline-block; width:86px; }
  td.no-l::before { content:none; }
  .wk-grid { grid-template-columns:repeat(4,1fr); }
  .modal-overlay { padding:0; }
  .modal { max-height:100vh; border-radius:0; padding:16px; }
}
</style>
</head>
<body>

<div class="header">
  <h1>📋 GHS Schedule Hub</h1>
  <div class="week-toggle" id="weekToggle"></div>
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
  <input type="text" id="searchInput" placeholder="🔍 Search client..." oninput="debouncedLoad()">
  <button onclick="exportCSV()">📥 CSV</button>
  <button onclick="exportDayPDF()">📄 Day PDF</button>
  <button onclick="exportWeeklyPDF()">📦 Weekly Pack</button>
</div>

<div class="content">
  <div class="day-tabs" id="dayTabs"></div>
  <div class="summary-cards" id="summaryCards"></div>
  <div id="tableContainer"><div class="loading">Loading...</div></div>
</div>

<div id="modalHost"></div>

<script>
const DAYS = ['sun','mon','tue','wed','thu','fri','sat'];
const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
let state = { day: null, week: 31, transport: false, issues: false };
let debounceT = null;

function todayCode() {
  // JS getDay(): Sun=0..Sat=6 — matches DAY_CODES
  return DAYS[new Date().getDay()];
}

async function init() {
  state.day = todayCode();
  renderWeekToggle();
  await loadDay();
  await loadSummary();
}

function renderWeekToggle() {
  document.getElementById('weekToggle').innerHTML =
    `<button class="${state.week===30?'active':''}" onclick="setWeek(30)">This Week</button>` +
    `<button class="${state.week===31?'active':''}" onclick="setWeek(31)">Next Week</button>`;
}

async function setWeek(w) {
  state.week = w;
  renderWeekToggle();
  await loadDay();
}

function debouncedLoad() {
  clearTimeout(debounceT);
  debounceT = setTimeout(loadDay, 250);
}

async function switchDay(day, el) {
  state.day = day;
  document.querySelectorAll('.day-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  await loadDay();
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

function chipHTML(f) {
  return `<span class="chip chip-${f.sev}">${f.label}</span>`;
}

async function loadDay() {
  const shift = document.getElementById('shiftFilter').value;
  const search = document.getElementById('searchInput').value.trim();

  if (search.length >= 2) {
    const r = await fetch(`/schedule-hub/api/search?q=${encodeURIComponent(search)}&week=${state.week}`);
    renderSearchResults(await r.json());
    return;
  }

  let url = `/schedule-hub/api/signin?day=${state.day}&week=${state.week}`;
  if (shift) url += `&shift=${shift}`;
  if (state.transport) url += '&transport_only=true';
  if (state.issues) url += '&issues_only=true';

  const r = await fetch(url);
  const data = await r.json();
  renderDayTabs(data);
  renderSignIn(data);
}

function renderDayTabs(data) {
  // Keep counts from summary (fetched separately); just render tabs
  const el = document.getElementById('dayTabs');
  if (!el.dataset.built) {
    el.innerHTML = DAYS.map((d,i) =>
      `<span class="day-tab${d===state.day?' active':''}" onclick="switchDay('${d}',this)">${DAY_NAMES[i]}</span>`
    ).join('');
    el.dataset.built = '1';
  } else {
    document.querySelectorAll('.day-tab').forEach((t,i) =>
      t.classList.toggle('active', DAYS[i]===state.day));
  }
}

function renderSignIn(data) {
  const clients = data.clients || [];
  let html = `<table><thead><tr>
    <th>#</th><th>Client</th><th>Time</th><th>Payer</th><th>TR</th><th>Auth Exp</th><th>Flags</th>
  </tr></thead><tbody>`;

  clients.forEach((c,i) => {
    const shiftBadge = c.shift === 'MORNING' ? 'badge-morning' : 'badge-afternoon';
    html += `<tr>
      <td data-l="#" class="no-l">${i+1}</td>
      <td data-l="Client"><button class="name-btn" onclick="openClient(${c.client_id})">${c.name}</button></td>
      <td data-l="Time"><span class="badge ${shiftBadge}">${c.time}</span></td>
      <td data-l="Payer">${c.payer || '?'}</td>
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
    <div class="card warn"><div class="value">${data.issues||0}</div><div class="label">⚠️ Auth/Payer Issues</div></div>
  `;
}

function renderSearchResults(data) {
  const results = data.results || [];
  let html = `<table><thead><tr><th>Client</th><th>Day</th><th>Time</th><th>Payer</th></tr></thead><tbody>`;
  results.forEach(r => {
    html += `<tr>
      <td data-l="Client"><button class="name-btn" onclick="openClient(${r.client_id})">${r.full_name}</button></td>
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

async function loadSummary() {
  const r = await fetch('/schedule-hub/api/summary');
  const data = await r.json();
  document.getElementById('headerStats').innerHTML =
    `${data.total_clients} clients · Next Mon: ${data.next_monday} · ` +
    `<span style="color:var(--red)">${data.auth_gaps} no-auth Mon</span> · ` +
    `<span style="color:var(--yellow)">${data.auth_expiring} expiring</span>`;
}

/* ── Client detail modal ── */
async function openClient(id) {
  const r = await fetch(`/schedule-hub/api/client/${id}`);
  if (!r.ok) return;
  const c = await r.json();
  const wk = c.weeks['31'];
  const wk30 = c.weeks['30'];

  const gridHTML = (wkdata, label) => `
    <h3>${label} <span style="color:var(--dim);font-weight:400">${wkdata.start} → ${wkdata.end}</span></h3>
    <div class="wk-grid">
      ${DAYS.map(d => {
        const cell = wkdata.days[d];
        if (!cell) return `<div class="wk-cell off"><div class="d">${d.toUpperCase()}</div>—</div>`;
        return `<div class="wk-cell"><div class="d">${d.toUpperCase()}</div>
          <div class="t">${cell.time}</div>
          <div>${cell.payer||'?'} ${cell.transport?'🚗':''}</div>
          <div style="margin-top:2px">${cell.flags.join(' ')}</div></div>`;
      }).join('')}
    </div>`;

  const authHTML = c.authorizations.length ? c.authorizations.map(a => `
    <div class="auth-row ${a.status==='ACTIVE'?'auth-active':'auth-other'}">
      <span class="pn">${a.payer||'Unknown payer'}</span>
      <span>Auth: ${a.auth_number||'—'}</span>
      <span>${a.service_start||'?'} → <b>${a.service_end||'?'}</b></span>
      <span>${a.status}</span>
    </div>`).join('') : '<div style="color:var(--red);font-size:.85em">🔴 No authorization on file — client attends, submit auth ASAP.</div>';

  const routeHTML = c.transport_routes.length ? c.transport_routes.map(t => `
    <div class="route-row">🚗 <b>${t.day_of_week.toUpperCase()}</b> ${t.shift} · Driver: <b>${t.driver_name}</b>${t.driver_phone?' · '+t.driver_phone:''}<br>
    <span style="color:var(--dim)">${t.client_address||''} ${t.client_phone?'· '+t.client_phone:''}</span></div>`).join('')
    : '<div style="color:var(--dim);font-size:.85em">No route assignment on file.</div>';

  document.getElementById('modalHost').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <button class="close-x" onclick="closeModal()">✕ Close</button>
        <h2>${c.full_name}</h2>
        <div class="sub">Carecenta ID ${c.carecenta_id} · ${c.status} · ${c.overall_flags.join(' ')}</div>
        ${gridHTML(wk, 'Next Week')}
        ${gridHTML(wk30, 'This Week')}
        <h3>Authorizations (${c.authorizations.length})</h3>
        ${authHTML}
        <h3>Transport / Routes</h3>
        ${routeHTML}
      </div>
    </div>`;
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modalHost').innerHTML = '';
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

function exportCSV() {
  window.open(`/schedule-hub/api/export/signin?day=${state.day}&week=${state.week}&format=csv`);
}
function exportDayPDF() {
  window.open(`/schedule-hub/api/export/daily-pdf?day=${state.day}&week=${state.week}`);
}
function exportWeeklyPDF() {
  window.open(`/schedule-hub/api/export/weekly-pack?week=${state.week}`);
}

init();
</script>
</body>
</html>
""")


@router.get("/health")
async def health():
    return {"status": "ok", "db": str(SCHEDULE_DB), "db_exists": SCHEDULE_DB.exists()}
