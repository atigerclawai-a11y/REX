#!/usr/bin/env python3
"""Assemble definitive Tuesday Aug 4 roster from Clients.aspx TUE column times.
WED cell (index 4) holds actual scheduled time: 9AM-1PM/10AM-2PM = S1,
1:15PM-5:15PM = S2. Ground truth (sign-in checkbox filter unreliable)."""
import json
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/scripts')
all_rows = []
for i in range(1, 9):
    try:
        data = json.loads((BASE / f'tue_p{i}.json').read_text())
        if isinstance(data, dict):
            data = data.get(f'p{i}', [])
        all_rows.extend(data)
    except FileNotFoundError:
        print(f'MISSING tue_p{i}.json')

print(f'collected {len(all_rows)} TUE-scheduled client rows from 8 pages')

s1, s2 = [], []
for r in all_rows:
    t = r.get('tue', '').upper()
    if not t:
        continue
    if '9AM-5PM' in t:
        s1.append(r['name']); s2.append(r['name'])  # full-day: both
    elif '1:15PM' in t:
        s2.append(r['name'])
    else:
        s1.append(r['name'])

print(f'S1 (AM) = {len(s1)}  S2 (PM) = {len(s2)}')
out = {'date': '2026-08-04', 's1': sorted(set(s1)), 's2': sorted(set(s2))}
Path('/tmp/tue_definitive.json').write_text(json.dumps(out, indent=1))
print(f'saved /tmp/tue_definitive.json: S1={len(out["s1"])} S2={len(out["s2"])} total={len(out["s1"])+len(out["s2"])}')
