#!/usr/bin/env python3
"""Check Epshteyn Yelizaveta + Buslayeva Alisa Thursday rows."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
p.row_factory = sqlite3.Row
for name in ['Epshteyn Yelizaveta', 'Buslayeva Alisa']:
    print(f'\n=== {name} ===')
    for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-07-27' AND '2026-08-07'
        ORDER BY menu_date DESC LIMIT 6""", (name,)):
        print(f"  {r['menu_date']} {r['day_code']}: {r['salad']}|{r['soup']}|{r['main']}|{r['side']} [{r['source_sheet']}]")
p.close()
