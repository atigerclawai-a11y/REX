#!/usr/bin/env python3
"""
GOJ v1.2 — Distribution Sheet Generator
Generates per-shift, print-ready distribution PDFs from auth_tracker.db.
Usage: python3 generate_distribution_sheet.py [--date YYYY-MM-DD] [--db PATH] [--output-dir PATH]
"""

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Cyrillic font registration ────────────────────────────────────────────────
FONTS_DIR = Path.home() / "Documents" / "goj files" / "fonts"
FONT_REG  = "DejaVu"
FONT_BOLD = "DejaVuBold"
try:
    pdfmetrics.registerFont(TTFont(FONT_REG,  str(FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONTS_DIR / "DejaVuSans-Bold.ttf")))
except Exception:
    FONT_REG  = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_DB   = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
MENU_DB_PATH = Path.home() / "Documents" / "goj files" / "proprietary" / "goj_proprietary.db"
DEFAULT_OUT  = Path.home() / "Documents" / "goj files" / "documents" / "print_sheets"
ADDR_FOOTER  = "3152 Brighton 6 St, Brooklyn NY 11235  |  Garden of Joy Adult Day Care Center"

DAY_KEYS = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "Su", 6: "Su"}  # weekday() → col key (Sat+Sun share day_Su_actual)
DAY_NAMES = {"M": "M", "T": "T", "W": "W",
             "TH": "TH", "F": "F", "Su": "SA"}  # matches client_menus.day column values

# ── Helpers ──────────────────────────────────────────────────────────────────
def next_business_day(from_date: date) -> date:
    """Return next Mon–Sat from from_date."""
    d = from_date + timedelta(days=1)
    while d.weekday() == 6:  # skip Sunday
        d += timedelta(days=1)
    return d


def get_day_key(d: date) -> str:
    wd = d.weekday()
    return DAY_KEYS.get(wd, "M")


