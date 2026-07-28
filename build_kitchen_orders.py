#!/usr/bin/env python3
"""
BUILDER — Generate final per-shift kitchen order files.
Takes validated data from goj_proprietary.db (populated by Red + Blue teams).
Aggregates all menu selections by category, filters by attendance,
and saves 4 per-shift markdown files.
"""
import sqlite3
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, date

# Paths
MENU_DB = Path.home() / "Desktop/REX/goj_proprietary.db"
AUTH_DB = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
OUTPUT_DIR = Path.home() / "Desktop/REX/menu_ocr_output"

# ── Normalization maps ──────────────────────────────────────────────────

SALAD_MAP = {
    "вин": "Винегрет",
    "свкл": "Свекла",
    "свекла": "Свекла",
    "баклаж": "Салат из баклажан",
    "салат из баклажан": "Салат из баклажан",
    "ол": "Оливье",
    "оливье": "Оливье",
    "селедка": "Селедка",
    "сало": "Сало",
    "весна": "Салат весенний",
    "салат весенний": "Салат весенний",
    "капуста": "Квашеная капуста",
    "квашеная капуста": "Квашеная капуста",
    "днестр": "Салат Днестр",
    "салат днестр": "Салат Днестр",
    "борщ зеленый": "Борщ зеленый",
    "борщ красный": "Борщ красный",
    "тушеная капуста": "Тушеная капуста",
}

SOUP_MAP = {
    "б": "Борщ красный",
    "борщ красный": "Борщ красный",
    "з.б": "Борщ зеленый",
    "3.б": "Борщ зеленый",
    "борщ зеленый": "Борщ зеленый",
    "кур": "Куриный суп",
    "куриный суп": "Куриный суп",
    "куриныйcyp": "Куриный суп",
    "гриб": "Грибной суп",
    "грибной суп": "Грибной суп",
    "горох": "Гороховый суп",
    "гороховый суп": "Гороховый суп",
    "харчо": "Харчо",
    "овощ": "Овощной суп",
    "овощной cуп": "Овощной суп",
    "овощной суп": "Овощной суп",
}

MAIN_MAP = {
    "s": "Шницель",
    "шницель": "Шницель",
    "чалахач": "Чалахач",
    "котл. кур": "Котлеты куриные",
    "котлеты куриные": "Котлеты куриные",
    "дорадо": "Дорадо запеченая",
    "дорадо запеченая": "Дорадо запеченая",
    "чебуреки": "Чебуреки",
    "табака": "Цыпленок табака",
    "цыпленок табака": "Цыпленок табака",
    "крылья": "Куриные крылышки",
    "куриные крылышки": "Куриные крылышки",
    "терияки": "Курица в терияки",
    "курица в терияки": "Курица в терияки",
    "поперечка": "Поперечка",
    "вар.кар": "Вареники с картошкой",
    "вареники с картошкой": "Вареники с картошкой",
    "св. отбив": "Свиная отбивная",
    "свиная отбивная": "Свиная отбивная",
    "пельмени": "Пельмени",
    "жульен": "Жульен",
    "голубцы": "Голубцы",
    "бл. твор": "Блины с творогом",
    "блины с творогом": "Блины с творогом",
    "бл. мясо": "Блины с мясом",
    "блины с мясом": "Блины с мясом",
    "баса": "Баса с помидорами",
    "баса с помидорами": "Баса с помидорами",
    "гуляш": "Гуляш",
    "фуняш": "Гуляш",   # OCR artifact: Ф→Г error
    "фуляш": "Гуляш",   # OCR artifact
    "фыняш": "Гуляш",   # OCR artifact
    "фолубцы": "Голубцы",  # OCR artifact
    "паста": "Паста",
    "салмон": "Салмон",
    "картошка": "Картошка",
    "картошка по деревенски": "Картошка ПО ДЕРЕВЕНСКИ",
    "картошка фри": "Картошка фри",
}

SIDE_MAP = {
    "гр": "Гречка",
    "гречка": "Гречка",
    "mp": "Пюре",
    "пюре": "Пюре",
    "фасоль": "Стручковая фасоль",
    "стручковая фасоль": "Стручковая фасоль",
    "туш. кап.": "Тушеная капуста",
    "тушеная капуста": "Тушеная капуста",
    "паста": "Паста",
    "картошка": "Картошка",
    "ff": "Картошка фри",
    "картошка фри": "Картошка фри",
}

# ── Helpers ─────────────────────────────────────────────────────────────

def normalize(val, mapping):
    """Normalize a menu value using the mapping, with OCR artifact cleanup."""
    if not val:
        return None
    v = val.strip().lower()
    # Remove OCR noise: trailing punctuation, stray chars
    v = re.sub(r'[\s,.\-—)\]]+$', '', v)
    v = re.sub(r'^[\s,.\-—\[(]+', '', v)
    # Direct lookup
    if v in mapping:
        return mapping[v]
    # Try fuzzy: find best prefix match
    for key, full in mapping.items():
        if v.startswith(key) or key.startswith(v):
            return full
    # Return original if no match (preserve novel items)
    return val.strip().title()


def get_attending(date_str, shift):
    """Get set of client names attending on given date+shift."""
    conn = sqlite3.connect(str(AUTH_DB))
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_codes = ["M", "T", "W", "TH", "F", "Su", "Su"]
    day_col = f"day_{day_codes[dt.weekday()]}_actual"
    rows = conn.execute(
        f"SELECT name FROM clients WHERE active=1 AND {day_col}=?",
        (str(shift),)
    ).fetchall()
    conn.close()
    return set(r[0] for r in rows)


