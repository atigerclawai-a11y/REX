#!/usr/bin/env python3
"""Name-level plate-truth for Tuesday Aug 4: who gets real order vs fallback."""
import sqlite3

DATE = '2026-08-04'
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
sched = a.execute("SELECT name, day_T_actual FROM clients WHERE active=1 AND day_T_actual IN (1,2)").fetchall()
a.close()

p = sqlite3.connect(PROP)
rows = p.execute("""SELECT client_name, shift, source_sheet, salad, soup, main, side
    FROM client_menus WHERE menu_date=?""", (DATE,)).fetchall()
p.close()

by_client = {}
for name, shift, src, salad, soup, main_, side in rows:
    key = (name.strip().lower(), str(shift))
    complete = all([salad, soup, main_, side])
    prio = {'ocr_scan': 0, 'day_shifted': 1, 'drive_sync': 1, 'last_order_fallback': 2, 'house_standard': 3}.get(src, 4)
    if key not in by_client or prio < by_client[key][0]:
        by_client[key] = (prio, src, complete, salad, soup, main_, side, name)

for label, want in [('REAL ocr_scan', 'ocr_scan'), ('day_shifted', 'day_shifted'),
                    ('last_order_fallback', 'last_order_fallback'), ('house_standard', 'house_standard')]:
    names = []
    for name, shift in sched:
        key = (name.strip().lower(), str(shift))
        if key in by_client and by_client[key][1] == want:
            names.append(f"S{shift}:{by_client[key][7]}")
    print(f'{label} ({len(names)}):')
    for n in sorted(names):
        print(f'  {n}')

# incomplete
print('INCOMPLETE (needs top-up):')
for name, shift in sched:
    key = (name.strip().lower(), str(shift))
    if key in by_client and not by_client[key][2]:
        _, src, _, sal, sou, mai, sid, nm = by_client[key]
        print(f'  S{shift} {nm} [{src}]: {sal} | {sou} | {mai} | {sid}')
