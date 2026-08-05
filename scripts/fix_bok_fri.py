#!/usr/bin/env python3
"""Fix Bok Lyudmila Fri shift: plate S1 → S2 (her actual shift day_F_actual=2)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # check if S2 row exists already (would collide)
    s2 = con.execute("""SELECT COUNT(*) FROM client_menus
        WHERE client_name='Bok Lyudmila' AND menu_date='2026-08-07' AND shift=2""").fetchone()[0]
    if s2:
        # delete the S1 duplicate
        c = con.execute("""DELETE FROM client_menus
            WHERE client_name='Bok Lyudmila' AND menu_date='2026-08-07' AND shift=1""")
        print(f'{db.split("/")[-1]}: deleted S1 dup, S2 row exists ({c.rowcount})')
    else:
        c = con.execute("""UPDATE client_menus SET shift=2
            WHERE client_name='Bok Lyudmila' AND menu_date='2026-08-07'""")
        print(f'{db.split("/")[-1]}: {c.rowcount} row shift→2')
    con.commit()
    con.close()
