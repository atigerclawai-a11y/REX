#!/usr/bin/env python3
"""Check + top up Shumaeva Anna (W S1) + Gamkrelidze Mikhail (W S2) from their
own real orders."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Shumaeva Anna', 'Gamkrelidze Mikhail']:
    print(f'=== {name} ===')
    for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date='2026-08-05'""", (name,)):
        print(f'  TH row: {r[3]}|{r[4]}|{r[5]}|{r[6]} S{r[2]} [{r[7]}]')
    h = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND main != '' AND main NOT LIKE '%заказ не размещен%'
        AND source_sheet NOT IN ('house_standard','no_order_flag')
        ORDER BY ABS(julianday(menu_date)-julianday('2026-08-05')) LIMIT 1""", (name,)).fetchone()
    if h:
        print(f'  history: {h[0]} {h[1]}: {h[2]}|{h[3]}|{h[4]}|{h[5]} [{h[6]}]')
p.close()
