#!/usr/bin/env python3
"""Check current attendance for WED (Aug 5) and THU (Aug 6) + their orders."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('=== ACTUALS ===')
for col, label in [('day_W_actual', 'WED Aug5'), ('day_TH_actual', 'THU Aug6')]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {label}: S1={s1} S2={s2}')

print('\n=== PLATES (week) ===')
for d in ['2026-08-05', '2026-08-06']:
    rows = p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
        WHERE menu_date=? GROUP BY 1 ORDER BY 2 DESC""", (d,)).fetchall()
    print(f'  {d}: {rows}')
a.close()
p.close()
