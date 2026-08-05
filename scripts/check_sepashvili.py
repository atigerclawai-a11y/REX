#!/usr/bin/env python3
"""Full detector_state + check Sepashvili attendance."""
import json
import sqlite3

st = json.load(open('/Users/mainsobhelper/.whatsapp_bridge/detector_state.json'))
print('=== ALL reported changes ===')
for rid in st.get('reported_ids', []):
    print(f'  {rid}')
print(f'\nlast_seen_ts: {st.get("last_seen_ts")}')

# Sepashvili in auth
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('\n=== Sepashvili in auth ===')
for row in a.execute("""SELECT name, active, day_M_actual, day_T_actual, day_W_actual,
    day_TH_actual, day_F_actual, shift FROM clients WHERE name LIKE '%Sepashvili%'"""):
    print(f'  {row}')

# what's in DB for Sepashvili this week
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
print('\n=== Sepashvili rows this week ===')
for row in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name LIKE '%Sepashvili%'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {row}')
a.close()
p.close()
