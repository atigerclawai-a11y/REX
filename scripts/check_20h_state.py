#!/usr/bin/env python3
"""Check actuals now + orders JSON structure."""
import json
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('actuals now:')
for col in ['day_M_actual', 'day_T_actual', 'day_W_actual', 'day_TH_actual', 'day_F_actual']:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {col}: {s1}/{s2}')
print('\nbase:')
for col in ['day_M_base', 'day_T_base', 'day_W_base', 'day_TH_base', 'day_F_base']:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {col}: {s1}/{s2}')
a.close()

orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
print(f'\norders JSON keys: {len(orders)} dates')
for d in sorted(orders.keys())[-8:]:
    n1 = sum(1 for v in orders[d].values() if '1' in v)
    n2 = sum(1 for v in orders[d].values() if '2' in v)
    print(f'  {d}: {n1} S1 / {n2} S2')
