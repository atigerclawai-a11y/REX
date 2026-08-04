#!/usr/bin/env python3
"""Check: Monday DB actuals vs base (was Monday clobbered too?), _superseded contents."""
import sqlite3
import os

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
con = sqlite3.connect(AUTH)
print('=== Monday: actual vs base ===')
s1a = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_M_actual=1").fetchone()[0]
s2a = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_M_actual=2").fetchone()[0]
s1b = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_M_base=1").fetchone()[0]
s2b = con.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_M_base=2").fetchone()[0]
print(f'  day_M_actual: S1={s1a} S2={s2a} (total {s1a+s2a})')
print(f'  day_M_base:   S1={s1b} S2={s2b} (total {s1b+s2b})')
for day, col in [('Tue', 'day_T_actual'), ('Tue', 'day_T_base'),
                 ('Wed', 'day_W_actual'), ('Wed', 'day_W_base'),
                 ('Thu', 'day_TH_actual'), ('Thu', 'day_TH_base'),
                 ('Fri', 'day_F_actual'), ('Fri', 'day_F_base')]:
    s1 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    s2 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    print(f'  {col}: S1={s1} S2={s2} total={s1+s2}')
con.close()

print('\n=== _superseded (what the cron moved) ===')
SUP = '/Users/mainsobhelper/Documents/goj files/output_docs/_superseded'
if os.path.isdir(SUP):
    for f in sorted(os.listdir(SUP)):
        if 'Tue' in f or 'Wed' in f or 'Mon' in f:
            p = os.path.join(SUP, f)
            print(f'  {os.path.getsize(p)//1024} KB  {f}')
