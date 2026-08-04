#!/usr/bin/env python3
"""Gap details: which clients have NO plate + house-standard clients."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

DAYS = [('2026-08-03', 'day_M_actual', 'MON'), ('2026-08-04', 'day_T_actual', 'TUE'),
        ('2026-08-05', 'day_W_actual', 'WED'), ('2026-08-06', 'day_TH_actual', 'THU'),
        ('2026-08-07', 'day_F_actual', 'FRI')]

print('=== GAPS (scheduled but NO plate) ===')
for date, col, label in DAYS:
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        if not sched:
            continue
        ph = ','.join('?' * len(sched))
        have = set(r[0] for r in p.execute(f"SELECT client_name FROM client_menus WHERE menu_date=? AND shift=? AND client_name IN ({ph})", (date, shift, *sched)))
        gaps = [n for n in sched if n not in have]
        if gaps:
            print(f'  {label} S{shift} ({len(gaps)}): {", ".join(sorted(gaps))}')

print('\n=== HOUSE STANDARD clients (generic plate) ===')
for date, col, label in DAYS:
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        if not sched:
            continue
        ph = ','.join('?' * len(sched))
        hs = [r[0] for r in p.execute(f"SELECT client_name FROM client_menus WHERE menu_date=? AND shift=? AND source_sheet='house_standard' AND client_name IN ({ph})", (date, shift, *sched))]
        if hs:
            print(f'  {label} S{shift} ({len(hs)}): {", ".join(sorted(hs))}')
a.close()
p.close()
