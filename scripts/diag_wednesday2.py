#!/usr/bin/env python3
"""Reconcile: which roster names share a client / which clients are set vs roster."""
import json
import re
import sqlite3
from collections import defaultdict

data = json.load(open('/tmp/wednesday_live_roster.json'))
roster = [(n.upper(), 'AM') for n in data['am']] + [(n.upper(), 'PM') for n in data['pm']]


def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))


con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
cids = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
auth = {r['client_id']: r for r in con.execute('SELECT client_id, name, active, day_W_actual FROM clients')}
con.close()

from rapidfuzz import fuzz
cid_norms = [(norm(r['name']), r) for r in cids]

# map each roster entry -> client_id
name2client = {}
for name, shift in roster:
    nk = norm(name)
    r = next((r for cn, r in cid_norms if cn == nk), None)
    if r is None:
        best, bs = None, 0
        for cn, rr in cid_norms:
            s = fuzz.WRatio(nk, cn)
            if s > bs:
                best, bs = rr, s
        if bs >= 85:
            r = best
    if r is not None:
        name2client.setdefault(name, []).append((r['auth_id'], shift, r['name']))

# duplicates: same client mapped from multiple roster entries
client_names = defaultdict(list)
for name, hits in name2client.items():
    for cid, shift, cname in hits:
        client_names[cid].append((name, shift))

dups = {cid: v for cid, v in client_names.items() if len(v) > 1}
print(f'clients mapped from MULTIPLE roster entries ({len(dups)}):')
for cid, v in list(dups.items())[:20]:
    print(f'  client {cid}: {v}')

# count: roster entries that DID resolve to a client, but client not active or day_W mismatch
mismatch = []
for name, hits in name2client.items():
    for cid, shift, cname in hits:
        cl = auth.get(cid)
        if cl is None:
            mismatch.append((name, shift, 'NO CLIENT'))
        elif not cl['active']:
            mismatch.append((name, shift, f'INACTIVE cid={cid}'))
        elif shift == 'AM' and cl['day_W_actual'] != 1:
            mismatch.append((name, shift, f'day_W={cl["day_W_actual"]} cid={cid}'))
        elif shift == 'PM' and cl['day_W_actual'] != 2:
            mismatch.append((name, shift, f'day_W={cl["day_W_actual"]} cid={cid}'))
print(f'\nmismatches (resolved but wrong/not set) ({len(mismatch)}):')
for n, s, why in mismatch:
    print(f'  [{s}] {n}: {why}')
