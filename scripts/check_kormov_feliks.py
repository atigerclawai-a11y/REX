#!/usr/bin/env python3
"""Kormov Feliks: check auth + his Carecenta schedule."""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('auth matches:')
for r in a.execute("SELECT client_id, name, active, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual FROM clients WHERE name LIKE '%Kormov%'"):
    print(f'  {r}')
print('\ncanonical:')
for r in a.execute("SELECT * FROM canonical_ids WHERE name LIKE '%Kormov%'"):
    print(f'  {r}')
a.close()
