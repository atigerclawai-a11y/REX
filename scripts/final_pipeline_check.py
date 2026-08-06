#!/usr/bin/env python3
"""FINAL VERIFICATION: email-scan sign-in pipeline."""
import json
import os
import sqlite3

print('=== 1. BACKUPS (from emailed scans) ===')
B = '/Users/mainsobhelper/Desktop/REX/attendance_backups'
if os.path.isdir(B):
    for f in sorted(os.listdir(B)):
        if f.endswith('.json'):
            d = json.load(open(os.path.join(B, f)))
            print(f'  {f}: {d["name_count"]} names')
else:
    print('  MISSING')

print('\n=== 2. ATTENDANCE_LOG (signin_ocr source) ===')
con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
rows = con.execute("""SELECT log_date, shift, COUNT(*) FROM attendance_log
    WHERE source='signin_ocr' AND log_date >= '2026-07-28'
    GROUP BY log_date, shift ORDER BY log_date, shift""").fetchall()
for r in rows:
    print(f'  {r[0]} S{r[1]}: {r[2]}')

print('\n=== 3. MONITOR (stale alert) ===')
import subprocess
r = subprocess.run(['python3', '/Users/mainsobhelper/Desktop/REX/signin_email_monitor.py'],
                   capture_output=True, text=True, env={'PATH': '/Users/mainsobhelper/.rex-venv/bin:/usr/bin:/bin'})
print(f'  {r.stdout.strip() or "silent (healthy)"}')

print('\n=== 4. LAUNCHD AGENTS ===')
r = subprocess.run(['launchctl', 'list'], capture_output=True, text=True)
for line in r.stdout.splitlines():
    if 'signin' in line:
        print(f'  {line}')
con.close()
