#!/usr/bin/env python3
"""Facts: how many active clients, how many have sheets/menus per day this week."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
con = sqlite3.connect(AUTH)

total = con.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
print(f'active clients: {total}')

print('\nper-day actual attendance (week 31, Aug 3-7):')
for day, col in [('Mon', 'day_M_actual'), ('Tue', 'day_T_actual'),
                 ('Wed', 'day_W_actual'), ('Thu', 'day_TH_actual'),
                 ('Fri', 'day_F_actual')]:
    s1 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1").fetchone()[0]
    s2 = con.execute(f"SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2").fetchone()[0]
    print(f'  {day}: S1={s1} S2={s2} total={s1+s2}')

# clients with NO attendance this week at all
no_any = con.execute("""SELECT COUNT(*) FROM clients WHERE active=1
    AND day_M_actual NOT IN (1,2) AND day_T_actual NOT IN (1,2)
    AND day_W_actual NOT IN (1,2) AND day_TH_actual NOT IN (1,2)
    AND day_F_actual NOT IN (1,2)""").fetchone()[0]
print(f'\nactive clients with NO attendance this week (Mon-Fri): {no_any}')
con.close()

# sheets on disk
import os
OUT = '/Users/mainsobhelper/Documents/goj files/output_docs'
files = [f for f in os.listdir(OUT) if f.endswith('.pdf') and ('Tuesday' in f or 'Wednesday' in f or 'Monday' in f or 'Thursday' in f or 'Friday' in f)]
print(f'\nsheet PDFs on disk: {len(files)}')
for f in sorted(files):
    print(f'  {f} ({os.path.getsize(os.path.join(OUT, f))//1024} KB)')
