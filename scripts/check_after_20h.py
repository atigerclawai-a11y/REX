#!/usr/bin/env python3
"""Check: did the 20:00 cron overwrite sheets or clobber actuals after my 20:15 run?"""
import sqlite3
import os
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== sheet timestamps (my run was 20:14-20:15) ===')
for f in ['GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_signin.pdf',
          'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_signin.pdf',
          'GOJ_T_S1_Tuesday_kitchen.pdf', 'GOJ_W_S1_Wednesday_kitchen.pdf',
          'Kitchen_Thu_Aug06.pdf']:
    p = os.path.join(OUT, f)
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S') if os.path.exists(p) else 'MISSING'
    print(f'  {f}: {mt}')

print('\n=== actuals now ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for col in ['day_T_actual', 'day_W_actual']:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {col}: {s1}/{s2}')
a.close()
