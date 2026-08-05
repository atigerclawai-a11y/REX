#!/usr/bin/env python3
"""FINAL VERIFY: actuals, sheets, garbage, parity after everything."""
import sqlite3
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('=== ACTUALS (target Tue 81/55, Wed 73/95) ===')
for col, exp in [('day_T_actual', (81, 55)), ('day_W_actual', (73, 95))]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {col}: {s1}/{s2} {"OK" if (s1, s2) == exp else "MISMATCH"}')
a.close()

print('\n=== SHEETS (final) ===')
for f in ['GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_signin.pdf',
          'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_signin.pdf']:
    p = os.path.join(OUT, f)
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S')
    print(f'  {f}: {mt}')

print('\n=== Fedorova Olga final ===')
import json
orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
for d in ['2026-08-03', '2026-08-06']:
    if 'Fedorova Olga' in orders.get(d, {}):
        print(f'  {d}: {orders[d]["Fedorova Olga"]}')
