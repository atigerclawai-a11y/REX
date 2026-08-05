#!/usr/bin/env python3
"""Check the W2 discrepancy clients — real absence or spelling?"""
import json
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
wed = json.load(open('/tmp/wed_definitive.json'))
cc_w2 = wed.get('s2', [])
print('=== Carecenta W2 clients missing from auth W2 ===')
for n in cc_w2:
    parts = [p.strip() for p in n.split(',')]
    flipped = f"{parts[0]} {parts[1]}" if len(parts) == 2 else n.strip()
    # search auth by surname
    sur = flipped.split()[0]
    rows = a.execute("SELECT name, day_W_actual FROM clients WHERE name LIKE ?", (f'%{sur}%',)).fetchall()
    if not rows:
        print(f'  {flipped}: NO MATCH in auth at all!')
    else:
        for r in rows:
            mark = '' if r[1] else '  ← W=0!'
            print(f'  {flipped} → auth {r[0]} (W={r[1]}){mark}')
a.close()
