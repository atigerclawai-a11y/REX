#!/usr/bin/env python3
"""SAFE Thursday sync: remove clients NOT on live Carecenta Thursday roster
(keep existing shift for those who ARE). Preserves S1/S2 split."""
import json
import pickle
import re
import sqlite3
import requests
from rapidfuzz import fuzz

# Live Carecenta Thursday roster (name list)
thu = json.load(open('/tmp/thursday_live_full.json'))
roster = {n.lower() for n in thu}
print(f'Carecenta Thu roster: {len(roster)}')

def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
con.row_factory = sqlite3.Row

# all clients with Thursday attendance
rows = con.execute("SELECT client_id, name, day_TH_actual FROM clients WHERE active=1 AND day_TH_actual IN (1,2)").fetchall()
print(f'auth Thu clients before: {len(rows)}')

roster_norm = {norm(n) for n in thu}
removed = []
kept = 0
for r in rows:
    nk = norm(r['name'])
    if nk in roster_norm:
        kept += 1
        continue
    # fuzzy check — don't remove spelling variants that ARE the same person
    best, bs = None, 0
    for rn in roster_norm:
        s = fuzz.WRatio(nk, rn)
        if s > bs:
            best, bs = rn, s
    if bs >= 85:
        kept += 1
        continue
    con.execute("UPDATE clients SET day_TH_actual=0 WHERE client_id=?", (r['client_id'],))
    removed.append((r['name'], r['day_TH_actual'], f'fuzzy best {best} ({bs:.0f})'))

con.commit()
print(f'kept: {kept}, removed: {len(removed)}')
for name, shift, why in removed:
    print(f'  REMOVED S{shift} {name} ({why})')

s1 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=1").fetchone()[0]
s2 = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=2").fetchone()[0]
print(f'\nday_TH_actual now: {s1}/{s2}')
con.close()
