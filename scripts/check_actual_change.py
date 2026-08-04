#!/usr/bin/env python3
"""Check: did day_T_actual change? Compare auth base vs actual vs sheet counts."""
import sqlite3
from datetime import datetime

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('auth day_*_actual vs base (Tue/Wed):')
for col in ['day_T_actual', 'day_T_base', 'day_W_actual', 'day_W_base']:
    n1 = a.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    n2 = a.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    print(f'  {col}: S1={n1} S2={n2}')
a.close()

import os
for f in ['GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_signin.pdf',
          'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_signin.pdf']:
    p = f'/Users/mainsobhelper/Documents/goj files/output_docs/{f}'
    if os.path.exists(p):
        print(f'{f}: {datetime.fromtimestamp(os.stat(p).st_mtime).strftime("%H:%M:%S")}')
