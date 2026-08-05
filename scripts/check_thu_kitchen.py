#!/usr/bin/env python3
"""Check Thursday kitchen data: plates per source, any gaps/house needing fix."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('=== THU Aug6 attendance ===')
for shift in (1, 2):
    n = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=?", (shift,)).fetchone()[0]
    print(f'  S{shift}: {n}')

print('\n=== THU plates by source ===')
for d in ['2026-08-06']:
    for r in p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
        WHERE menu_date=? GROUP BY 1 ORDER BY 2 DESC""", (d,)):
        print(f'  {r[0]}: {r[1]}')

print('\n=== THU house_standard clients (17) — fixable? ===')
for r in p.execute("""SELECT client_name, shift FROM client_menus
    WHERE menu_date='2026-08-06' AND source_sheet='house_standard' ORDER BY shift, client_name"""):
    print(f'  {r[0]} S{r[1]}')
a.close()
p.close()
