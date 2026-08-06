#!/usr/bin/env python3
"""attendance_log real schema + drive_signin_sync rows this week."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('attendance_log columns:')
for r in con.execute("PRAGMA table_info(attendance_log)"):
    print(f'  {r[1]} ({r[2]})')

print('\ndrive_signin_sync rows by date (recent):')
for r in con.execute("""SELECT log_date, COUNT(*) FROM attendance_log
    WHERE source='drive_signin_sync' GROUP BY log_date ORDER BY log_date DESC LIMIT 8"""):
    print(f'  {r[0]}: {r[1]}')

print('\nocr_signin rows by date (recent):')
for r in con.execute("""SELECT log_date, COUNT(*) FROM attendance_log
    WHERE source IN ('ocr_signin','ocr_signin_match') GROUP BY log_date ORDER BY log_date DESC LIMIT 8"""):
    print(f'  {r[0]}: {r[1]}')
con.close()
