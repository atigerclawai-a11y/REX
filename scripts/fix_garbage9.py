#!/usr/bin/env python3
"""Fix the 9 Wed garbage cells re-introduced by the 17:12 cron (both DBs).
Real orders from each client's history (verified earlier today)."""
import sqlite3

FIXES = [
    # (client, date, salad, soup, main, side)
    ('Zhelabovska Nadia', '2026-08-05', 'Оливье', 'Грибной суп', 'Салмон', 'Картошка'),
    ('Umanskaya Yelena', '2026-08-05', 'Квашеная капуста', 'Борщ красный', 'Поперечка', 'Картошка фри'),
    ('Kormov Feliks', '2026-08-05', 'Винегрет', 'Гороховый суп', 'Поперечка', 'Гречка'),
    ('Gamkrelidze Mikhail', '2026-08-05', 'Сало', 'Гороховый суп', 'Свиная отбивная', 'Картошка'),
    ('Minogina Ninel', '2026-08-05', 'Салат Днестр', 'Харчо', 'Блины с мясом', 'Гречка'),
]

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, date, sal, sup, main_, side in FIXES:
        c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?,
            source_sheet='last_order_fallback'
            WHERE client_name=? AND menu_date=?""",
            (sal, sup, main_, side, name, date))
        print(f'{db.split("/")[-1]} {name}: {c.rowcount} row fixed')
    con.commit()
    con.close()
