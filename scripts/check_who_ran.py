#!/usr/bin/env python3
"""Check: when did day_W_actual change? What ran between 13:18 and 20:09?"""
import sqlite3
from datetime import datetime
import os

# check cron output dirs for today
cron_out = '/Users/mainsobhelper/.hermes/profiles/work/cron/output'
print('=== cron outputs today (Aug 4) ===')
for d in sorted(os.listdir(cron_out)):
    p = os.path.join(cron_out, d)
    if not os.path.isdir(p):
        continue
    files = os.listdir(p)
    today = [f for f in files if f.startswith('2026-08-04')]
    if today:
        latest = max(today)
        mt = datetime.fromtimestamp(os.stat(os.path.join(p, latest)).st_mtime).strftime('%H:%M')
        print(f'  {d[:12]}: {latest[:16]} ({mt})')

# check executions db for 20:00 cron today
try:
    import json
    jobs = json.load(open('/Users/mainsobhelper/.hermes/profiles/work/cron/jobs.json'))
    jl = jobs if isinstance(jobs, list) else jobs.get('jobs', [])
    for j in jl:
        if j.get('job_id') == 'd5a36bd909c4':
            print(f'\n20:00 cron last_run: {j.get("last_run_at")}')
            print(f'  next_run: {j.get("next_run_at")}')
            print(f'  status: {j.get("last_status")}')
except Exception as e:
    print(f'jobs.json read: {e}')
