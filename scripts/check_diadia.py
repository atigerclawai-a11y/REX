#!/usr/bin/env python3
"""Fix Diadia Valentina Aug 5: salad='Борщ' is a miscategorized soup.
Find her real salad from history."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
p.row_factory = sqlite3.Row
print('current row:')
for r in p.execute("SELECT * FROM client_menus WHERE client_name='Diadia Valentina' AND menu_date='2026-08-05'"):
    print(f"  {r['menu_date']} {r['day_code']}: {r['salad']}|{r['soup']}|{r['main']}|{r['side']} [{r['source_sheet']}]")
print('\nher week + history salads:')
for r in p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Diadia Valentina'
    AND (menu_date BETWEEN '2026-08-03' AND '2026-08-07' OR menu_date BETWEEN '2026-07-27' AND '2026-08-02')
    ORDER BY menu_date DESC LIMIT 10"""):
    print(f"  {r['menu_date']} {r['day_code']}: {r['salad']}|{r['soup']}|{r['main']}|{r['side']} [{r['source_sheet']}]")
p.close()
