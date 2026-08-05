#!/usr/bin/env python3
"""Verify Fedorova Olga's final state: DB rows + orders JSON for Mon/Thu."""
import json
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('=== Fedorova Olga DB rows (week) ===')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Fedorova Olga'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()

orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
for d in ['2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06', '2026-08-07']:
    if 'Fedorova Olga' in orders.get(d, {}):
        print(f'JSON {d}: {orders[d]["Fedorova Olga"]}')
