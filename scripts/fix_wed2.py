#!/usr/bin/env python3
"""Fix Bialkovska Maria Wed shift → 1, insert Bolotin Marina Wed S2 row (both DBs)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # Bialkovska: shift 2 → 1
    c = con.execute("""UPDATE client_menus SET shift=1
        WHERE client_name='Bialkovska Maria' AND menu_date='2026-08-05'""")
    print(f'{db.split("/")[-1]} Bialkovska Maria W: {c.rowcount} row shift→1')
    # Bolotin: insert Wed row from her real history
    n = con.execute("""SELECT COUNT(*) FROM client_menus
        WHERE client_name='Bolotin Marina' AND menu_date='2026-08-05'""").fetchone()[0]
    if n:
        c = con.execute("""UPDATE client_menus SET salad='Салат из баклажан', soup='Куриный суп',
            main='Дорадо запеченая', side='Паста', source_sheet='last_order_fallback', shift=2
            WHERE client_name='Bolotin Marina' AND menu_date='2026-08-05'""")
        print(f'{db.split("/")[-1]} Bolotin Marina W: updated {c.rowcount} row')
    else:
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Bolotin Marina', '2026-08-05', 'W', '2',
            'Салат из баклажан', 'Куриный суп', 'Дорадо запеченая', 'Паста', 'last_order_fallback')""")
        print(f'{db.split("/")[-1]} Bolotin Marina W: inserted row')
    con.commit()
    con.close()
