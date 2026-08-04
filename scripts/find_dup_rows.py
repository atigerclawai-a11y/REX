#!/usr/bin/env python3
"""Find duplicate (client, date, shift) rows that break the UNIQUE constraint."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    p = sqlite3.connect(db)
    print(f'\n=== {db.split("/")[-1]} ===')
    dups = p.execute("""SELECT client_name, menu_date, shift, COUNT(*)
        FROM client_menus WHERE menu_date IN ('2026-08-04','2026-08-05')
        GROUP BY client_name, menu_date, shift HAVING COUNT(*) > 1""").fetchall()
    for d in dups:
        print(f'  DUP {d[0]} {d[1]} S{d[2]}: {d[3]} rows')
        for r in p.execute("""SELECT rowid, day_code, salad, soup, main, side, source_sheet
            FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?""",
            (d[0], d[1], d[2])):
            print(f'    rowid={r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
    p.close()
