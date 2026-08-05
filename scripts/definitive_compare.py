#!/usr/bin/env python3
"""DEFINITIVE COMPARISON: live Carecenta (399 clients) vs auth day_*_actual.
Day map: Day3=Tue(Aug4), Day4=Wed(Aug5), Day2=Mon(Aug3), Day5=Thu(Aug6), Day6=Fri(Aug7)."""
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

def norm(n):
    return n.strip().lower()

# Carecenta names: "Last First" format
cc_by_day = {2: set(), 3: set(), 4: set(), 5: set(), 6: set()}
for name, days in cc:
    n = norm(name)
    for d in days:
        try:
            di = int(d)
        except (TypeError, ValueError):
            di = d
        if di in cc_by_day:
            cc_by_day[di].add(n)

# auth actuals
auth_by_day = {}
for col, day in [('day_M_actual', 2), ('day_T_actual', 3), ('day_W_actual', 4),
                 ('day_TH_actual', 5), ('day_F_actual', 6)]:
    s = set()
    for shift in (1, 2):
        for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,)):
            s.add(norm(r[0]))
    auth_by_day[day] = s

labels = {2: 'MON Aug3', 3: 'TUE Aug4', 4: 'WED Aug5', 5: 'THU Aug6', 6: 'FRI Aug7'}
for day in [3, 4, 2, 5, 6]:
    cc_s = cc_by_day[day]
    au_s = auth_by_day[day]
    print(f'\n=== {labels[day]} ===')
    print(f'  Carecenta: {len(cc_s)} | auth: {len(au_s)}')
    # on Carecenta not on auth (potential missing)
    missing = cc_s - au_s
    # on auth not on Carecenta (potential stale)
    extra = au_s - cc_s
    if missing:
        print(f'  IN CARECENTA NOT AUTH ({len(missing)}):')
        for n in sorted(missing)[:40]:
            print(f'    {n}')
    if extra:
        print(f'  IN AUTH NOT CARECENTA ({len(extra)}):')
        for n in sorted(extra)[:20]:
            print(f'    {n}')
a.close()
