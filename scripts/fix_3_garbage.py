#!/usr/bin/env python3
"""Fix the 3 remaining garbage rows from their real Wednesday history (both DBs)."""
import sqlite3

FIXES = {
    'Umanskaya Yelena': ('Квашеная капуста', 'Борщ красный', 'Поперечка', 'Картошка фри'),
    'Zhelabovska Nadia': ('Оливье', 'Грибной суп', 'Салмон', 'Картошка'),
    'Minogina Ninel': ('Салат Днестр', 'Харчо', 'Блины с мясом', 'Гречка'),
}

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, (sal, sup, main_, side) in FIXES.items():
        c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
            source_sheet='last_order_fallback'
            WHERE client_name=? AND menu_date='2026-08-05'""",
            (sal, sup, main_, side, name))
        print(f'{db.split("/")[-1]} {name}: {c.rowcount} row fixed')
    con.commit()
    con.close()
