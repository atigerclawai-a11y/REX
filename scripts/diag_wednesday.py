#!/usr/bin/env python3
"""Diagnose which Wednesday roster names are NOT set in day_W_actual."""
import json
import re
import sqlite3

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
unmapped = []
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
    if r is None:
        unmapped.append((name, shift, 'NO canonical_id'))
        continue
    cl = auth.get(r['auth_id'])
    if cl is None:
        unmapped.append((name, shift, f'canonical_id -> no auth client'))
        continue
    if not cl['active']:
        unmapped.append((name, shift, f'client INACTIVE (day_W={cl["day_W_actual"]})'))
        continue
    if cl['day_W_actual'] == 0:
        unmapped.append((name, shift, f'client day_W=0 (NOT SET)'))
print(f'roster entries unmapped/not-set ({len(unmapped)}):')
for n, s, why in unmapped:
    print(f'  [{s}] {n}: {why}')
