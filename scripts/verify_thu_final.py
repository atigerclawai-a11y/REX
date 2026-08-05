#!/usr/bin/env python3
"""Verify Thu fully covered + no garbage, then generate kitchen sheet."""
import sqlite3
import subprocess

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('=== THU coverage ===')
for shift in (1, 2):
    sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual=?", (shift,))]
    ph = ','.join('?' * len(sched))
    have = set(r[0] for r in p.execute(f"SELECT client_name FROM client_menus WHERE menu_date='2026-08-06' AND shift=? AND client_name IN ({ph})", (shift, *sched)))
    gaps = [n for n in sched if n not in have]
    print(f'  S{shift}: {len(sched)} sched / {len(sched)-len(gaps)} plates / {len(gaps)} gaps {gaps}')

print('\n=== THU sources ===')
for r in p.execute("SELECT source_sheet, COUNT(*) FROM client_menus WHERE menu_date='2026-08-06' GROUP BY 1 ORDER BY 2 DESC"):
    print(f'  {r[0]}: {r[1]}')
a.close()
p.close()

print('\n=== garbage check ===')
r = subprocess.run(['python3', '/Users/mainsobhelper/Desktop/REX/scripts/find_garbage_dishes.py'],
                   capture_output=True, text=True, cwd='/Users/mainsobhelper/Desktop/REX',
                   env={'PATH': '/Users/mainsobhelper/.rex-venv/bin:/usr/bin:/bin'})
for line in r.stdout.splitlines():
    if 'non-canonical' in line:
        print(f'  {line.strip()}')