def get_menu_orders(date_str, shift):
    """Get menu orders for given date+shift from goj_proprietary.db."""
    conn = sqlite3.connect(str(MENU_DB))
    rows = conn.execute("""
        SELECT cm.client_name, cm.salad, cm.soup, cm.main, cm.side
        FROM client_menus cm
        WHERE cm.menu_date = ? AND cm.shift = ?
        ORDER BY cm.client_name
    """, (date_str, str(shift))).fetchall()
    conn.close()
    return rows


def ensure_menu_data(date_str, shift):
    """Ensure menu data exists for date. Use fallback from previous week if missing."""
    orders = get_menu_orders(date_str, shift)
    if orders:
        return orders

    # No data — use fallback from 7 days prior
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    from datetime import timedelta
    fallback_date = (dt - timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"  ⚠️  No menu data for {date_str} S{shift} — using fallback from {fallback_date}")

    conn = sqlite3.connect(str(MENU_DB))
    fallback_rows = conn.execute("""
        SELECT client_name, salad, soup, main, side
        FROM client_menus
        WHERE menu_date = ? AND shift = ?
        ORDER BY client_name
    """, (fallback_date, str(shift))).fetchall()
    conn.close()

    if not fallback_rows:
        print(f"  ❌ No fallback data either for {fallback_date} S{shift}")
        return []

    # Insert fallback data for the target date
    conn = sqlite3.connect(str(MENU_DB))
    for row in fallback_rows:
        conn.execute("""
            INSERT OR IGNORE INTO client_menus
            (client_name, menu_date, shift, salad, soup, main, side, source_sheet, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'last_order_fallback', datetime('now'))
        """, (row[0], date_str, str(shift), row[1], row[2], row[3], row[4]))
    conn.commit()
    conn.close()

    return get_menu_orders(date_str, shift)


def aggregate(orders, attending):
    """Aggregate orders by category, filtering to attending clients only."""
    salads = defaultdict(int)
    soups = defaultdict(int)
    mains = defaultdict(int)
    sides = defaultdict(int)
    matched_clients = set()

    for row in orders:
        name, salad, soup, main, side = row
        if name not in attending:
            continue
        matched_clients.add(name)

        s = normalize(salad, SALAD_MAP)
        if s and "заказ не размещен" not in s.lower():
            salads[s] += 1

        sp = normalize(soup, SOUP_MAP)
        if sp and "заказ не размещен" not in sp.lower():
            soups[sp] += 1

        m = normalize(main, MAIN_MAP)
        if m and "заказ не размещен" not in m.lower():
            mains[m] += 1

        sd = normalize(side, SIDE_MAP)
        if sd and "заказ не размещен" not in sd.lower():
            sides[sd] += 1

    return {
        "client_count": len(matched_clients),
        "salads": dict(sorted(salads.items(), key=lambda x: -x[1])),
        "soups": dict(sorted(soups.items(), key=lambda x: -x[1])),
        "mains": dict(sorted(mains.items(), key=lambda x: -x[1])),
        "sides": dict(sorted(sides.items(), key=lambda x: -x[1])),
    }


def total_selections(agg):
    """Total number of item selections across all categories (sum of counts)."""
    return (sum(agg["salads"].values()) +
            sum(agg["soups"].values()) +
            sum(agg["mains"].values()) +
            sum(agg["sides"].values()))


def format_category(name, counts):
    """Format a category section."""
    lines = [f"### {name}"]
    for item, cnt in counts.items():
        lines.append(f"- {cnt}x {item}")
    return "\n".join(lines)


def write_order_file(output_path, date_str, shift, agg):
    """Write the kitchen order markdown file."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = dt.strftime("%A")
    month_day = dt.strftime("%B %d, %Y")

    lines = [
        f"# GOJ Kitchen Order — Shift {shift} {day_name} {month_day}",
        f"## {agg['client_count']} clients • {total_selections(agg)} selections",
        "",
        format_category("SALADS", agg["salads"]),
        "",
        format_category("SOUPS", agg["soups"]),
        "",
        format_category("MAINS", agg["mains"]),
        "",
        format_category("SIDES", agg["sides"]),
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return str(output_path)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [
        ("2026-07-23", 1, "Thu"),
        ("2026-07-23", 2, "Thu"),
        ("2026-07-24", 1, "Fri"),
        ("2026-07-24", 2, "Fri"),
    ]

    for date_str, shift, day_abbr in tasks:
        print(f"Processing {date_str} Shift {shift} ({day_abbr})...")

        # Get attending clients
        attending = get_attending(date_str, shift)
        print(f"  Attending: {len(attending)} clients")

        # Get menu orders (with fallback if missing)
        orders = ensure_menu_data(date_str, shift)
        print(f"  Menu entries: {len(orders)}")

        # Aggregate
        agg = aggregate(orders, attending)
        print(f"  Matched: {agg['client_count']} clients with menus")

        # Write file
        out_name = f"kitchen_order_S{shift}_{day_abbr}_{date_str}.md"
        out_path = OUTPUT_DIR / out_name
        write_order_file(out_path, date_str, shift, agg)
        print(f"  → {out_path}")
        print(f"    Salads: {sum(agg['salads'].values())} | Soups: {sum(agg['soups'].values())} | Mains: {sum(agg['mains'].values())} | Sides: {sum(agg['sides'].values())}")
        print()

    print("Done! Generated 4 kitchen order files in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
