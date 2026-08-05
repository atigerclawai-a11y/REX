#!/usr/bin/env python3
"""Final verification: Aug 5 menus on disk + all sheet reconciliations."""
import os
import sqlite3
from datetime import datetime

OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
print('=== AUG 5 BLANK MENUS ===')
for f in ['Menus_Wed_Aug05_S1_LIVE.pdf', 'Menus_Wed_Aug05_S2_LIVE.pdf']:
    p = os.path.join(OUT, f)
    if os.path.exists(p):
        mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%m-%d %H:%M')
        sz = os.path.getsize(p) // 1024
        print(f'  {f}: {sz} KB ({mt})')
    else:
        print(f'  {f}: MISSING!')

print('\n=== TODAY (Aug 5) reconciliation ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for col, date, label in [('day_W_actual', '2026-08-05', 'WED'), ('day_TH_actual', '2026-08-06', 'THU')]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {label}: attendance {s1}/{s2}')
a.close()
p.close()
