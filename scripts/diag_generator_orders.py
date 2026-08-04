#!/usr/bin/env python3
"""Trace generate_tomorrow's actual orders load — same import path it uses."""
import sys
sys.path.insert(0, '/Users/mainsobhelper/Documents/goj files/dashboard')
import generate_tomorrow as gt

data = gt.load_data()
orders = data.get('orders', {})
print('DATA_DIR:', gt.DATA_DIR)
print('orders type:', type(orders).__name__, '| dates:', list(orders.keys())[:5] if isinstance(orders, dict) else 'N/A')
day = orders.get('2026-08-05') if isinstance(orders, dict) else None
print('2026-08-05 entry:', 'PRESENT' if day else 'MISSING')
if day:
    keys = list(day.keys())
    print(f'  clients in entry: {len(keys)}, sample: {keys[:3]}')
    sample = day[keys[0]] if keys else {}
    print(f'  sample shifts: {list(sample.keys()) if isinstance(sample, dict) else sample}')
