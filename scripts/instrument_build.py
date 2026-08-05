#!/usr/bin/env python3
"""Instrument: call build_menu_clients for Tue directly and see the result."""
import json
import sys
sys.path.insert(0, '/Users/mainsobhelper/Documents/goj files/dashboard')
import generate_tomorrow as gt

data = gt.load_data()
orders = data.get('orders', {})
clients = data.get('clients', [])
print(f'orders: {len(orders)} dates, clients: {len(clients) if isinstance(clients, list) else "dict"}')

# build for Tue shift 1
res1 = gt.build_menu_clients('2026-08-04', 1, orders, clients, {})
res2 = gt.build_menu_clients('2026-08-04', 2, orders, clients, {})
print(f'Tue S1 menu clients: {len(res1)}')
print(f'Tue S2 menu clients: {len(res2)}')

# try Wed for comparison
res3 = gt.build_menu_clients('2026-08-05', 1, orders, clients, {})
print(f'Wed S1 menu clients: {len(res3)}')
if res3:
    print(f'  sample: {res3[0]}')
