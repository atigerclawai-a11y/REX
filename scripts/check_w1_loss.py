#!/usr/bin/env python3
"""Check Wed actuals — why S1 dropped 73→64?"""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for col in ['day_T_actual', 'day_W_actual']:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'{col}: {s1}/{s2}')

# who was W1 that's now not?
print('\nW1 diff vs backup:')
b = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db.bak_pre_apply_0804')
bw1 = {r[0] for r in b.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=1")}
cw1 = {r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=1")}
lost = bw1 - cw1
print(f'lost from W1 ({len(lost)}):')
for n in sorted(lost)[:25]:
    print(f'  {n}')
added = cw1 - bw1
print(f'added to W1 ({len(added)}): {sorted(added)[:10]}')
a.close()
b.close()
