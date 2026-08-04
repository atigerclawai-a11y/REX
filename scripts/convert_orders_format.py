#!/usr/bin/env python3
"""Convert GOJ_Menu_Orders.json to FULLY date-based format.
Old: {'2026-02-27_S1': {'orders': [...]}}  New: {'2026-02-27': {name: {shift: {...}}}}"""
import json
import re

P = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
d = json.load(open(P))

date_based = {}
for key, val in d.items():
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_S(\d)$', key)
    if m:  # old shift-based entry
        date_iso, shift = m.group(1), m.group(2)
        orders = val.get('orders', []) if isinstance(val, dict) else []
        for o in orders:
            name = o.get('name', '').strip()
            if not name:
                continue
            date_based.setdefault(date_iso, {}).setdefault(name, {})[shift] = {
                'salad': o.get('salad', ''), 'soup': o.get('soup', ''),
                'main': o.get('main', ''), 'side': o.get('side', ''),
                'kosher': o.get('kosher', False),
            }
    else:  # already date-based
        date_based.setdefault(key, val)

json.dump(date_based, open(P, 'w'), ensure_ascii=False, indent=1)
print(f'converted: {len(date_based)} date keys')
print('sample dates:', sorted(date_based.keys())[:3], '...')
print('2026-08-05 present:', '2026-08-05' in date_based)
if '2026-08-05' in date_based:
    print('  2026-08-05 clients:', len(date_based['2026-08-05']))
