#!/usr/bin/env python3
"""Re-verify current actuals against backup — what's different NOW vs 05:10 backup?"""
import sqlite3

BAK = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db.bak_pre_apply_0804'
CUR = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

b = sqlite3.connect(BAK)
c = sqlite3.connect(CUR)
for col in ['day_T_actual', 'day_W_actual']:
    b1 = b.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    b2 = b.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    c1 = c.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    c2 = c.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    print(f'{col}: bak {b1}/{b2} vs now {c1}/{c2}')

# who differs in day_W now vs bak
tb = dict((r[0], r[1]) for r in b.execute("SELECT name, day_W_actual FROM clients WHERE active=1"))
tc = dict((r[0], r[1]) for r in c.execute("SELECT name, day_W_actual FROM clients WHERE active=1"))
changed = [(n, tb.get(n), tc.get(n)) for n in tb if tb.get(n) != tc.get(n)]
print(f'\nday_W changed vs backup: {len(changed)}')
for n, bv, cv in changed[:15]:
    print(f'  {n}: {bv} → {cv}')
b.close()
c.close()
