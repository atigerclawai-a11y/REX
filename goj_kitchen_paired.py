#!/usr/bin/env python3
"""
GOJ Kitchen Count Sheet Generator — Paired Main + Side
Reads from goj_proprietary.db, generates PDF kitchen count sheets
Usage: python3 goj_kitchen_paired.py --date 2026-06-10 --shift 1

Deploy to Mac Mini:
  cp goj_kitchen_paired.py ~/Desktop/REX/
  python3 ~/Desktop/REX/goj_kitchen_paired.py --date 2026-06-10 --shift 1
"""
import sqlite3, argparse, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Drive preflight ───────────────────────────────────────────────────
sys.path.insert(0, str(Path.home() / "Desktop" / "REX"))
from CC_drive_preflight import preflight

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import stringWidth
except ImportError:
    print("Installing reportlab...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "reportlab", "--break-system-packages", "-q"])
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import stringWidth

DB_PATH    = Path.home() / "Documents/goj files/proprietary/goj_proprietary.db"
OUTPUT_DIR = Path.home() / "Documents/goj files/output_docs"
ADDRESS    = "3152 Brighton 6 St, Brooklyn NY 11235  |  Garden of Joy Adult Day Care Center"

FONT_PATHS = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def register_fonts():
    for path in FONT_PATHS:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont('DV', path))
                pdfmetrics.registerFont(TTFont('DV-Bold', path))
                return True
            except Exception:
                continue
    return False

