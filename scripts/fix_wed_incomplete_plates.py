#!/usr/bin/env python3
"""Fix 9 incomplete Wednesday plates: top up missing salad/soup/side from each
client's own most recent COMPLETE same-shift real order. Preserves OCR-read cells."""
import sqlite3

DATE = '2026-08-05'
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']

# name -> shift of the incomplete row
TARGETS = {
    'Gorodetskaya Ninel': '1', 'Lebedenko Valentyna': '1',
    'Gutkina Lyudmila': '2', 'Starodubets Valentina': '2',
    'Glukhova Shavelina': '2', 'Bass Khana': '2',
    'Dranikov Berta': '2', 'Ruvinskaya Natalia': '2', 'Maglakelidze Mzia': '2',
}

REAL_SOURCES = "('ocr_scan','day_shifted','last_order_fallback','drive_sync')"


def get_history(con, name, shift):
    """Most recent COMPLETE same-shift real row before Aug 5."""
    return con.execute(f"""
        SELECT salad, soup, main, side FROM client_menus
        WHERE client_name=? AND shift=? AND menu_date < ?
          AND salad != '' AND soup != '' AND main != '' AND side != ''
          AND source_sheet IN {REAL_SOURCES}
        ORDER BY menu_date DESC LIMIT 1""", (name, shift, DATE)).fetchone()


for db in DBS:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    for name, shift in TARGETS.items():
        cur = con.execute("""SELECT salad, soup, main, side FROM client_menus
            WHERE menu_date=? AND client_name=? AND shift=?""", (DATE, name, shift)).fetchone()
        if cur is None:
            print(f'{db.split("/")[-1]} {name}: no row at all')
            continue
        salad, soup, main_, side = cur['salad'], cur['soup'], cur['main'], cur['side']
        missing = [not salad, not soup, not main_, not side]
        if not any(missing):
            continue  # already complete
        hist = get_history(con, name, shift)
        if hist is None:
            print(f'{db.split("/")[-1]} {name}: NO complete history to top up!')
            continue
        h = dict(hist)
        new_salad = salad or h['salad']
        new_soup = soup or h['soup']
        new_main = main_ or h['main']
        new_side = side or h['side']
        con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
            source_sheet=CASE WHEN source_sheet='ocr_scan' THEN 'day_shifted' ELSE source_sheet END
            WHERE menu_date=? AND client_name=? AND shift=?""",
            (new_salad, new_soup, new_main, new_side, DATE, name, shift))
        print(f'{db.split("/")[-1]} {name} S{shift}: {salad!r}|{soup!r}|{main_!r}|{side!r} → '
              f'{new_salad}|{new_soup}|{new_main}|{new_side}')
    con.commit()
    con.close()
print('\nBoth DBs updated. Orders JSON needs rebuild.')
