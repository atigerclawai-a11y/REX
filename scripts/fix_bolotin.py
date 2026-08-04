#!/usr/bin/env python3
"""Insert Bolotin Marina's Wednesday row from her real history (both DBs)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    cur = con.cursor()
    # check if row exists first
    n = cur.execute("""SELECT COUNT(*) FROM client_menus
        WHERE client_name='Bolotin Marina' AND menu_date='2026-08-05'""").fetchone()[0]
    if n:
        cur.execute("""UPDATE client_menus SET salad='Салат из баклажан', soup='Куриный суп',
            main='Дорадо запеченая', side='Паста', source_sheet='last_order_fallback'
            WHERE client_name='Bolotin Marina' AND menu_date='2026-08-05'""")
        print(f'{db.split("/")[-1]}: updated existing row')
    else:
        cur.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Bolotin Marina', '2026-08-05', 'W', '2',
            'Салат из баклажан', 'Куриный суп', 'Дорадо запеченая', 'Паста', 'last_order_fallback')""")
        print(f'{db.split("/")[-1]}: inserted row')
    con.commit()
    con.close()
