#!/usr/bin/env python3
"""Dovgalyuk Zelda attends TH S1. Her real order row is in S2 — move to S1.
(Deleting the S1 house row was correct; now fix the S2 row's shift.)"""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # check for S1 row now
    s1 = con.execute("""SELECT COUNT(*) FROM client_menus
        WHERE client_name='Dovgalyuk Zelda' AND menu_date='2026-08-06' AND shift=1""").fetchone()[0]
    s2 = con.execute("""SELECT salad, soup, main, side, source_sheet FROM client_menus
        WHERE client_name='Dovgalyuk Zelda' AND menu_date='2026-08-06' AND shift=2""").fetchone()
    print(f'{db.split("/")[-1]}: S1 rows={s1}, S2 rows={s2}')
    if s2 and not s1:
        # copy S2 → S1 (insert), delete S2
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Dovgalyuk Zelda', '2026-08-06', 'TH', '1', ?, ?, ?, ?, ?)""", s2)
        con.execute("""DELETE FROM client_menus
            WHERE client_name='Dovgalyuk Zelda' AND menu_date='2026-08-06' AND shift=2""")
        print(f'{db.split("/")[-1]}: moved S2→S1')
    elif not s2 and not s1:
        # need to insert fresh
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Dovgalyuk Zelda', '2026-08-06', 'TH', '1',
            'Винегрет', 'Борщ зеленый', 'Гуляш', 'Паста', 'last_order_fallback')""")
        print(f'{db.split("/")[-1]}: inserted S1 row')
    con.commit()
    con.close()
