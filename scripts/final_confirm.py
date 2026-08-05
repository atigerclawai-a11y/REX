#!/usr/bin/env python3
"""FINAL diagnostic confirmation."""
import sqlite3
import os
from datetime import datetime

print('=== CRON STATE (refresh crons hardened) ===')
import json
jobs = json.load(open('/Users/mainsobhelper/.hermes/profiles/work/cron/jobs.json'))
jobs_list = jobs if isinstance(jobs, list) else jobs.get('jobs', [])
for j in jobs_list:
    if j.get('job_id') in ('839aed29d920', '7a623c74b4f1'):
        prompt = j.get('prompt', '')[:90].replace('\n', ' ')
        print(f'  {j["job_id"]}: {"HARDENED ✓" if "HARD RULES" in j.get("prompt", "") else "⚠ NOT hardened"}')

print('\n=== ACTUALS ===')
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for col, exp in [('day_T_actual', (81, 55)), ('day_W_actual', (73, 95))]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'  {col}: {s1}/{s2} {"OK" if (s1, s2) == exp else "MISMATCH"}')
a.close()

print('\n=== SHEETS (final timestamps) ===')
for f in ['GOJ_T_S1_Tuesday_signin.pdf', 'GOJ_T_S2_Tuesday_signin.pdf',
          'GOJ_W_S1_Wednesday_signin.pdf', 'GOJ_W_S2_Wednesday_signin.pdf',
          'Menus_Tue_Aug04_S1_LIVE.pdf', 'Menus_Tue_Aug04_S2_LIVE.pdf']:
    p = f'/Users/mainsobhelper/Documents/goj files/output_docs/{f}'
    mt = datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S') if os.path.exists(p) else 'MISSING'
    print(f'  {f}: {mt}')
