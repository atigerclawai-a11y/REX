#!/usr/bin/env python3
"""Dovgalyuk Zelda: check her history — why house_standard?"""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('=== Dovgalyuk Zelda recent history ===')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Dovgalyuk Zelda'
    ORDER BY menu_date DESC LIMIT 10"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
