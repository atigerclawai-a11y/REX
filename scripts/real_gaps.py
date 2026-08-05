#!/usr/bin/env python3
"""Real gaps after fuzzy/spelling normalization — use surname+first-initial match."""
import difflib
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

# auth name index: normalized + surname lookup
auth_names = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1")]
auth_by_surname = {}
for n in auth_names:
    parts = n.split()
    if parts:
        auth_by_surname.setdefault(parts[0].lower(), []).append(n)

def find_auth(cc_name):
    """Try exact, then surname match."""
    low = cc_name.lower()
    if low in {n.lower() for n in auth_names}:
        return 'EXACT'
    sur = cc_name.split()[0].lower()
    if sur in auth_by_surname:
        return auth_by_surname[sur]
    # fuzzy on surname
    best, br = None, 0
    for s in auth_by_surname:
        r = difflib.SequenceMatcher(None, sur, s).ratio()
        if r > br:
            best, br = s, r
    return auth_by_surname.get(best, []) if br >= 0.8 else None

for day, col, label in [(3, 'day_T_actual', 'TUE'), (4, 'day_W_actual', 'WED')]:
    cc_s = set()
    for name, days in cc:
        if str(day) in {str(d) for d in days}:
            cc_s.add(name)
    au_s = {r[0].lower() for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col} IN (1,2)")}
    print(f'\n=== {label}: Carecenta {len(cc_s)} vs auth {len(au_s)} ===')
    print('REAL missing (no auth match even by surname):')
    for n in sorted(cc_s):
        if n.lower() in au_s:
            continue
        hit = find_auth(n)
        if hit is None:
            print(f'  ⚠️ {n} — NO MATCH')
        elif isinstance(hit, list) and n.lower() not in {h.lower() for h in hit}:
            print(f'  {n} → {hit} (spelling variant)')
a.close()
