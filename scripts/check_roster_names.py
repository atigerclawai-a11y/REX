#!/usr/bin/env python3
"""Check roster for Gukovskaja / Rapouk / Papouk candidates."""
import sqlite3

con = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('Gukovskaja candidates:')
for r in con.execute("SELECT name, active FROM clients WHERE name LIKE '%ukovsk%' OR name LIKE '%iukov%'"):
    print(' ', r)
print('Rapouk/Papouk candidates:')
for r in con.execute("SELECT name, active FROM clients WHERE name LIKE '%apouk%' OR name LIKE '%apoun%'"):
    print(' ', r)
con.close()
