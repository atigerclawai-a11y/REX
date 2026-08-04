#!/usr/bin/env python3
"""Delete house_standard rows for the 6 clients on Tue/Wed so fill re-derives
their most recent real order (post-fix)."""
import sqlite3

HOUSE_CLIENTS = ['Sekh Stefaniia', 'Shteyman Faina', 'Britavskaya Sofiya', 'Shadkhan Bella',
                 'Safonov Anatoliy']

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name in HOUSE_CLIENTS:
        c = con.execute("""DELETE FROM client_menus WHERE client_name=?
            AND menu_date IN ('2026-08-04','2026-08-05') AND source_sheet='house_standard'""", (name,))
        print(f'{db.split("/")[-1]} {name}: deleted {c.rowcount} house rows')
    con.commit()
    con.close()
