#!/usr/bin/env python3
"""
GOJ Kitchen Staff List — Russian Template (combined shifts)
Generates aggregated kitchen prep PDF from live Drive (via preflight).
Landscape, Cyrillic, GOJ navy+gold.
Usage: python3 generate_kitchen_sheet.py [--date YYYY-MM-DD] [--output-dir PATH]
"""

import argparse, sqlite3, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HOME = Path.home()
REX_DIR = HOME / "Desktop" / "REX"
sys.path.insert(0, str(REX_DIR))

DEFAULT_DB   = HOME / "Documents/goj files/dashboard/auth_tracker.db"
MENU_DB_PATH = HOME / "Documents/goj files/proprietary/goj_proprietary.db"
DEFAULT_OUT  = HOME / "Documents/goj files/output_docs"
ADDR_FOOTER  = "3152 Brighton 6 St, Brooklyn NY 11235  |  Garden of Joy Adult Day Care Center"

DAY_KEYS  = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "Su"}

# ── Cyrillic fonts ──────────────────────────────────────────────────────
FONT_PATHS = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    str(HOME / "Documents/goj files/fonts/DejaVuSans.ttf"),
]

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

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


def get_day_key(d: date) -> str:
    return DAY_KEYS.get(d.weekday(), "M")


def next_business_day(from_date: date) -> date:
    d = from_date + timedelta(days=1)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


MONTHS_RU = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",
             7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}
DAYS_RU = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]


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


