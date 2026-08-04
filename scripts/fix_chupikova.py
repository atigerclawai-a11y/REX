#!/usr/bin/env python3
"""Fix Chupikova Elvira: fill main/side from her own recent Wednesday real orders."""
import sqlite3

MAIN = 'Дорадо запеченая'
SIDE = 'Тушеная капуста'

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    cur = con.execute("""UPDATE client_menus SET main=?, side=?, source_sheet='day_shifted'
        WHERE client_name='Chupikova Elvira' AND menu_date='2026-08-05'""", (MAIN, SIDE))
    print(f'{db.split("/")[-1]}: updated {cur.rowcount} row → {MAIN} + {SIDE}')
    con.commit()
    con.close()
