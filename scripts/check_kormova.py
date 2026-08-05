#!/usr/bin/env python3
"""Check Kormova Lyubov active=0 + her history + the TUE real gaps."""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('=== Kormova Lyubov ===')
for r in a.execute("""SELECT name, active, client_id, day_M_actual, day_T_actual, day_W_actual,
    day_TH_actual, day_F_actual FROM clients WHERE name LIKE '%Kormova%'"""):
    print(f'  auth: {r}')

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\n  plates this week:')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name LIKE '%Kormova%'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'    {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

# Tuesday real gaps: Carecenta Tue 139 vs auth 137
import json
cc = json.load(open('/tmp/carecenta_clients_week.json'))
au_t = {r[0].lower() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_T_actual IN (1,2)")}
print('\n=== TUE real gaps (Carecenta-only, no surname match) ===')
cc_tue = {name for name, days in cc if '3' in {str(d) for d in days}}
for n in sorted(cc_tue):
    if n.lower() in au_t:
        continue
    sur = n.split()[0].lower()
    hits = [r[0] for r in a.execute("SELECT name FROM clients WHERE name LIKE ?", (f'%{sur}%',))]
    if not hits:
        print(f'  ⚠️ {n} — NO MATCH')
a.close()
p.close()
