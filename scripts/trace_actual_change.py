#!/usr/bin/env python3
"""Trace: when did day_T_actual change from 81/55 to 76/47?
Check auth DB mtime + sign-in bridge + carecenta sync logs."""
import os
import sqlite3
from datetime import datetime

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
st = os.stat(AUTH)
print(f'auth DB mtime: {datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M:%S")}')

a = sqlite3.connect(AUTH)
print('current day_T_actual:', a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=1").fetchone()[0],
      '/', a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_T_actual=2").fetchone()[0])
# check who's marked actual but not base (or vice versa)
rows = a.execute("""SELECT name, day_T_base, day_T_actual, day_W_actual FROM clients
    WHERE active=1 AND (day_T_base IS NOT day_T_actual OR day_T_actual IN (1,2)) AND (day_T_base IN (1,2) OR day_T_actual IN (1,2))
    ORDER BY name LIMIT 60""").fetchall()
print(f'\nclients where Tue base != actual: {len(rows)}')
for r in rows[:40]:
    print(f'  {r[0]}: base={r[1]} actual={r[2]} (Wed={r[3]})')
a.close()

# sign-in bridge log
for lg in ['/Users/mainsobhelper/Desktop/REX/signin_bridge.log',
           '/Users/mainsobhelper/Documents/goj files/logs/signin_bridge.log']:
    if os.path.exists(lg):
        lines = open(lg, errors='ignore').read().splitlines()
        print(f'\n{lg} last 10:')
        for l in lines[-10:]:
            print(f'  {l}')
