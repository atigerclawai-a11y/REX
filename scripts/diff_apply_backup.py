#!/usr/bin/env python3
"""Diff day_*_actual between bak_pre_apply_0804 (05:10) and current auth DB."""
import sqlite3

BAK = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db.bak_pre_apply_0804'
CUR = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

def counts(db):
    con = sqlite3.connect(db)
    out = {}
    for col in ['day_M_actual', 'day_T_actual', 'day_W_actual', 'day_TH_actual', 'day_F_actual']:
        s1 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
        s2 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
        out[col] = (s1, s2)
    con.close()
    return out

b, c = counts(BAK), counts(CUR)
print('               bak@05:10   current   delta')
for col in b:
    d = (c[col][0]-b[col][0], c[col][1]-b[col][1])
    print(f'{col}:        S1={b[col][0]:3d}/S2={b[col][1]:3d}   S1={c[col][0]:3d}/S2={c[col][1]:3d}   ({d[0]:+d},{d[1]:+d})')

# per-client diff for day_T_actual
con_b, con_c = sqlite3.connect(BAK), sqlite3.connect(CUR)
tb = dict((r[0], r[1]) for r in con_b.execute("SELECT name, day_T_actual FROM clients WHERE active=1"))
tc = dict((r[0], r[1]) for r in con_c.execute("SELECT name, day_T_actual FROM clients WHERE active=1"))
changed = [(n, tb.get(n), tc.get(n)) for n in tb if tb.get(n) != tc.get(n)]
print(f'\nday_T_actual changed: {len(changed)} clients')
for n, bv, cv in changed[:40]:
    print(f'  {n}: {bv} → {cv}')
con_b.close(); con_c.close()
