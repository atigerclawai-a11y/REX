#!/usr/bin/env python3
"""Verify: Wed should now be 73 S1 + 96 S2 = 169 (Carecenta truth, incl Kormova).
Tue: 81 S1 + 55 S2 = 136 minus Kravets Sima sick = 80/55? Verify each client."""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for col, label in [('day_T_actual', 'TUE'), ('day_W_actual', 'WED')]:
    s1 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=1').fetchone()[0]
    s2 = a.execute(f'SELECT COUNT(*) FROM clients WHERE active=1 AND {col}=2').fetchone()[0]
    print(f'{label}: S1={s1} S2={s2} total={s1+s2}')

# Kravets Sima check
r = a.execute("SELECT name, active, day_T_actual FROM clients WHERE name='Kravets Sima'").fetchone()
print(f'\nKravets Sima: {r} (should be Tue=0, sick)')
# Kormova
r = a.execute("SELECT name, active, day_W_actual FROM clients WHERE name='Kormova Lyubov'").fetchone()
print(f'Kormova Lyubov: {r} (should be active=1, Wed=2)')
a.close()
