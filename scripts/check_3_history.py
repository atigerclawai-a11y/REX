#!/usr/bin/env python3
"""Check real Wednesday history for the 3 remaining garbage clients."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Minogina Ninel', 'Umanskaya Yelena', 'Zhelabovska Nadia']:
    print(f'\n=== {name} ===')
    for r in con.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? ORDER BY menu_date DESC LIMIT 8""", (name,)):
        print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
con.close()
