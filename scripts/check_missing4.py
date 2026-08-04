#!/usr/bin/env python3
"""Check DB state for the 4 missing-order clients on their scheduled days."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
p.row_factory = sqlite3.Row
for name, date in [('Elbert Milla', '2026-08-04'), ('Volov Boris', '2026-08-04'),
                   ('Chupikova Elvira', '2026-08-05'), ('Makaron Khaya', '2026-08-05')]:
    print(f'\n=== {name} on {date} ===')
    rows = p.execute("SELECT * FROM client_menus WHERE client_name=? AND menu_date=?",
                     (name, date)).fetchall()
    if not rows:
        print('  NO ROW in DB')
        # what rows do they have this week?
        hist = p.execute("SELECT menu_date, day_code, salad, soup, main, side, source_sheet FROM client_menus "
                         "WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date",
                         (name,)).fetchall()
        for h in hist:
            print(f"  {h['menu_date']} {h['day_code']}: {h['salad']}|{h['soup']}|{h['main']}|{h['side']} [{h['source_sheet']}]")
    else:
        for r in rows:
            print(f"  {r['menu_date']} S{r['shift']} {r['day_code']}: {r['salad']}|{r['soup']}|{r['main']}|{r['side']} [{r['source_sheet']}]")
p.close()
