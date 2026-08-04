#!/usr/bin/env python3
"""Verify auth actuals + sheet timestamps after restore."""
import sqlite3
import os
from datetime import datetime

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for col, exp in [('day_T_actual', (81, 55)), ('day_W_actual', (73, 95))]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'{col}: {s1}/{s2} → {"OK" if (s1, s2) == exp else "MISMATCH"}')
a.close()

for f in ['GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_W_S1_Wednesday_signin.pdf',
          'GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_W_S1_Wednesday_kitchen.pdf']:
    p = f'/Users/mainsobhelper/Documents/goj files/output_docs/{f}'
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S') if os.path.exists(p) else 'MISSING'
    print(f'{f}: {mt}')
