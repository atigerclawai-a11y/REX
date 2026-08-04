#!/usr/bin/env python3
"""Check day_T_actual state + find Wed S2 missing client."""
import json
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('actuals now:')
for col in ['day_T_actual', 'day_W_actual']:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {col}: {s1}/{s2}')

# who changed since restore? compare with pre-apply backup
b = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db.bak_pre_apply_0804')
changed = []
tb = dict((r[0], r[1]) for r in b.execute("SELECT name, day_T_actual FROM clients WHERE active=1"))
tc = dict((r[0], r[1]) for r in a.execute("SELECT name, day_T_actual FROM clients WHERE active=1"))
for n in tb:
    if tb.get(n) != tc.get(n):
        changed.append((n, tb.get(n), tc.get(n)))
print(f'\nday_T changed vs backup: {len(changed)}')
for n, bv, cv in changed[:25]:
    print(f'  {n}: {bv} → {cv}')

# Wed S2 missing client
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=2")]
have = set()
for name, shifts in orders.get('2026-08-05', {}).items():
    for sh, o in shifts.items():
        if sh == '2':
            have.add(name)
missing = [n for n in sched if n not in have]
print(f'\nWed S2: scheduled {len(sched)}, have {len(have)}, missing {missing}')
a.close()
b.close()
