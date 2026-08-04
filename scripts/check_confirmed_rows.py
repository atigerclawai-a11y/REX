#!/usr/bin/env python3
"""Verify: do confirmed clients like Shefer Bella have ocr_scan rows this week?"""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Shefer Bella', 'Uchitel Vilyam', 'Malkiyev Boris', 'Shklovsky Gita',
             'Khashimova Zukhra', 'Finkelshteyn Anya', 'Bok Lyudmila']:
    print(f'\n=== {name} ===')
    rows = p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
        ORDER BY menu_date""", (name,)).fetchall()
    if not rows:
        print('  NO ROWS at all this week')
    for r in rows:
        print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
