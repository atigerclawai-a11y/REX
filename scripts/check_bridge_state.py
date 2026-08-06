#!/usr/bin/env python3
"""Check bridge state + attendance_log in both auth DBs."""
import json
import os
import sqlite3

STATE = os.path.expanduser('~/.hermes/profiles/work/state/signin_attendance_processed.json')
if os.path.exists(STATE):
    st = json.load(open(STATE))
    print(f'bridge state: {st}')
else:
    print('bridge state: MISSING')

print('\n=== attendance_log in canonical auth DB ===')
for db in ['/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db',
           '/Users/mainsobhelper/Desktop/REX/auth_tracker.db']:
    if os.path.exists(db):
        con = sqlite3.connect(db)
        t = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance_log'").fetchone()
        if t:
            n = con.execute("SELECT COUNT(*) FROM attendance_log").fetchone()[0]
            srcs = con.execute("SELECT source, COUNT(*) FROM attendance_log GROUP BY 1").fetchall()
            print(f'{os.path.basename(os.path.dirname(os.path.dirname(db)))}: {n} rows, sources: {srcs}')
            # recent
            for r in con.execute("SELECT date, shift, client_name, source FROM attendance_log ORDER BY id DESC LIMIT 5"):
                print(f'    {r[0]} S{r[1]} {r[2]} [{r[3]}]')
        else:
            print(f'{os.path.basename(os.path.dirname(os.path.dirname(db)))}: no attendance_log table')
        con.close()
