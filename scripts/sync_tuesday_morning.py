#!/usr/bin/env python3
"""Tuesday Aug 4 sync — ID-first, using the morning-verified 81/55 lists
(dashboard EXPECTED match). Zero-then-set. UPDATE only. Backup taken."""
import re
import sqlite3

src = open('/tmp/sync_final_live.py').read()
TUE_AM = [x.strip() for x in re.search(r'TUE_AM = """(.*?)"""', src, re.S).group(1).split('|')]
TUE_PM = [x.strip() for x in re.search(r'TUE_PM = """(.*?)"""', src, re.S).group(1).split('|')]
EXCLUDE_TUE_AM = ['Kramer, Sofya', 'Magalnik, Malvina']
tue_am = [x for x in TUE_AM if x not in EXCLUDE_TUE_AM]
print(f'morning-verified lists: AM={len(tue_am)} PM={len(TUE_PM)}')


def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split())) if n else ''


con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
auth = {r['client_id']: r for r in con.execute('SELECT client_id, name, active FROM clients')}

am_n = {norm(x) for x in tue_am}
pm_n = {norm(x) for x in TUE_PM}

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


con.execute('UPDATE clients SET day_T_actual=0 WHERE active=1')
con.commit()

set1 = set2 = 0
unmapped = []
for name in tue_am + TUE_PM:
    nk = norm(name)
    r = resolve(nk)
    shift = 1 if nk in am_n else 2
    if r is None:
        unmapped.append((name, shift))
        continue
    cl = auth.get(r['auth_id'])
    if cl is None or not cl['active']:
        unmapped.append((name, shift, 'inactive/no-client'))
        continue
    con.execute('UPDATE clients SET day_T_actual=? WHERE client_id=?', (shift, r['auth_id']))
    if shift == 1:
        set1 += 1
    else:
        set2 += 1
con.commit()
con.close()
print(f'Tuesday sync: day_T_actual S1={set1} S2={set2} (target 81/55)')
print(f'unmapped ({len(unmapped)}):')
for u in unmapped:
    print(f'  {u}')
