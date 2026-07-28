"""
GOJ Attendance Report Generator
=================================
Generates a clean, professional PDF attendance report from attendance_log
in auth_tracker.db — formatted for the Molina Healthcare site visit auditor.

Covers all logged attendance from REPORT_START onward, grouped by date.

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python goj_attendance_report.py

Or for a specific date range:
    python goj_attendance_report.py --from 2026-03-01 --to 2026-04-30

Output: ~/Desktop/GOJ_Attendance_Report_<date>.pdf
"""

import sys
import sqlite3
import datetime
import argparse
import logging
from pathlib import Path
from collections import defaultdict

# ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("attendance_report")

# ─── Paths ──────────────────────────────────────────────────────────────────────
DASHBOARD_DIR = Path.home() / "Documents" / "goj files" / "dashboard"
AUTH_DB       = DASHBOARD_DIR / "auth_tracker.db"
OUT_DIR       = Path.home() / "Desktop"

# Default report range
DEFAULT_START = "2026-01-01"
DEFAULT_END   = datetime.date.today().isoformat()

# Colors
GOJ_GREEN  = colors.HexColor("#2d5016")
GOJ_GOLD   = colors.HexColor("#d4a843")
GOJ_CREAM  = colors.HexColor("#fdf8f2")
GOJ_TAN    = colors.HexColor("#e8dfd0")
LIGHT_GREY = colors.HexColor("#f7f2ea")
TEXT_DARK  = colors.HexColor("#2c2418")
TEXT_MUTED = colors.HexColor("#7a6a5a")

DOW = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
       4: "Friday", 5: "Saturday", 6: "Sunday"}


# ─── Data loading ──────────────────────────────────────────────────────────────

def load_attendance(db: sqlite3.Connection, start: str, end: str) -> dict:
    """
    Returns {date_str: {shift_int: [client_name, ...]}}
    """
    cur = db.cursor()
    cur.execute("""
        SELECT log_date, shift, client_name, status, source, note
        FROM attendance_log
        WHERE log_date >= ? AND log_date <= ?
        ORDER BY log_date ASC, shift ASC, client_name ASC
    """, (start, end))

    data = defaultdict(lambda: defaultdict(list))
    for row in cur.fetchall():
        log_date, shift, client_name, status, source, note = row
        data[log_date][shift or 1].append({
            "name":   client_name,
            "status": status or "scheduled",
            "source": source or "",
        })
    return data


def load_scheduled_clients(db: sqlite3.Connection, date_str: str) -> dict[int, list[str]]:
    """
    Returns {shift: [client_names]} for clients scheduled on the given date's weekday.
    """
    try:
        dt = datetime.date.fromisoformat(date_str)
    except ValueError:
        return {}

    day_cols = {
        0: "day_M_actual",
        1: "day_T_actual",
        2: "day_W_actual",
        3: "day_TH_actual",
        4: "day_F_actual",
        5: "day_Su_actual",
    }
    col = day_cols.get(dt.weekday())
    if not col:
        return {}

    cur = db.cursor()
    try:
        cur.execute(f"""
            SELECT name, shift FROM clients
            WHERE active=1 AND {col} > 0
            ORDER BY name ASC
        """)
        result = defaultdict(list)
        for name, shift in cur.fetchall():
            result[shift or 1].append(name)
        return result
    except Exception as e:
        log.warning(f"Could not load scheduled clients for {date_str}: {e}")
        return {}


# ─── PDF generation ────────────────────────────────────────────────────────────

