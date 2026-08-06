#!/usr/bin/env python3
"""attendance_log full schema + a sample row."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('attendance_log columns:')
cols = con.execute("PRAGMA table_info(attendance_log)").fetchall()
for c in cols:
    print(f'  {c[1]} ({c[2]})')

print('\nsample rows:')
for r in con.execute("SELECT * FROM attendance_log WHERE source='ocr_signin' LIMIT 3"):
    print(f'  {r}')

print('\nunique keys on table:')
for r in con.execute("PRAGMA index_list(attendance_log)"):
    print(f'  {r}')
con.close()
