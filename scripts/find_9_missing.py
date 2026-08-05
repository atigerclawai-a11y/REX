#!/usr/bin/env python3
"""Find the 9 Carecenta Thu clients not in auth day_TH (need ADDING)."""
import json
import re
import sqlite3
from rapidfuzz import fuzz

thu = json.load(open('/tmp/thursday_live_full.json'))

def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
auth_thu = {norm(r['name']) for r in con.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual IN (1,2)")}

# canonical name index for adding
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
cid_norms = [(norm(r['name']), r) for r in cid_rows]

missing = []
for name in thu:
    nk = norm(name)
    if nk in auth_thu:
        continue
    # fuzzy against auth Thu set
    best, bs = None, 0
    for at in auth_thu:
        s = fuzz.WRatio(nk, at)
        if s > bs:
            best, bs = at, s
    if bs >= 85:
        continue  # it's there under variant spelling
    missing.append(name)

print(f'Carecenta Thu clients NOT in auth day_TH ({len(missing)}):')
for n in sorted(missing):
    # is this client in auth at all (any spelling)?
    nk = norm(n)
    best, bs = None, 0
    for cn, r in cid_norms:
        s = fuzz.WRatio(nk, cn)
        if s > bs:
            best, bs = cn, s
    print(f'  {n}: auth-match {best} ({bs:.0f})')
con.close()
