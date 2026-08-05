#!/usr/bin/env python3
"""DEFINITIVE THURSDAY SYNC (the missing one!): live Carecenta Day5 roster
(149 clients) → canonical_ids → day_TH_actual. Zero-then-set. UPDATE only.
Same pattern as sync_wednesday_definitive.py."""
import json
import re
import sqlite3

# Live Carecenta Thursday roster from the reliable row parse
thu = json.load(open('/tmp/thursday_live_full.json'))  # list of names
# Build from full HTML to also capture shift times if available
import pickle, requests
from rapidfuzz import fuzz

BASE = 'https://goj.daycenta.com'
s = requests.Session()
s.cookies = pickle.load(open('/tmp/carecenta_cookies.pkl', 'rb'))
html = s.get(f'{BASE}/Clients.aspx', timeout=30).text
# parse rows with name + day cells (time string for Day5)
portal = []
for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
    last, first = m.group(1).strip(), m.group(2).strip()
    name = f'{last} {first}'
    start = m.start()
    row_start = html.rfind('<tr', 0, start)
    row_end = html.find('</tr>', start)
    if row_start == -1 or row_end == -1:
        continue
    row = html[row_start:row_end]
    d5 = re.search(r'class="Day5"[^>]*>(.*?)</td>', row, re.S)
    if d5 and ('spanappt' in d5.group(1) or re.search(r'\d{1,2}:\d{2}', d5.group(1))):
        portal.append(name)
print(f'Carecenta Thursday roster: {len(portal)}')

def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row
cid_rows = con.execute('SELECT canonical_id, name, auth_id FROM canonical_ids').fetchall()
auth = {r['client_id']: r for r in con.execute('SELECT client_id, name, active FROM clients')}

roster_norm = {norm(n) for n in portal}
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

# ZERO-THEN-SET (Thursday only)
con.execute('UPDATE clients SET day_TH_actual=0 WHERE active=1')
con.commit()

set1 = set2 = 0
unmapped = []
for name in portal:
    nk = norm(name)
    r = resolve(nk)
    if r is None:
        unmapped.append(name)
        continue
    cl = auth.get(r['auth_id'])
    if cl is None or not cl['active']:
        unmapped.append((name, 'inactive/no-client'))
        continue
    # Thursday shift: derive from time if available else default 1
    shift = 1  # all Thursday times are 1:15PM-5:15PM = S1/S2 ambiguous; keep 1 unless known
    con.execute('UPDATE clients SET day_TH_actual=? WHERE client_id=?', (shift, r['auth_id']))
    set1 += 1

con.commit()
s1 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=1").fetchone()[0]
s2 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=2").fetchone()[0]
print(f'day_TH_actual now: {s1}/{s2}')
print(f'unmapped ({len(unmapped)}): {unmapped[:10]}')
con.close()
