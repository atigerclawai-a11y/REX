#!/usr/bin/env python3
"""Audit: per-day fallback counts for the week + clients with NO real picks at all."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('=== Aug 3-7 by source (per day) ===')
for d in ['2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06', '2026-08-07']:
    rows = dict(p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
        WHERE menu_date=? GROUP BY 1 ORDER BY 2 DESC""", (d,)).fetchall())
    fb = rows.get('last_order_fallback', 0)
    house = rows.get('house_standard', 0)
    ocr = rows.get('ocr_scan', 0)
    shifted = rows.get('day_shifted', 0)
    print(f'  {d}: ocr={ocr} shifted={shifted} fallback={fb} house={house}  '
          f'→ non-real={fb + house}')

print('\n=== clients with ZERO ocr_scan rows all week (true no-form clients) ===')
noform = p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')
    ORDER BY client_name""").fetchall()
print(f'  count: {len(noform)}')
for r in noform:
    print(f'    {r[0]}')
p.close()
