#!/usr/bin/env python3
"""Verify: signin_ocr rows now in attendance_log for Jul 28-30."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('signin_ocr rows by date:')
for r in con.execute("""SELECT log_date, shift, COUNT(*) FROM attendance_log
    WHERE source='signin_ocr' AND log_date >= '2026-07-28'
    GROUP BY log_date, shift ORDER BY log_date, shift"""):
    print(f'  {r[0]} S{r[1]}: {r[2]}')

# sample
print('\nsample:')
for r in con.execute("""SELECT log_date, day_key, shift, client_name, status, source
    FROM attendance_log WHERE source='signin_ocr' AND log_date >= '2026-07-28'
    ORDER BY log_date LIMIT 5"""):
    print(f'  {r}')
con.close()
