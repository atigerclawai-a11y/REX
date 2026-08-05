#!/usr/bin/env python3
"""Check attendance + plates for ALL WhatsApp-flagged clients."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

CHANGES = [
    ('Sepashvili', 'moved Fri → Tue (Oleg 08-04 12:11)'),
    ('Polyak', 'MD appointment today (Oleg 08-04 08:39)'),
    ('Shefer', 'out ALL WEEK resting (Valeri 08-03 07:29)'),
    ('Bok', 'going to doctor (Ravil 08-03 07:53)'),
    ('Ruvinskaya', 'road flooded (Ravil 08-03 12:02)'),
    ('Slavinskiy', 'road flooded (Ravil 08-03 12:02)'),
    ('Nezgevenko', 'out - дела (Ravil)'),
    ('Yampolskiy', 'vacation until Aug 7 (Oleg 07-28)'),
    ('Keyserman', 'приедет сама (Valeri 08-03 09:48)'),
]

for frag, note in CHANGES:
    print(f'\n=== {frag} — {note} ===')
    for row in a.execute("""SELECT name, active, day_M_actual, day_T_actual, day_W_actual,
        day_TH_actual, day_F_actual FROM clients WHERE name LIKE ?""", (f'%{frag}%',)):
        print(f'  auth: {row}')
        # plates this week
        for r in p.execute("""SELECT menu_date, day_code, shift, source_sheet FROM client_menus
            WHERE client_name=? AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
            ORDER BY menu_date""", (row[0],)):
            print(f'    plate {r[0]} {r[1]} S{r[2]} [{r[3]}]')
a.close()
p.close()