def get_week_start(d: date) -> date:
    """Return Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def _norm(n):
    """Normalize name: Cyrillic transliteration variants (y↔i, ks↔x)."""
    n = n.strip().lower().replace("'", "").replace("\u02bc", "")
    n = n.replace("ks", "x").replace("iy", "i")
    result = []
    for i, ch in enumerate(n):
        if ch == 'y' and i > 0 and n[i-1] not in 'aeiou':
            result.append('i')
        else:
            result.append(ch)
    return ''.join(result)


def fetch_attendees(db_path: Path, service_date: date) -> dict:
    """
    Returns {1: [client_rows], 2: [client_rows]} sorted alphabetically.
    Each row: (client_name, shift, salad, soup, main, side)
    Attendance from auth_tracker.db. Menus from goj_proprietary.db (preflight-synced).
    """
    day_key = get_day_key(service_date)
    col = f"day_{day_key}_actual"

    # Attendance from auth_tracker.db
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"""
        SELECT client_id, name, shift, {col} as day_shift
        FROM clients
        WHERE {col} > 0 AND active = 1 AND (deceased IS NULL OR deceased = 0)
        ORDER BY name
    """)
    clients = cur.fetchall()
    conn.close()

    # Menus from goj_proprietary.db (synced by preflight from live Drive)
    menu_conn = sqlite3.connect(str(MENU_DB_PATH))
    menu_conn.row_factory = sqlite3.Row
    menu_cur = menu_conn.cursor()

    result = {1: [], 2: []}
    # Build normalized menu map for fallback matching
    menu_cur.execute("SELECT client_name, salad, soup, main, side FROM client_menus WHERE menu_date=?",
                     (service_date.isoformat(),))
    all_menus = menu_cur.fetchall()
    menu_map = {r["client_name"]: r for r in all_menus}
    norm_menu_map = {_norm(r["client_name"]): r for r in all_menus}

    for c in clients:
        client_shift = c["day_shift"]
        # Exact match first, then normalized
        menu = menu_map.get(c["name"]) or norm_menu_map.get(_norm(c["name"]))

        if menu:
            salad = menu["salad"] or ""
            soup  = menu["soup"]  or ""
            main  = menu["main"]  or ""
            side  = menu["side"]  or ""
            main_side = f"{main} + {side}" if main and side else (main or side or "")
            no_menu = False
        else:
            salad = soup = main_side = ""
            no_menu = True

        row = {
            "name":      c["name"],
            "shift":     client_shift,
            "salad":     salad,
            "soup":      soup,
            "main_side": main_side,
            "no_menu":   no_menu,
        }
        if client_shift in result:
            result[client_shift].append(row)

    menu_conn.close()
    return result


def build_pdf(clients: list, shift_num: int, service_date: date, output_path: Path):
    """Generate a single distribution PDF for one shift — PORTRAIT, full-page."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.40*inch,
        rightMargin=0.40*inch,
        topMargin=0.40*inch,
        bottomMargin=0*inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", fontSize=18, fontName=FONT_BOLD,
                                 alignment=TA_CENTER, spaceAfter=8)
    sub_style   = ParagraphStyle("sub",   fontSize=13, fontName=FONT_REG,
                                 alignment=TA_CENTER, spaceAfter=10)
    foot_style  = ParagraphStyle("foot",  fontSize=9,  fontName=FONT_REG,
                                 alignment=TA_CENTER)
    no_menu_style = ParagraphStyle("nomenu", fontSize=13, fontName=FONT_BOLD,
                                   textColor=colors.red)

    ROWS_PER_PAGE = 17
    total_clients = len(clients)
    total_pages   = max(1, -(-total_clients // ROWS_PER_PAGE))  # ceiling div

    story = []

    # Cell styles with text wrapping
    cell_style = ParagraphStyle("cell", fontSize=13, fontName=FONT_REG,
                                leading=16, alignment=TA_LEFT)
    cell_bold  = ParagraphStyle("cellb", fontSize=13, fontName=FONT_BOLD,
                                leading=16, alignment=TA_LEFT)
    no_menu_para = ParagraphStyle("nomenu", fontSize=13, fontName=FONT_BOLD,
                                  leading=16, textColor=colors.red)

    for page_idx in range(total_pages):
        page_num    = page_idx + 1
        slice_start = page_idx * ROWS_PER_PAGE
        slice_end   = slice_start + ROWS_PER_PAGE
        page_clients = clients[slice_start:slice_end]

        # Header
        story.append(Paragraph("Garden of Joy — FOOD DISTRIBUTION SHEET", title_style))
        hdr = (f"Date: {service_date.strftime('%B %d, %Y')}    "
               f"Shift: {shift_num}    "
               f"Total Clients: {total_clients}    "
               f"Page {page_num}/{total_pages}    "
               f"★ Check box after each delivery")
        story.append(Paragraph(hdr, sub_style))
        story.append(Spacer(1, 0.10*inch))

        # Table header — portrait 8.5" → 7.7" available with 0.40" margins
        col_widths = [0.40*inch, 1.90*inch, 1.35*inch, 1.10*inch, 2.55*inch, 0.40*inch]
        header_row = ["No", "Client Name", "Salad", "Soup", "Main + Side", "✓"]
        table_data = [header_row]

        # Data rows (pad to ROWS_PER_PAGE)
        for i in range(ROWS_PER_PAGE):
            row_num = slice_start + i + 1
            if i < len(page_clients):
                c = page_clients[i]
                if c["no_menu"]:
                    name_cell = Paragraph(c["name"], cell_style)
                    salad_cell = Paragraph("<b>NO MENU</b>", no_menu_para)
                    soup_cell  = Paragraph("", cell_style)
                    ms_cell    = Paragraph("", cell_style)
                else:
                    name_cell  = Paragraph(c["name"], cell_style)
                    salad_cell = Paragraph(c["salad"] or "", cell_style)
                    soup_cell  = Paragraph(c["soup"] or "", cell_style)
                    ms_cell    = Paragraph(c["main_side"] or "", cell_style)
                table_data.append([
                    Paragraph(str(row_num), ParagraphStyle("n", fontSize=13, fontName=FONT_REG, alignment=TA_CENTER)),
                    name_cell, salad_cell, soup_cell, ms_cell,
                    Paragraph("", cell_style)
                ])
            else:
                table_data.append([
                    Paragraph(str(row_num) if row_num <= total_clients else "", cell_style),
                    Paragraph("", cell_style), Paragraph("", cell_style),
                    Paragraph("", cell_style), Paragraph("", cell_style),
                    Paragraph("", cell_style)
                ])

        # Footer row on last page
        if page_num == total_pages:
            table_data.append([
                Paragraph(f"<b>TOTAL: {total_clients}</b>", styles["Normal"]),
                Paragraph("<b>All dishes delivered: ___________</b>", styles["Normal"]),
                "", "",
                Paragraph("<b>Staff signature: _______________</b>", styles["Normal"]),
                ""
            ])

        # Calculate row heights: header + data rows, evenly filling available space
        # Available height ≈ 7.8" = 562 pts, header 26pt, 14 data rows
        data_row_h = 32  # pts per data row (portrait)
        row_heights = [26] + [data_row_h] * ROWS_PER_PAGE
        # Add footer row height on last page
        if page_num == total_pages:
            row_heights.append(30)
        tbl = Table(table_data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)

        style = TableStyle([
            # Header
            ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1a1a1a")),
            ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
            ("FONTNAME",     (0,0), (-1,0), FONT_BOLD),
            ("FONTSIZE",     (0,0), (-1,0), 14),
            ("ALIGN",        (0,0), (-1,0), "CENTER"),
            ("VALIGN",       (0,0), (-1,0), "MIDDLE"),
            ("ROWHEIGHT",    (0,0), (-1,0), 26),
            # Data rows
            ("FONTNAME",     (0,1), (-1,-1), FONT_REG),
            ("FONTSIZE",     (0,1), (-1,-1), 13),
            ("ALIGN",        (0,1), (0,-1),  "CENTER"),   # No col
            ("ALIGN",        (5,1), (5,-1),  "CENTER"),   # ✓ col
            ("VALIGN",       (0,1), (-1,-1), "MIDDLE"),
            # Alternating rows
            *[("BACKGROUND", (0,i), (-1,i), colors.HexColor("#f0f0f0"))
              for i in range(2, len(table_data), 2)],
            # Grid
            ("GRID",         (0,0), (-1,-1), 0.5, colors.grey),
            ("BOX",          (0,0), (-1,-1), 1.0, colors.black),
            # Checkbox column border
            ("BOX",          (5,1), (5,-1),  1.5, colors.black),
        ])
        tbl.setStyle(style)
        story.append(tbl)

        story.append(Paragraph(ADDR_FOOTER, foot_style))

        # Page break between pages (not after last)
        if page_num < total_pages:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

    doc.build(story)
    return output_path


def generate(service_date: date, db_path: Path, output_dir: Path) -> list:
    """Generate distribution sheets for all shifts. Returns list of created file paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    attendees = fetch_attendees(db_path, service_date)
    created = []
    no_menu_flags = []

    for shift_num, clients in attendees.items():
        if not clients:
            print(f"  Shift {shift_num}: No clients scheduled — skipping")
            continue

        fname = output_dir / f"distribution_shift{shift_num}_{service_date.isoformat()}.pdf"
        build_pdf(clients, shift_num, service_date, fname)
        nm = [c["name"] for c in clients if c["no_menu"]]
        no_menu_flags.extend(nm)
        print(f"  ✅ Shift {shift_num}: {len(clients)} clients → {fname.name}")
        if nm:
            print(f"     ⚠️  NO MENU: {', '.join(nm)}")
        created.append(fname)

    return created, no_menu_flags


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate GOJ distribution sheets")
    parser.add_argument("--date",       default=None, help="Service date YYYY-MM-DD (default: tomorrow)")
    parser.add_argument("--db",         default=str(DEFAULT_DB))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    service_date = date.fromisoformat(args.date) if args.date else next_business_day(date.today())
    db_path      = Path(args.db)
    output_dir   = Path(args.output_dir)

    print(f"\n{'='*60}")
    print(f" GOJ Distribution Sheet Generator — {service_date}")
    print(f"{'='*60}")

    files, flags = generate(service_date, db_path, output_dir)

    print(f"\n{'='*60}")
    print(f" Generated {len(files)} file(s)")
    if flags:
        print(f" ⚠️  {len(flags)} clients flagged with NO MENU")
    print(f"{'='*60}\n")
