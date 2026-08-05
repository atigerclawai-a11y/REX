#!/usr/bin/env python3
"""Check the 5 Thu S1 gap clients: any history to fill from?"""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Breytman Polina', 'Coniglio Vera', 'Dmitriyeva Tamara', 'Epshteyn Yelizaveta', 'Firdman Mark']:
    print(f'\n=== {name} ===')
    # any TH history
    r = p.execute("""SELECT menu_date, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND day_code='TH' AND main != ''
        AND main NOT LIKE '%заказ не размещен%' AND source_sheet != 'house_standard'
        ORDER BY menu_date DESC LIMIT 2""", (name,)).fetchall()
    if r:
        for row in r:
            print(f'  TH: {row[0]}: {row[1]}|{row[2]}|{row[3]}|{row[4]} [{row[5]}]')
    else:
        r2 = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
            FROM client_menus WHERE client_name=? AND main != ''
            AND main NOT LIKE '%заказ не размещен%' AND source_sheet != 'house_standard'
            ORDER BY menu_date DESC LIMIT 2""", (name,)).fetchall()
        for row in r2:
            print(f'  ANY: {row[0]} {row[1]}: {row[2]}|{row[3]}|{row[4]}|{row[5]} [{row[6]}]')
        if not r2:
            print('  NO HISTORY AT ALL')
p.close()
