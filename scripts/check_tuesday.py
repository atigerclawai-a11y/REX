#!/usr/bin/env python3
"""Check Tuesday Aug 4 state: auth day_T_actual, DB coverage, partial rows."""
import sqlite3

DATE = '2026-08-04'
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
sched = a.execute("SELECT name, day_T_actual FROM clients WHERE active=1 AND day_T_actual IN (1,2)").fetchall()
a.close()
print(f'auth day_T_actual: S1={sum(1 for _,s in sched if s==1)} S2={sum(1 for _,s in sched if s==2)} total={len(sched)}')

p = sqlite3.connect(PROP)
rows = p.execute("""SELECT client_name, shift, salad, soup, main, side, source_sheet FROM client_menus
    WHERE menu_date=?""", (DATE,)).fetchall()
p.close()
print(f'DB rows for {DATE}: {len(rows)}')
complete = [r for r in rows if all([r[2], r[3], r[4], r[5]])]
partial = [r for r in rows if not all([r[2], r[3], r[4], r[5]])]
print(f'  complete (4 dishes): {len(complete)}  partial: {len(partial)}')
by_src = {}
for r in rows:
    by_src[r[6]] = by_src.get(r[6], 0) + 1
print(f'  by source: {by_src}')
if partial:
    print('  partial rows:')
    for r in partial[:15]:
        print(f'    {r[0]} S{r[1]} [{r[6]}]: {r[2]} | {r[3]} | {r[4]} | {r[5]}')

# scheduled but no row at all
have = {(r[0], str(r[1])) for r in rows}
missing = [(n, s) for n, s in sched if (n, str(s)) not in have]
print(f'scheduled WITHOUT any row ({len(missing)}):')
for n, s in missing[:10]:
    print(f'  S{s}: {n}')
