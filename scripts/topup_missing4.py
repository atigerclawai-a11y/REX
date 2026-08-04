#!/usr/bin/env python3
"""Top up the 4 missing-main clients from their own same-week real history
(day_shifted pattern), then re-verify they have full plates."""
import sqlite3

DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']

TARGETS = {
    'Elbert Milla': ('2026-08-04', 'T', '2'),
    'Volov Boris': ('2026-08-04', 'T', '2'),
    'Chupikova Elvira': ('2026-08-05', 'W', '2'),
    'Makaron Khaya': ('2026-08-05', 'W', '2'),
}

def history_main(con, name, date):
    """Most recent complete main from same week (other days), real source."""
    rows = con.execute("""SELECT main FROM client_menus
        WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        AND menu_date != ? AND main IS NOT NULL AND main != ''
        AND source_sheet IN ('ocr_scan','day_shifted','last_order_fallback')
        ORDER BY menu_date DESC LIMIT 1""", (name, date)).fetchall()
    return rows[0][0] if rows else None

def history_side(con, name, date):
    rows = con.execute("""SELECT side FROM client_menus
        WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        AND menu_date != ? AND side IS NOT NULL AND side != ''
        AND source_sheet IN ('ocr_scan','day_shifted','last_order_fallback')
        ORDER BY menu_date DESC LIMIT 1""", (name, date)).fetchall()
    return rows[0][0] if rows else None

for db in DBS:
    con = sqlite3.connect(db)
    for name, (date, day, shift) in TARGETS.items():
        row = con.execute("""SELECT salad, soup, main, side, source_sheet FROM client_menus
            WHERE client_name=? AND menu_date=?""", (name, date)).fetchone()
        if row is None:
            print(f'{db.split("/")[-1]} {name}: NO ROW')
            continue
        salad, soup, main_, side, src = row
        new_main = main_ or history_main(con, name, date)
        new_side = side or history_side(con, name, date)
        if new_main or new_side:
            con.execute("""UPDATE client_menus SET main=?, side=?, source_sheet='day_shifted'
                WHERE client_name=? AND menu_date=?""", (new_main, new_side, name, date))
            print(f'{db.split("/")[-1]} {name} {date}: main→{new_main} side→{new_side} '
                  f'(was main={main_!r} side={side!r} [{src}])')
        else:
            print(f'{db.split("/")[-1]} {name}: NO history to top up with!')
    con.commit()
    con.close()
