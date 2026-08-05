#!/usr/bin/env python3
"""What's writing day_W_actual? Check attendance_log writes + all scripts that
UPDATE day_W_actual, and search for the value 64/96 signature."""
import sqlite3
import os
import subprocess

# scripts that UPDATE day_W_actual
print('=== scripts with UPDATE day_W_actual ===')
r = subprocess.run(['grep', '-rln', 'UPDATE clients SET day_W_actual', 
                    '/Users/mainsobhelper/.hermes/profiles/work/scripts/',
                    '/Users/mainsobhelper/Desktop/REX/'],
                   capture_output=True, text=True)
for line in r.stdout.splitlines():
    print(f'  {line}')

# check attendance_log recent writes
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
try:
    print('\n=== attendance_log recent ===')
    rows = a.execute("SELECT * FROM attendance_log ORDER BY rowid DESC LIMIT 10").fetchall()
    for r in rows:
        print(f'  {r}')
except Exception as e:
    print(f'  no attendance_log: {e}')
a.close()
