#!/usr/bin/env python3
"""DEFINITIVE THURSDAY + FRIDAY sync — the SAME proven method as
sync_wednesday_definitive.py (which produced the accepted 73/96).
Source: /tmp/thu_fri_definitive.json (parsed from live Carecenta Clients.aspx
with BOTH time formats — 9AM-1PM = S1, 1:15PM-5:15PM = S2).
Zero-then-set day_TH_actual and day_F_actual. UPDATE only."""
import json
import re
import sqlite3
from rapidfuzz import fuzz

data = json.load(open('/tmp/thu_fri_definitive.json'))

def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
auth = {r['client_id']: r for r in con.execute('SELECT client_id, name, active FROM clients')}
cid_norms = [(norm(r['name']), r) for r in cid_rows]

def resolve(nk):
    r = next((r for cn, r in cid_norms if cn == nk), None)
    if r is None:
        best, bs = None, 0
        for cn, rr in cid_norms:
            s = fuzz.WRatio(nk, cn)
            if s > bs:
                best, bs = rr, s
        if bs >= 85:
            r = best
    return r

for day_key, col in [('thu', 'day_TH_actual'), ('fri', 'day_F_actual')]:
    roster = data[day_key]
    s1_norm = {norm(n) for n in roster['s1']}
    s2_norm = {norm(n) for n in roster['s2']}
    all_names = roster['s1'] + roster['s2']

    # ZERO-THEN-SET
    con.execute(f'UPDATE clients SET {col}=0 WHERE active=1')
    con.commit()

    set1 = set2 = 0
    unmapped = []
    for name in all_names:
        nk = norm(name)
        r = resolve(nk)
        shift = 1 if nk in s1_norm else 2
        if r is None:
            unmapped.append((name, shift))
            continue
        cl = auth.get(r['auth_id'])
        if cl is None or not cl['active']:
            unmapped.append((name, shift, 'inactive/no-client'))
            continue
        con.execute(f'UPDATE clients SET {col}=? WHERE client_id=?', (shift, r['auth_id']))
        if shift == 1:
            set1 += 1
        else:
            set2 += 1
    con.commit()
    s1f = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    s2f = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    print(f'\n{day_key}: roster S1={len(roster["s1"])} S2={len(roster["s2"])} → DB {s1f}/{s2f} (total {s1f+s2f})')
    print(f'unmapped ({len(unmapped)}):')
    for u in unmapped:
        print(f'  {u}')

con.close()