def draw_page_header(c: canvas.Canvas, doc_date: str, page_num: int, total_pages: int,
                     report_start: str, report_end: str, width: float, height: float):
    """Draws the GOJ header on each page."""
    c.setFillColor(GOJ_GREEN)
    c.rect(0, height - 72, width, 72, fill=True, stroke=False)

    c.setFillColor(GOJ_GOLD)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, height - 28, "GARDEN OF JOY ADULT DAY CARE CENTER")

    c.setFillColor(colors.white)
    c.setFont("Helvetica", 10)
    c.drawString(36, height - 48, "3152 Brighton 6 St, Brooklyn NY 11235  |  Attendance Record")

    c.setFont("Helvetica", 9)
    c.drawRightString(width - 36, height - 28, f"Report Period: {report_start} to {report_end}")
    c.drawRightString(width - 36, height - 48, f"Generated: {datetime.date.today().isoformat()}")
    c.drawRightString(width - 36, height - 65, f"Page {page_num} of {total_pages}")

    # Thin gold rule below header
    c.setStrokeColor(GOJ_GOLD)
    c.setLineWidth(2)
    c.line(0, height - 74, width, height - 74)


def build_day_table(day_date: str, shift_data: dict, scheduled: dict) -> list:
    """Build table rows for one day."""
    try:
        dt = datetime.date.fromisoformat(day_date)
        dow_name = DOW[dt.weekday()]
        date_label = dt.strftime("%B %d, %Y")
    except ValueError:
        dow_name = "Unknown"
        date_label = day_date

    elements = []
    styles = getSampleStyleSheet()

    # Day header
    day_style = ParagraphStyle(
        "DayHeader",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=GOJ_GREEN,
        spaceAfter=4,
        spaceBefore=14,
    )
    elements.append(Paragraph(f"{dow_name}, {date_label}", day_style))

    # Shift sections
    for shift_num in sorted(set(list(shift_data.keys()) + list(scheduled.keys()))):
        logged  = {e["name"]: e["status"] for e in shift_data.get(shift_num, [])}
        sched   = scheduled.get(shift_num, [])

        # Merge: scheduled clients + any extra logged ones
        all_names = sorted(set(sched) | set(logged.keys()))

        if not all_names:
            continue

        shift_label = f"Shift {shift_num}"
        elements.append(Paragraph(
            f"<font color='#{GOJ_GREEN.hexval()[2:]}'><b>{shift_label}</b></font> — {len(all_names)} clients",
            ParagraphStyle("ShiftLabel", parent=styles["Normal"], fontSize=9,
                           textColor=TEXT_MUTED, spaceBefore=4, spaceAfter=3)
        ))

        # Table: No | Name | Status | Source
        table_data = [["#", "Client Name", "Status", "Source"]]
        for i, name in enumerate(all_names, 1):
            status = logged.get(name, "scheduled")
            source = ""
            for e in shift_data.get(shift_num, []):
                if e["name"] == name:
                    source = e.get("source", "")
                    break

            # Format status
            status_display = {
                "present":   "✓ Present",
                "absent":    "✗ Absent",
                "scheduled": "— Scheduled",
            }.get(status, status)

            table_data.append([str(i), name, status_display, source])

        col_widths = [0.4 * inch, 2.8 * inch, 1.2 * inch, 1.1 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header row
            ("BACKGROUND",    (0, 0), (-1, 0),  GOJ_GREEN),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("TOPPADDING",    (0, 0), (-1, 0),  5),
            ("BOTTOMPADDING", (0, 0), (-1, 0),  5),
            # Data rows
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("TOPPADDING",    (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            # Alternating rows
            *[("BACKGROUND", (0, r), (-1, r), LIGHT_GREY)
              for r in range(2, len(table_data), 2)],
            # Grid
            ("GRID",          (0, 0), (-1, -1), 0.4, GOJ_TAN),
            ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
            # Status coloring
            *[("TEXTCOLOR", (2, r), (2, r),
               colors.HexColor("#2e7d32") if table_data[r][2].startswith("✓")
               else (colors.HexColor("#c62828") if table_data[r][2].startswith("✗")
                     else TEXT_MUTED))
              for r in range(1, len(table_data))],
        ]))
        elements.append(table)

        # Total row
        present_count = sum(1 for e in shift_data.get(shift_num, []) if e["status"] == "present")
        absent_count  = sum(1 for e in shift_data.get(shift_num, []) if e["status"] == "absent")
        sched_count   = len(all_names)
        elements.append(Paragraph(
            f"Total scheduled: {sched_count} | Present: {present_count} | Absent: {absent_count} | Unverified: {sched_count - present_count - absent_count}",
            ParagraphStyle("Totals", parent=styles["Normal"], fontSize=8,
                           textColor=TEXT_MUTED, spaceBefore=2, spaceAfter=6)
        ))

    return elements


