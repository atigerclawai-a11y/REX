#!/usr/bin/env python3
"""Assemble definitive Wednesday Aug 5 roster from Clients.aspx WED column times.
WED cell (index 5) holds the actual scheduled time: 9AM-1PM / 10AM-2PM = S1,
1:15PM-5:15PM = S2. This is the ground truth (sign-in AM/PM checkbox filter
proved unreliable — pollutes with cross-shift names)."""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/scripts')
pages = {}
for i in range(1, 9):
    try:
        pages[i] = json.loads((BASE / f'wed_p{i}.json').read_text())
    except FileNotFoundError:
        print(f'MISSING wed_p{i}.json — will continue with what exists')

# All pages should be present; merge
all_rows = []
for i in sorted(pages):
    data = pages[i]
    if isinstance(data, dict):  # wrapped {"pN": [...]}
        data = data.get(f'p{i}', [])
    all_rows.extend(data)
print(f'collected {len(all_rows)} client rows from {len(pages)} pages')

# Classify by WED time
s1, s2, none = [], [], []
for r in all_rows:
    w = r['wed'].upper()
    if not w:
        none.append(r['name'])
    elif '9AM-5PM' in w or ('9AM-1PM' in w and '1:15PM' in w):
        # full-day: assign to BOTH? generator needs ONE — check both entries later
        s1.append(r['name']); s2.append(r['name'])
    elif '1:15PM' in w:
        s2.append(r['name'])
    else:
        s1.append(r['name'])

print(f'S1 (AM) = {len(s1)}  S2 (PM) = {len(s2)}  no-schedule = {len(none)}')
print(f'no-schedule count is expected (Wed not their day)')

# Save the definitive roster
out = {'date': '2026-08-05', 's1': sorted(set(s1)), 's2': sorted(set(s2))}
Path('/tmp/wed_definitive.json').write_text(json.dumps(out, indent=1))
print(f'saved /tmp/wed_definitive.json: S1={len(out["s1"])} S2={len(out["s2"])} total={len(out["s1"])+len(out["s2"])}')
