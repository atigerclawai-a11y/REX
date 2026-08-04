#!/usr/bin/env python3
"""Inspect real GOJ_Menu_Orders.json structure at the CORRECT path."""
import json

d = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
keys = list(d.keys())
print('total keys:', len(keys))
print('first 3 keys:', keys[:3])
print('has orders-in-value:', any(isinstance(v, dict) and 'orders' in v for v in d.values()))
print('2026-08-05 in file:', '2026-08-05' in d)
if '2026-08-05' in d:
    e = d['2026-08-05']
    print('entry type:', type(e).__name__)
    if isinstance(e, dict):
        ks = list(e.keys())
        print('first keys:', ks[:2])
        if ks:
            print('first client value:', str(e[ks[0]])[:120])
