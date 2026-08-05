#!/usr/bin/env python3
"""Check the 5 Thu-missing clients: DB rows this week + history."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Chepizhko Raya', 'Dranikov Berta', 'Drochik Oleg', 'Makaron Khaya', 'Verbitskaya Svetlana']:
    print(f'\n=== {name} ===')
    rows = p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date='2026-08-06'""", (name,)).fetchall()
    if rows:
        for r in rows:
            print(f'  TH: {r[3]}|{r[4]}|{r[5]}|{r[6]} S{r[2]} [{r[7]}]')
    else:
        print('  NO Thu row')
    # history
    h = p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date < '2026-08-06'
        AND main != '' AND main NOT LIKE '%заказ не размещен%'
        ORDER BY menu_date DESC LIMIT 2""", (name,)).fetchall()
    for r in h:
        print(f'  HIST {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
