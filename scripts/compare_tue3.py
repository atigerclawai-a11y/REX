#!/usr/bin/env python3
"""Compare Tue rows for Neginis/Shkolnik/Zabizhin between DB copies."""
import sqlite3

for db, tag in [('/Users/mainsobhelper/Desktop/REX/goj_proprietary.db', 'REX'),
                ('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db', 'DOC')]:
    con = sqlite3.connect(db)
    print(f'=== {tag} ===')
    for name in ['Neginis Rivekka', 'Shkolnik Betya', 'Zabizhin Grigoriy']:
        for r in con.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
            FROM client_menus WHERE client_name=? AND menu_date='2026-08-04'""", (name,)):
            print(f'  {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
    con.close()
