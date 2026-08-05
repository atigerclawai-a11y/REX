#!/usr/bin/env python3
"""Inspect the saved carecenta JSON structure."""
import json

cc = json.load(open('/tmp/carecenta_clients_week.json'))
print(f'type: {type(cc)}, len: {len(cc)}')
if isinstance(cc, list):
    print(f'first 3: {cc[:3]}')
    # check day keys
    all_days = set()
    for name, days in cc:
        all_days.update(days.keys())
    print(f'day keys: {sorted(all_days)}')
