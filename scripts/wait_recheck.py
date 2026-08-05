#!/usr/bin/env python3
"""Wait 60s, recheck day_W_actual for re-zeroing."""
import sqlite3
import time

time.sleep(60)
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
s1 = a.execute('SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=1').fetchone()[0]
s2 = a.execute('SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=2').fetchone()[0]
print(f'day_W_actual after 60s: {s1}/{s2} {"OK" if (s1, s2) == (73, 95) else "RE-ZEROED"}')
a.close()
