#!/usr/bin/env python3
"""Verify Kormova Wed plate exists in both DBs."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    rows = con.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name='Kormova Lyubov'
        AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date""").fetchall()
    print(f'{db.split("/")[-1]}:')
    for r in rows:
        print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
    con.close()
