#!/usr/bin/env python3
"""Delete Dovgalyuk Zelda's stray S1 house_standard Thu row (her real S2 row exists).
Check her actual shift first."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
a = sqlite3.connect(AUTH)
r = a.execute("SELECT name, day_TH_actual FROM clients WHERE name='Dovgalyuk Zelda'").fetchone()
print(f'auth: {r}')
a.close()

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    c = con.execute("""DELETE FROM client_menus
        WHERE client_name='Dovgalyuk Zelda' AND menu_date='2026-08-06'
        AND source_sheet='house_standard'""")
    print(f'{db.split("/")[-1]}: deleted {c.rowcount} house row')
    con.commit()
    con.close()