def generate_report(start: str, end: str, output_path: Path):
    log.info(f"Generating attendance report: {start} → {end}")

    db = sqlite3.connect(str(AUTH_DB))
    attendance = load_attendance(db, start, end)

    if not attendance:
        log.warning("No attendance records found for this period.")
        db.close()
        return

    log.info(f"Found attendance for {len(attendance)} dates")

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=90,
        bottomMargin=54,
        leftMargin=36,
        rightMargin=36,
    )

    width, height = letter

    # Cover summary
    elements = []
    cover_style = ParagraphStyle(
        "Cover", parent=styles["Normal"], fontSize=11,
        textColor=TEXT_DARK, spaceAfter=6
    )
    total_entries = sum(
        sum(len(v) for v in shifts.values())
        for shifts in attendance.values()
    )
    present = sum(
        sum(1 for e in v if e["status"] == "present")
        for shifts in attendance.values() for v in shifts.values()
    )

    elements.append(Paragraph(
        f"<b>Attendance Summary</b>",
        ParagraphStyle("SumTitle", parent=styles["Heading1"], textColor=GOJ_GREEN, fontSize=14, spaceAfter=8)
    ))
    elements.append(Paragraph(f"Report Period: <b>{start}</b> to <b>{end}</b>", cover_style))
    elements.append(Paragraph(f"Operating Days Recorded: <b>{len(attendance)}</b>", cover_style))
    elements.append(Paragraph(f"Total Attendance Entries: <b>{total_entries}</b>", cover_style))
    elements.append(Paragraph(f"Confirmed Present: <b>{present}</b>", cover_style))
    elements.append(Paragraph(
        "Status key: ✓ Present = confirmed attendance | ✗ Absent = notified absence | — Scheduled = on roster (signature not yet verified)",
        ParagraphStyle("Key", parent=styles["Normal"], fontSize=8, textColor=TEXT_MUTED, spaceAfter=16)
    ))
    elements.append(Spacer(1, 0.2 * inch))

    # One section per day
    for day_date in sorted(attendance.keys()):
        day_elements = build_day_table(day_date, attendance[day_date], load_scheduled_clients(db, day_date))
        elements.extend(day_elements)

    db.close()

    # Page template with header
    def header_footer(c: canvas.Canvas, doc_obj):
        c.saveState()
        draw_page_header(c, datetime.date.today().isoformat(),
                         doc_obj.page, 999, start, end, width, height)
        # Footer
        c.setFont("Helvetica", 7)
        c.setFillColor(TEXT_MUTED)
        c.drawCentredString(width / 2, 24,
            "CONFIDENTIAL — Garden of Joy Adult Day Care | Internal Attendance Record | "
            "3152 Brighton 6 St, Brooklyn NY 11235 | (718) 000-0000")
        c.restoreState()

    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)
    log.info(f"✅ Report saved: {output_path}")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate GOJ Attendance Report PDF")
    parser.add_argument("--from", dest="start", default=DEFAULT_START,
                        help=f"Start date YYYY-MM-DD (default: {DEFAULT_START})")
    parser.add_argument("--to", dest="end", default=DEFAULT_END,
                        help=f"End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if not AUTH_DB.exists():
        log.error(f"auth_tracker.db not found at {AUTH_DB}")
        sys.exit(1)

    today = datetime.date.today().strftime("%Y%m%d")
    out   = OUT_DIR / f"GOJ_Attendance_Report_{today}.pdf"

    generate_report(args.start, args.end, out)
    print(f"\nReport ready: {out}")
    print("Print or email this to keep on file for the Molina auditor.")


if __name__ == "__main__":
    main()
