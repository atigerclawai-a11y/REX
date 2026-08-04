#!/usr/bin/env python3
"""Find clients with rows in BOTH shifts for the same date (cross-shift dup)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    p = sqlite3.connect(db)
    print(f'\n=== {db.split("/")[-1]} ===')
    rows = p.execute("""SELECT client_name, menu_date, day_code, shift, rowid, salad, soup, main, side, source_sheet
        FROM client_menus WHERE menu_date IN ('2026-08-04','2026-08-05')
        ORDER BY client_name, menu_date, day_code""").fetchall()
    by_key = {}
    for r in rows:
        key = (r[0], r[1], r[2])
        by_key.setdefault(key, []).append(r)
    for key, hits in by_key.items():
        shifts = {h[3] for h in hits}
        if len(shifts) > 1:
            print(f'  CROSS-SHIFT {key[0]} {key[1]} {key[2]}:')
            for h in hits:
                print(f'    rowid={h[4]} S{h[3]}: {h[5]}|{h[6]}|{h[7]}|{h[8]} [{h[9]}]')
    p.close()
