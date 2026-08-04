#!/usr/bin/env python3
"""ID-first definitive Wednesday sync: roster from Clients.aspx WED times
(73 S1 / 96 S2) → canonical_ids → day_W_actual. Zero-then-set. UPDATE only."""
import json
import re
import sqlite3

data = json.load(open('/tmp/wed_definitive.json'))
roster_s1 = [n.upper() for n in data['s1']]
roster_s2 = [n.upper() for n in data['s2']]


def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))


con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
auth = {r['client_id']: r for r in con.execute('SELECT client_id, name, active FROM clients')}

s1_norm = {norm(n) for n in roster_s1}
s2_norm = {norm(n) for n in roster_s2}

from rapidfuzz import fuzz
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


# ZERO-THEN-SET
con.execute('UPDATE clients SET day_W_actual=0 WHERE active=1')
con.commit()

set1 = set2 = 0
unmapped = []
for name in roster_s1 + roster_s2:
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
    con.execute('UPDATE clients SET day_W_actual=? WHERE client_id=?', (shift, r['auth_id']))
    if shift == 1:
        set1 += 1
    else:
        set2 += 1
con.commit()
con.close()
print(f'DEFINITIVE sync: day_W_actual S1={set1} S2={set2} (roster 73/96)')
print(f'unmapped ({len(unmapped)}):')
for u in unmapped:
    print(f'  {u}')
