#!/usr/bin/env python3
"""Fix client_menus.shift to match auth day_*_actual for Aug 4/5 (both DBs)."""
import sqlite3

p_dbs = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
         '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

fixed = 0
for db in p_dbs:
    p = sqlite3.connect(db)
    for date, col in [('2026-08-04', 'day_T_actual'), ('2026-08-05', 'day_W_actual')]:
        rows = p.execute("""SELECT rowid, client_name, day_code, shift FROM client_menus
            WHERE menu_date=?""", (date,)).fetchall()
        for rid, name, dc, shift in rows:
            auth = a.execute(f"SELECT {col} FROM clients WHERE name=?", (name,)).fetchone()
            if auth is None or auth[0] not in (1, 2):
                continue
            if int(shift) != auth[0]:
                p.execute("UPDATE client_menus SET shift=? WHERE rowid=?", (auth[0], rid))
                fixed += 1
    p.commit()
    p.close()
    print(f'{db.split("/")[-1]}: fixed {fixed} shift mismatches')
a.close()
