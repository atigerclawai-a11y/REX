#!/usr/bin/env python3
"""Find clients where DB row shift != auth day_*_actual shift for Aug 4/5."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

for date, col in [('2026-08-04', 'day_T_actual'), ('2026-08-05', 'day_W_actual')]:
    print(f'\n=== {date} (auth {col}) ===')
    rows = p.execute("""SELECT client_name, day_code, shift, source_sheet FROM client_menus
        WHERE menu_date=?""", (date,)).fetchall()
    seen = set()
    for name, dc, shift, src in rows:
        if (name, dc) in seen:
            continue
        seen.add((name, dc))
        auth = a.execute(f"SELECT {col} FROM clients WHERE name=?", (name,)).fetchone()
        if auth is None or auth[0] not in (1, 2):
            continue
        if int(shift) != auth[0]:
            print(f'  MISMATCH {name} {dc}: row shift={shift} vs auth {col}={auth[0]} [{src}]')
p.close()
a.close()
