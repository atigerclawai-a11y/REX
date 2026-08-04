#!/usr/bin/env python3
"""End-to-end verification: DB parity, garbage, plate coverage, sheet files."""
import json
import sqlite3
import os
from datetime import date

print('=' * 62)
print('1. DB PARITY — both goj_proprietary copies')
print('=' * 62)
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
stats = []
for db in DBS:
    p = sqlite3.connect(db)
    n = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'").fetchone()[0]
    bysrc = dict(p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' GROUP BY 1 ORDER BY 2 DESC""").fetchall())
    stats.append((db.split('/')[-1], n, bysrc))
    print(f'{db.split("/")[-1]}: {n} rows {bysrc}')
    p.close()
if stats[0][1] == stats[1][1] and stats[0][2] == stats[1][2]:
    print('PARITY OK — identical row counts and source mix')
else:
    print('⚠️ PARITY DRIFT — investigate')

print('\n' + '=' * 62)
print('2. GARBAGE / LEAKS (all days)')
print('=' * 62)
import subprocess
r = subprocess.run(['python3', 'scripts/find_garbage_dishes.py'], capture_output=True, text=True, cwd='/Users/mainsobhelper/Desktop/REX')
print(r.stdout.strip()[:400])
r2 = subprocess.run(['python3', 'scripts/find_category_leaks.py'], capture_output=True, text=True, cwd='/Users/mainsobhelper/Desktop/REX')
leaks = [l for l in r2.stdout.splitlines() if '←' in l]
print(f'category leaks: {len(leaks)}')

print('\n' + '=' * 62)
print('3. PLATE COVERAGE — every scheduled client has a plate')
print('=' * 62)
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
a = sqlite3.connect(AUTH)
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
for day, col, dt in [('T', 'day_T_actual', '2026-08-04'), ('W', 'day_W_actual', '2026-08-05')]:
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        have = []
        for name, shifts in orders.get(dt, {}).items():
            for sh, o in shifts.items():
                if int(sh) == shift:
                    have.append(name)
        missing = [n for n in sched if n not in have]
        status = 'OK' if not missing else f'MISSING {missing}'
        print(f'{dt} S{shift}: scheduled {len(sched)} / plates {len(have)} → {status}')
a.close()

print('\n' + '=' * 62)
print('4. SHEET FILES on disk')
print('=' * 62)
OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
for f in sorted(os.listdir(OUT)):
    if ('GOJ_T_S' in f or 'GOJ_W_S' in f) and f.endswith('.pdf'):
        st = os.stat(os.path.join(OUT, f))
        import datetime
        mt = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%H:%M')
        print(f'  {mt}  {st.st_size:>8}  {f}')
