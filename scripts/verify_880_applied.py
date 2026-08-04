#!/usr/bin/env python3
"""Verify: are doc006880's 31 forms already applied to the DB as ocr_scan?"""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
p.row_factory = sqlite3.Row

print('=== week-31 ocr_scan rows ===')
total = p.execute("""SELECT COUNT(*) FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan'""").fetchone()[0]
print(f'total ocr_scan rows: {total}')
rows = p.execute("""SELECT client_name, menu_date, salad, soup, main, side
    FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND source_sheet='ocr_scan' ORDER BY client_name LIMIT 12""").fetchall()
for r in rows:
    print(f"  {r['client_name']} {r['menu_date']}: {r['salad']} | {r['soup']} | {r['main']} | {r['side']}")

# known doc006880 vision-recovered names from the skill
KNOWN_880_W31 = ['Grabovskaya Larisa', 'Portnov Naum', 'Starikov Brayna', 'Yakobzon Rivka',
                 'Shulkin Faina', 'Gadilova Nina', 'Kruglov Viktor']
print('\n=== known 880 clients in DB for week 31? ===')
for name in KNOWN_880_W31:
    cnt = p.execute("""SELECT COUNT(*) FROM client_menus
        WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'""",
        (name,)).fetchone()[0]
    print(f'  {name}: {cnt} rows')
p.close()
