#!/usr/bin/env python3
"""Top up Bok Lyudmila Wed main/side from her own Wednesday history (both DBs)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    c = con.execute("""UPDATE client_menus SET main='Блины с творогом', side='Гречка',
        source_sheet='day_shifted'
        WHERE client_name='Bok Lyudmila' AND menu_date='2026-08-05'
        AND (main IS NULL OR main='')""")
    print(f'{db.split("/")[-1]}: {c.rowcount} row topped up')
    con.commit()
    con.close()
