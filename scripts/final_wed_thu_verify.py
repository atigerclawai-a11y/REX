#!/usr/bin/env python3
"""FINAL VERIFICATION: all deliverables."""
import sqlite3
import os
from datetime import datetime

print('=== 1. WED FORMS (blank menus) ===')
for f in ['Menus_Wed_Aug05_S1_LIVE.pdf', 'Menus_Wed_Aug05_S2_LIVE.pdf']:
    p = f'/Users/mainsobhelper/Documents/goj files/output_docs/{f}'
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M') if os.path.exists(p) else 'MISSING'
    print(f'  {f}: {mt}')

print('\n=== 2. THU KITCHEN + PACKAGE ===')
for f in ['GOJ_TH_S1_Thursday_kitchen.pdf', 'GOJ_TH_S2_Thursday_kitchen.pdf',
          'GOJ_TH_S1_Thursday_signin.pdf', 'GOJ_TH_S2_Thursday_signin.pdf']:
    p = f'/Users/mainsobhelper/Documents/goj files/output_docs/{f}'
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M') if os.path.exists(p) else 'MISSING'
    print(f'  {f}: {mt}')

print('\n=== 3. DATA INTEGRITY ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for col, label in [('day_W_actual', 'WED'), ('day_TH_actual', 'THU')]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {label} attendance: {s1}/{s2}')

print('\n=== 4. house_standard per day (should be minimal) ===')
for d in ['2026-08-05', '2026-08-06']:
    h = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date=? AND source_sheet='house_standard'", (d,)).fetchone()[0]
    print(f'  {d}: {h} house_standard')
a.close()
p.close()

print('\n=== 5. CHANGE LOG CRON ===')
import json
lg = '/Users/mainsobhelper/Desktop/REX/data/change_log.json'
if os.path.exists(lg):
    data = json.load(open(lg))
    print(f'  change_log.json: {len(data)} entries')
else:
    print('  change_log.json MISSING')
