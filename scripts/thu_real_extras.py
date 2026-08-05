#!/usr/bin/env python3
"""Real Thursday extras: fuzzy-match auth-only names against Carecenta names."""
import difflib
import json
import sqlite3

cc = json.load(open('/tmp/carecenta_clients_week.json'))
cc_thu = set()
cc_all = set()
for name, days in cc:
    cc_all.add(name.lower())
    if '5' in {str(d) for d in days}:
        cc_thu.add(name.lower())

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
au_thu = {}
for shift in (1, 2):
    for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual=?", (shift,)):
        au_thu[r[0].lower()] = (r[0], shift)

def fuzzy_hit(name_low):
    """Return a Carecenta name matching this auth name, or None."""
    if name_low in cc_thu:
        return name_low
    sur = name_low.split()[0]
    best, br = None, 0
    for c in cc_thu:
        r = difflib.SequenceMatcher(None, name_low, c).ratio()
        if r > br:
            best, br = c, r
    if br >= 0.75:
        return best
    # surname match
    for c in cc_thu:
        if c.split()[0] == sur:
            return c
    return None

print('REAL Thursday extras (in auth, NO Carecenta match):')
n_real = 0
for n_low, (disp, shift) in sorted(au_thu.items()):
    hit = fuzzy_hit(n_low)
    if hit is None:
        n_real += 1
        print(f'  S{shift} {disp} — NO MATCH')
print(f'total real extras: {n_real}')

print('\nREAL Thursday missing (in Carecenta, NO auth match):')
n_miss = 0
au_all = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1")}
for c_low in sorted(cc_thu):
    if c_low in au_thu:
        continue
    # is this person in auth at all (any spelling)?
    sur = c_low.split()[0]
    in_auth = any(n.split()[0] == sur for n in au_all)
    if not in_auth:
        n_miss += 1
        print(f'  {c_low} — NOT IN AUTH AT ALL')
print(f'total real missing: {n_miss}')
a.close()
