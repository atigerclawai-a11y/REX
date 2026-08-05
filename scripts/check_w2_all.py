#!/usr/bin/env python3
"""Check ALL Carecenta W2 missing clients for auth matches."""
import json
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
wed = json.load(open('/tmp/wed_definitive.json'))
cc_w2 = wed.get('s2', [])
auth_w2 = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=2")}

print('=== Carecenta W2 names NOT matched in auth W2 (by surname) ===')
for n in cc_w2:
    parts = [p.strip() for p in n.split(',')]
    flipped = f"{parts[0]} {parts[1]}" if len(parts) == 2 else n.strip()
    if flipped.lower() in auth_w2:
        continue
    sur = flipped.split()[0]
    rows = a.execute("SELECT name, active, day_W_actual FROM clients WHERE name LIKE ?", (f'%{sur}%',)).fetchall()
    if rows:
        for r in rows:
            print(f'  {flipped} → auth {r[0]} (active={r[1]}, W={r[2]})')
    else:
        print(f'  {flipped}: NO auth match')
a.close()
