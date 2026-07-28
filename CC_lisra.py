#!/usr/bin/env python3
"""CC_lisra.py — Daily Service List (Lisra) Generator.

Generates a clean, print-ready PDF of all clients served per shift,
with authorization numbers, payers, check-in/out times, and service codes.
Outputs to ~/Desktop/REX/output/ by default.
"""

import argparse, csv, os, sqlite3, sys
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
DB_PATH = HOME / "Documents/goj files/dashboard/auth_tracker.db"
OUTPUT_DIR = HOME / "Desktop/REX/output"

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHIFT_TIMES = {1: ("08:00", "14:00"), 2: ("14:00", "20:00")}

def generate_evv_csv(target_date: str, shift: int) -> list[dict]:
    """Generate EVV records (same logic as CC_evv.py but returns records)."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid date '{target_date}'. Use YYYY-MM-DD.", file=sys.stderr)
        return []

    day_col = {0: "day_M_actual", 1: "day_T_actual", 2: "day_W_actual",
               3: "day_TH_actual", 4: "day_F_actual", 5: "day_Su_actual",
               6: "day_Su_actual"}[dt.weekday()]

    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}", file=sys.stderr)
        return []

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(f"""
        SELECT c.name as client_name, c.shift as client_shift,
               a.authorization_number, a.payer_canonical as payer, a.status as auth_status
        FROM clients c
        LEFT JOIN authorization a ON c.name = a.client_name
        WHERE c.{day_col} = ? AND c.active = 1 AND (c.deceased IS NULL OR c.deceased = 0)
        ORDER BY c.name
    """, (str(shift),)).fetchall()

    records = []
    for row in rows:
        records.append({
            "Client Name": row["client_name"],
            "Service Date": target_date,
            "Shift": f"Shift {shift}",
            "Check In": SHIFT_TIMES[shift][0],
            "Check Out": SHIFT_TIMES[shift][1],
            "Authorization Number": row["authorization_number"] or "",
            "Payer": row["payer"] or "",
            "Auth Status": row["auth_status"] or "UNKNOWN",
            "Source": "Scheduled"
        })

    conn.close()
    return records


def generate_pdf_lisra(records: list[dict], target_date: str, shift: int, output_path: str):
    """Generate a clean, print-ready PDF Lisra."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        print("Installing reportlab...")
        os.system(f"{sys.executable} -m pip install reportlab")
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

    # Try Cyrillic font
    FONT_REG = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    for fp in [Path.home() / "Documents/goj files/fonts/DejaVuSans.ttf"]:
        if fp.exists():
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            pdfmetrics.registerFont(TTFont("DejaVu", str(fp)))
            pdfmetrics.registerFont(TTFont("DejaVuBold", str(Path.home() / "Documents/goj files/fonts/DejaVuSans-Bold.ttf")))
            FONT_REG = "DejaVu"
            FONT_BOLD = "DejaVuBold"
            break

    day_name = DAY_NAMES[datetime.strptime(target_date, "%Y-%m-%d").weekday()]

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('LisraTitle', fontName=FONT_BOLD, fontSize=14, alignment=TA_CENTER, spaceAfter=2)
    sub_style = ParagraphStyle('LisraSub', fontName=FONT_REG, fontSize=9, alignment=TA_CENTER, textColor=colors.gray, spaceAfter=8)

    elements = []
    elements.append(Paragraph(f"GARDEN OF JOY — DAILY SERVICE LIST (LISRA)", title_style))
    # Shift 0 = combined, don't show shift-specific header
    shift_label = f"Shifts 1 & 2" if shift == 0 else f"Shift {shift} ({SHIFT_TIMES[shift][0]}–{SHIFT_TIMES[shift][1]})"
    elements.append(Paragraph(f"{day_name}, {target_date}  |  {shift_label}", sub_style))
    elements.append(Spacer(1, 4))

    # Deduplicate by client name (keep first auth only for display)
    seen = set()
    unique = []
    for r in records:
        name = r["Client Name"]
        if name not in seen:
            seen.add(name)
            unique.append(r)

    # Group by payer
    payers = {}
    for r in unique:
        payer = r["Payer"] or "UNKNOWN"
        payers.setdefault(payer, []).append(r)

    page_num = 0
    for payer, clients in sorted(payers.items()):
        if page_num > 0:
            elements.append(PageBreak())
        page_num += 1

        elements.append(Paragraph(f"<b>{payer}</b> ({len(clients)} clients)", ParagraphStyle('PayerHeader', fontName=FONT_BOLD, fontSize=10, spaceAfter=4, spaceBefore=4)))

        # Build table
        header = ["#", "Client Name", "Auth #", "Status", "Time"]
        data = [header]
        for i, c in enumerate(clients, 1):
            auth = c["Authorization Number"]
            if len(auth) > 18:
                auth = auth[:17] + "…"
            data.append([
                str(i),
                c["Client Name"],
                auth,
                c["Auth Status"],
                f"{c['Check In']}–{c['Check Out']}"
            ])

        t = Table(data, colWidths=[18, 195, 105, 60, 55], repeatRows=1)
        style = [
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0, 0.35, 0, 0.12)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.Color(0, 0.3, 0)),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0, 0, 0, 0.12)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0, 0.4, 0, 0.03)]),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('FONTNAME', (0, 1), (-1, -1), FONT_REG),
        ]
        # Highlight expired auths
        for ri, c in enumerate(clients, 1):
            if c["Auth Status"].upper() == "EXPIRED":
                style.append(('TEXTCOLOR', (3, ri), (3, ri), colors.Color(0.8, 0.15, 0.15)))
                style.append(('FONTNAME', (3, ri), (3, ri), FONT_BOLD))

        t.setStyle(TableStyle(style))
        elements.append(t)
        elements.append(Spacer(1, 6))

    # Summary footer
    elements.append(Spacer(1, 10))
    total_unique = len(unique)
    total_records = len(records)
    elements.append(Paragraph(
        f"<b>Total clients served: {total_unique}  |  Total auth rows: {total_records}  |  "
        f"Payers: {len(payers)}</b>",
        ParagraphStyle('Footer', fontName=FONT_BOLD, fontSize=8, alignment=TA_CENTER, textColor=colors.gray)
    ))

    doc.build(elements)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate Daily Service List (Lisra) PDF")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date YYYY-MM-DD")
    parser.add_argument("--shift", type=int, default=0, choices=[0, 1, 2], help="1=Shift 1, 2=Shift 2, 0=Both")
    args = parser.parse_args()

    target_date = args.date
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)

    if args.shift in (0, 1):
        records_s1 = generate_evv_csv(target_date, 1)
        if records_s1:
            path = str(OUTPUT_DIR / f"lisra_{target_date}_S1.pdf")
            generate_pdf_lisra(records_s1, target_date, 1, path)
            print(f"✅ Shift 1: {len(records_s1)} records → {path}")

    if args.shift in (0, 2):
        records_s2 = generate_evv_csv(target_date, 2)
        if records_s2:
            path = str(OUTPUT_DIR / f"lisra_{target_date}_S2.pdf")
            generate_pdf_lisra(records_s2, target_date, 2, path)
            print(f"✅ Shift 2: {len(records_s2)} records → {path}")

    if args.shift == 0:
        # Combined
        all_records = []
        if records_s1: all_records.extend(records_s1)
        if records_s2: all_records.extend(records_s2)
        path = str(OUTPUT_DIR / f"lisra_{target_date}_combined.pdf")
        generate_pdf_lisra(all_records, target_date, 0, path)
        print(f"✅ Combined: {len(all_records)} records → {path}")


if __name__ == "__main__":
    main()
