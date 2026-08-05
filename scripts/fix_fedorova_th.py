#!/usr/bin/env python3
"""Fedorova Olga TH: replace house_standard with her own recent order (both DBs)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    c = con.execute("""UPDATE client_menus SET salad='Салат весенний', soup='Борщ красный',
        main='Блины с мясом', side='Пюре', source_sheet='last_order_fallback'
        WHERE client_name='Fedorova Olga' AND menu_date='2026-08-06'""")
    print(f'{db.split("/")[-1]} Fedorova Olga TH: {c.rowcount} row → own order')
    con.commit()
    con.close()
