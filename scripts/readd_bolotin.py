#!/usr/bin/env python3
"""Re-add Bolotin Marina Wed S2 plate (kept getting deleted by sync cycle)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name='Bolotin Marina' AND menu_date='2026-08-05'").fetchone()[0]
    if n:
        c = con.execute("""UPDATE client_menus SET salad='Салат из баклажан', soup='Куриный суп',
            main='Дорадо запеченая', side='Паста', source_sheet='last_order_fallback', shift=2
            WHERE client_name='Bolotin Marina' AND menu_date='2026-08-05'""")
        print(f'{db.split("/")[-1]}: updated {c.rowcount} row')
    else:
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Bolotin Marina', '2026-08-05', 'W', '2',
            'Салат из баклажан', 'Куриный суп', 'Дорадо запеченая', 'Паста', 'last_order_fallback')""")
        print(f'{db.split("/")[-1]}: inserted row')
    con.commit()
    con.close()
