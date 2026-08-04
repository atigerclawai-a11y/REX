#!/usr/bin/env python3
"""Confirm: house_standard clients' real orders exist but in different shift or
as excluded source. Show shift per history row."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Sekh Stefaniia', 'Shteyman Faina', 'Britavskaya Sofiya', 'Shadkhan Bella',
             'Safonov Anatoliy']:
    print(f'\n=== {name} ===')
    for r in p.execute("""SELECT menu_date, shift, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? ORDER BY menu_date DESC LIMIT 8""", (name,)):
        print(f'  {r[0]} S{r[1]} {r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
