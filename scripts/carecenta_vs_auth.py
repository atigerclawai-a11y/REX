#!/usr/bin/env python3
"""FULL COMPARISON: Carecenta scrape (tue_definitive/wed_definitive) vs auth actuals."""
import json
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')

def flip(name):
    """'LAST, FIRST' → 'Last First' (auth format)"""
    parts = [p.strip() for p in name.split(',')]
    if len(parts) == 2:
        return f"{parts[0]} {parts[1]}"
    return name.strip()

# Tuesday comparison
tue = json.load(open('/tmp/tue_definitive.json'))
print('=== TUESDAY (Carecenta vs auth day_T_actual) ===')
cc_s1 = {flip(n).lower() for n in tue.get('s1', [])}
cc_s2 = {flip(n).lower() for n in tue.get('s2', [])}
auth_s1 = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_T_actual=1")}
auth_s2 = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_T_actual=2")}
print(f'Carecenta: S1={len(cc_s1)} S2={len(cc_s2)}  auth: S1={len(auth_s1)} S2={len(auth_s2)}')
print(f'\n  In Carecenta S1 but NOT in auth S1 ({len(cc_s1 - auth_s1)}):')
for n in sorted(cc_s1 - auth_s1)[:30]:
    print(f'    {n}')
print(f'\n  In auth S1 but NOT in Carecenta S1 ({len(auth_s1 - cc_s1)}):')
for n in sorted(auth_s1 - cc_s1)[:30]:
    print(f'    {n}')
print(f'\n  In Carecenta S2 but NOT in auth S2 ({len(cc_s2 - auth_s2)}):')
for n in sorted(cc_s2 - auth_s2)[:20]:
    print(f'    {n}')

# Wednesday
wed = json.load(open('/tmp/wed_definitive.json'))
print('\n=== WEDNESDAY (Carecenta vs auth day_W_actual) ===')
cc_w1 = {flip(n).lower() for n in wed.get('s1', [])}
cc_w2 = {flip(n).lower() for n in wed.get('s2', [])}
auth_w1 = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=1")}
auth_w2 = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=2")}
print(f'Carecenta: S1={len(cc_w1)} S2={len(cc_w2)}  auth: S1={len(auth_w1)} S2={len(auth_w2)}')
print(f'\n  In Carecenta W1 but NOT in auth W1 ({len(cc_w1 - auth_w1)}):')
for n in sorted(cc_w1 - auth_w1)[:25]:
    print(f'    {n}')
print(f'\n  In auth W1 but NOT in Carecenta W1 ({len(auth_w1 - cc_w1)}):')
for n in sorted(auth_w1 - cc_w1)[:25]:
    print(f'    {n}')
print(f'\n  In Carecenta W2 but NOT in auth W2 ({len(cc_w2 - auth_w2)}):')
for n in sorted(cc_w2 - auth_w2)[:15]:
    print(f'    {n}')
a.close()
