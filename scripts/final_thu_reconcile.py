#!/usr/bin/env python3
"""FINAL Thursday reconciliation: auth 118/47 vs live Carecenta 149.
Fuzzy-match each auth client to a Carecenta name; report real differences."""
import difflib
import json
import sqlite3

cc = json.load(open('/tmp/thursday_live_full.json'))
cc_set = {n.lower() for n in cc}
print(f'Carecenta Thu: {len(cc_set)}')

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
auth_thu = []
for shift in (1, 2):
    for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual=?", (shift,)):
        auth_thu.append((r[0], shift))
print(f'Auth Thu: {len(auth_thu)} (S1={sum(1 for _,s in auth_thu if s==1)}, S2={sum(1 for _,s in auth_thu if s==2)})')

def fuzzy(name_low):
    if name_low in cc_set:
        return name_low
    best, br = None, 0
    for c in cc_set:
        r = difflib.SequenceMatcher(None, name_low, c).ratio()
        if r > br:
            best, br = c, r
    if br >= 0.8:
        return best
    return None

# auth NOT in Carecenta (extra)
extra = []
for name, shift in auth_thu:
    hit = fuzzy(name.lower())
    if hit is None:
        extra.append((name, shift))
print(f'\nIN AUTH NOT IN CARECENTA ({len(extra)}):')
for n, s in sorted(extra):
    print(f'  S{s} {n}')

# Carecenta NOT in auth
auth_set = {n.lower() for n, _ in auth_thu}
missing = []
for c in cc_set:
    hit = fuzzy(c)
    if hit is None:
        missing.append(c)
print(f'\nIN CARECENTA NOT IN AUTH ({len(missing)}):')
for c in sorted(missing):
    print(f'  {c}')
a.close()
