#!/usr/bin/env python3
"""Check REX copy's 3 remaining cells + compare with Documents copy."""
import sqlite3

REX = '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db'
DOC = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

for db, tag in [(REX, 'REX'), (DOC, 'DOC')]:
    con = sqlite3.connect(db)
    print(f'=== {tag} ===')
    for r in con.execute("""SELECT client_name, menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE menu_date='2026-08-05'
        AND (salad IN ('Борщ','Рыба','Олимп','Б') OR soup IN ('Борщ','Рыба','Олимп','Б')
          OR main IN ('S','Борщ','Рыба','Олимп') OR side IN ('S','FF','MP'))
        ORDER BY client_name"""):
        print(f'  {r[0]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
    con.close()
