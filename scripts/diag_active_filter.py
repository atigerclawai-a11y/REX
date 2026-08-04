#!/usr/bin/env python3
"""Debug the active filter for menu build."""
import sqlite3
import json

auth = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
active_names = {r[0].strip().lower() for r in auth.execute("SELECT name FROM clients WHERE active=1")}
auth.close()

roster = json.load(open('/tmp/wed_definitive.json'))
sample = roster['s2'][:5]
print('sample roster (LAST, FIRST):', sample)
print('sample active names:', sorted(list(active_names))[:5])

for n in sample:
    parts = [p.strip() for p in n.split(',')]
    flipped = f"{parts[1]} {parts[0]}".lower() if len(parts) == 2 else n.lower()
    print(f'  {n}: flipped={flipped!r} in_active={flipped in active_names} | raw_in={n.lower() in active_names}')