def fetch_kitchen_counts(db_path: Path, service_date: date) -> dict:
    """All shifts combined. Menus from goj_proprietary.db (preflight-synced from live Drive)."""
    day_key = get_day_key(service_date)
    col = f"day_{day_key}_actual"

    conn = sqlite3.connect(str(DEFAULT_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"""
        SELECT c.name, c.{col} as day_shift
        FROM clients c
        WHERE c.{col} > 0 AND c.active = 1 AND (c.deceased IS NULL OR c.deceased = 0)
    """)
    attending = cur.fetchall()
    conn.close()

    # Menus from goj_proprietary.db (synced by preflight from live Drive)
    menu_conn = sqlite3.connect(str(MENU_DB_PATH))
    menu_conn.row_factory = sqlite3.Row
    menu_cur = menu_conn.cursor()

    # Load all menus for normalized matching
    menu_cur.execute("SELECT client_name, salad, soup, main, side FROM client_menus WHERE menu_date=?",
                     (service_date.isoformat(),))
    all_menus = menu_cur.fetchall()
    menu_map = {r["client_name"]: r for r in all_menus}
    norm_menu_map = {_norm(r["client_name"]): r for r in all_menus}

    salads = Counter()
    soups  = Counter()
    mains  = Counter()
    sides  = Counter()
    combos = Counter()

    for row in attending:
        name = row["name"]
        shift = str(row["day_shift"])
        # Exact match first, then normalized
        m = menu_map.get(name) or norm_menu_map.get(_norm(name))
        if m:
            s_salad = (m["salad"] or "").strip()
            s_soup  = (m["soup"]  or "").strip()
            s_main  = (m["main"]  or "").strip()
            s_side  = (m["side"]  or "").strip()
            if s_salad: salads[s_salad] += 1
            if s_soup:  soups[s_soup]   += 1
            if s_main:  mains[s_main]   += 1
            if s_side:  sides[s_side]   += 1
            if s_main or s_side:
                combo = f"{s_main} + {s_side}" if s_main and s_side else (s_main or s_side)
                combos[combo] += 1

    menu_conn.close()
    return {
        "salads": salads, "soups": soups,
        "mains": mains, "sides": sides, "combos": combos,
        "total": len(attending),
    }


def draw_kitchen(output: Path, counts: dict, service_date: date):
    has_fonts = register_fonts()
    fn      = "DV" if has_fonts else "Helvetica"
    fn_bold = "DV-Bold" if has_fonts else "Helvetica-Bold"

    W, H = landscape(letter)
    M = 28
    CW = W - 2 * M

    date_ru = f"{DAYS_RU[service_date.weekday()]}, {service_date.day} {MONTHS_RU[service_date.month]}"
    total   = counts["total"]

    c = canvas.Canvas(str(output), pagesize=landscape(letter))

    # ── Header ──────────────────────────────────────────────────────────
    c.setFillColorRGB(0.12, 0.12, 0.12)
    c.rect(0, H - 48, W, 48, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(fn_bold, 13)
    c.drawCentredString(W / 2, H - 20, f"КУХНЯ — ЗАКАЗ НА {date_ru.upper()}")
    c.setFont(fn, 9)
    c.drawCentredString(W / 2, H - 37, f"Всего: {total} чел.   |   Garden of Joy Adult Day Care")

    # ── 3 columns ───────────────────────────────────────────────────────
    col_widths = [CW * 0.20, CW * 0.20, CW * 0.60]
    col_x      = [M, M + col_widths[0], M + col_widths[0] + col_widths[1]]

    # Build sections in Russian order: САЛАТЫ, СУПЫ, ГЛАВНОЕ + ГАРНИР
    sections = [
        ("САЛАТЫ",           counts["salads"], col_widths[0], col_x[0]),
        ("СУПЫ",             counts["soups"],  col_widths[1], col_x[1]),
        ("ГЛАВНОЕ + ГАРНИР", counts["combos"], col_widths[2], col_x[2]),
    ]

    for title, items, cw, cx in sections:
        y = H - 60
        # Section header
        c.setFillColorRGB(0.20, 0.35, 0.65)
        c.rect(cx + 2, y - 16, cw - 4, 18, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont(fn_bold, 10)
        c.drawCentredString(cx + cw / 2, y - 9, title)
        y -= 20

        c.setFont(fn, 8)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        section_total = sum(items.values())
        c.drawCentredString(cx + cw / 2, y - 6, f"Заказано: {section_total} из {total} чел.")
        y -= 12

        for i, (item, cnt) in enumerate(sorted(items.items(), key=lambda x: -x[1])):
            if y < 40:
                break
            # Alternating row color
            if i % 2 == 0:
                c.setFillColorRGB(0.94, 0.96, 1.0)
            else:
                c.setFillColorRGB(1, 1, 1)
            c.rect(cx + 2, y - 13, cw - 4, 14, fill=1, stroke=0)
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.setLineWidth(0.5)
            c.rect(cx + 2, y - 13, cw - 4, 14, fill=0, stroke=1)

            # Item name
            c.setFillColorRGB(0, 0, 0)
            fs = 8.5
            while stringWidth(item, fn, fs) > cw - 28 and fs > 7:
                fs -= 0.3
            c.setFont(fn, fs)
            c.drawString(cx + 5, y - 10, item)

            # Count
            c.setFont(fn_bold, 10)
            c.setFillColorRGB(0.12, 0.35, 0.65)
            c.drawRightString(cx + cw - 6, y - 10, str(cnt))
            y -= 14

    # ── Footer ───────────────────────────────────────────────────────────
    c.setFillColorRGB(0.12, 0.12, 0.12)
    c.rect(0, 0, W, 22, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(fn, 7)
    c.drawCentredString(W / 2, 7, ADDR_FOOTER)

    c.save()
    return str(output)


def generate(service_date: date, db_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = fetch_kitchen_counts(db_path, service_date)
    fname  = output_dir / f"Kitchen_{service_date.strftime('%a_%b%d')}.pdf"
    out = draw_kitchen(fname, counts, service_date)
    print(f"  ✅ {out} ({counts['total']} чел.)")
    return fname, counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    service_date = date.fromisoformat(args.date) if args.date else next_business_day(date.today())
    print(f"\n{'='*60}\n КУХНЯ — {service_date}\n{'='*60}")
    generate(service_date, Path(args.db), Path(args.output_dir))
    print(f"{'='*60}\n")