def get_orders(date_str, shift):
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT cm.client_name, cm.salad, cm.soup, cm.main, cm.side
        FROM client_menus cm
        JOIN clients c ON c.name = cm.client_name
        WHERE cm.menu_date = ? AND cm.shift = ? AND c.active = 1 AND (c.deceased IS NULL OR c.deceased = 0)
        ORDER BY cm.client_name
    """, (date_str, str(shift))).fetchall()
    conn.close()
    return rows

def tally_single(orders, field):
    counts = defaultdict(int)
    for row in orders:
        val = (row[field] or "").strip()
        if val: counts[val] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))

def tally_paired(orders):
    counts = defaultdict(int)
    for row in orders:
        main = (row[3] or "").strip()
        side = (row[4] or "").strip()
        if main:
            key = f"{main} + {side}" if side else main
            counts[key] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))

def draw_kitchen(output, orders, date_str, shift):
    has_fonts = register_fonts()
    fn      = "DV" if has_fonts else "Helvetica"
    fn_bold = "DV-Bold" if has_fonts else "Helvetica-Bold"

    W, H = landscape(letter)
    M = 28; CW = W - 2*M
    c = canvas.Canvas(str(output), pagesize=landscape(letter))

    salad_t = tally_single(orders, 1)
    soup_t  = tally_single(orders, 2)
    pair_t  = tally_paired(orders)
    total   = len(orders)

    # Header
    c.setFillColorRGB(0.12, 0.12, 0.12)
    c.rect(0, H-48, W, 48, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(fn_bold, 14)
    c.drawCentredString(W/2, H-22, f"KITCHEN COUNT SHEET — {date_str} — SHIFT {shift}")
    c.setFont(fn, 9)
    c.drawCentredString(W/2, H-37, f"Total clients: {total}   |   Garden of Joy Adult Day Care")

    # 3 columns: Salads 20% | Soups 20% | Main+Side 60%
    col_widths = [CW*0.20, CW*0.20, CW*0.60]
    col_x      = [M, M+col_widths[0], M+col_widths[0]+col_widths[1]]
    sections   = [
        ("САЛАТЫ",           salad_t, col_widths[0], col_x[0]),
        ("СУПЫ",             soup_t,  col_widths[1], col_x[1]),
        ("ГЛАВНОЕ + ГАРНИР", pair_t,  col_widths[2], col_x[2]),
    ]

    for title, counts, cw, cx in sections:
        def section_header():
            y0 = H - 60
            c.setFillColorRGB(0.20, 0.35, 0.65)
            c.rect(cx+2, y0-16, cw-4, 18, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1)
            c.setFont(fn_bold, 10)
            c.drawCentredString(cx+cw/2, y0-9, title)
            y0b = y0 - 20
            c.setFont(fn, 8); c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(cx+cw/2, y0b-6, f"Total: {sum(counts.values())}")
            return y0b - 12

        y = section_header()
        page_no = 1
        rendered = 0
        for i, (item, cnt) in enumerate(counts.items()):
            if y < 40:
                # paginate instead of silently dropping rows (fixed 2026-07-27:
                # previously `break` hid overflow combos — totals counted them, page didn't)
                print(f"  ⚠ {title}: page {page_no} full at row {i}/{len(counts)} — continuing on page {page_no+1}")
                c.setFont(fn, 7); c.setFillColorRGB(0.5, 0.5, 0.5)
                c.drawCentredString(W/2, 18, f"3152 Brighton 6 St, Brooklyn NY 11235 | Garden of Joy Adult Day Care Center — {title} p.{page_no}")
                c.showPage()
                page_no += 1
                y = section_header()
            c.setFillColorRGB(*(0.94, 0.96, 1.0) if i%2==0 else (1, 1, 1))
            c.rect(cx+2, y-13, cw-4, 14, fill=1, stroke=0)
            c.setStrokeColorRGB(0.8, 0.8, 0.8); c.setLineWidth(0.5)
            c.rect(cx+2, y-13, cw-4, 14, fill=0, stroke=1)
            c.setFillColorRGB(0, 0, 0)
            fs = 8.5
            while stringWidth(item, fn, fs) > cw-28 and fs > 7: fs -= 0.3
            c.setFont(fn, fs); c.drawString(cx+5, y-10, item)
            c.setFont(fn_bold, 10); c.setFillColorRGB(0.12, 0.35, 0.65)
            c.drawRightString(cx+cw-6, y-10, str(cnt))
            y -= 14

    # Footer
    c.setFillColorRGB(0.12, 0.12, 0.12); c.rect(0, 0, W, 22, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1); c.setFont(fn, 7)
    c.drawCentredString(W/2, 7, ADDRESS)
    c.save()
    return str(output)

def main():
    parser = argparse.ArgumentParser(description="GOJ Kitchen Count Sheet Generator")
    parser.add_argument("--date",  required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--shift", required=True, type=int, help="Shift number (1 or 2)")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip Drive preflight (use existing DB data)")
    args = parser.parse_args()

    # ── Drive-first preflight + no-menu flags ─────────────────────────
    pf = None
    if not args.skip_preflight:
        try:
            pf = preflight(args.date)
            # Determine no-menu clients for this specific shift
            shift_no_menu = []
            if pf.get("no_menu"):
                attendance_shift_raw = pf['attendance'].get(args.shift, [])
                attendance_shift = set(
                    c['name'] if isinstance(c, dict) else c
                    for c in attendance_shift_raw
                )
                shift_no_menu = [n for n in pf['no_menu'] if n in attendance_shift]
            if shift_no_menu:
                print(f"Preflight: {len(shift_no_menu)} no-menu clients for shift {args.shift}")
                conn = sqlite3.connect(str(DB_PATH))
                # Ensure source_sheet column exists
                conn.execute("CREATE TABLE IF NOT EXISTS client_menus ("
                             "client_name TEXT, menu_date TEXT, shift TEXT,"
                             "salad TEXT, soup TEXT, main TEXT, side TEXT,"
                             "source_sheet TEXT)")
                try:
                    conn.execute("ALTER TABLE client_menus ADD COLUMN source_sheet TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                for name in shift_no_menu:
                    conn.execute(
                        "INSERT OR IGNORE INTO client_menus "
                        "(client_name, menu_date, shift, salad, soup, main, side, source_sheet) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, args.date, str(args.shift),
                         "заказ не размещен", "заказ не размещен",
                         "заказ не размещен", "заказ не размещен",
                         "no_order_flag"))
                conn.commit()
                conn.close()
                print(f"  → Flagged {len(shift_no_menu)} clients as 'заказ не размещен'")
        except Exception as e:
            print(f"Preflight warning (non-fatal): {e}")
    else:
        print("⏭️  Skipping preflight — using existing DB data")

    orders = get_orders(args.date, args.shift)
    if not orders:
        print(f"No menu data found in goj_proprietary.db for {args.date} shift {args.shift}")
        print("Make sure the Mirror cron has synced today's menu data.")
        sys.exit(1)

    # ── Filter to attending clients only (auth_tracker.db day_*_actual) ──
    dt = datetime.strptime(args.date, "%Y-%m-%d")
    day_codes = ["M", "T", "W", "TH", "F", "Su", "Su"]  # Saturday uses day_Su_actual column (shared with Sunday)
    day_col = f"day_{day_codes[dt.weekday()]}_actual"
    auth_db = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
    aconn = sqlite3.connect(str(auth_db))
    attending = set(r[0] for r in aconn.execute(
        f"SELECT name FROM clients WHERE active=1 AND (deceased IS NULL OR deceased = 0) AND {day_col}=?", (str(args.shift),)
    ).fetchall())
    aconn.close()
    before = len(orders)
    orders = [o for o in orders if o[0] in attending]
    print(f"Attendance filter: {before} → {len(orders)} ({before - len(orders)} not attending removed)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dt       = datetime.strptime(args.date, "%Y-%m-%d")
    date_str = dt.strftime("%A, %B %-d, %Y")
    fname    = OUTPUT_DIR / f"Kitchen_{dt.strftime('%a_%b%d')}_S{args.shift}.pdf"

    out = draw_kitchen(fname, orders, date_str, args.shift)
    print(f"Generated: {out} ({len(orders)} clients)")

if __name__ == "__main__":
    main()
