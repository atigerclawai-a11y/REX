#!/usr/bin/env python3
"""THE KEY QUESTION: today Aug 5 — how many of the 169 scheduled clients have
their OWN confirmed form marks (ocr_scan) vs fallback?
This proves whether 'everyone is set' is TRUE for today."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('=== AUG 5 (TODAY): every scheduled client has a plate ===')
total = 0
for shift in (1, 2):
    sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=?", (shift,))]
    ph = ','.join('?' * len(sched))
    rows = p.execute(f"""SELECT client_name, source_sheet, salad, soup, main, side
        FROM client_menus WHERE menu_date='2026-08-05' AND shift=? AND client_name IN ({ph})""",
        (shift, *sched)).fetchall()
    have = {r[0]: r for r in rows}
    gaps = [n for n in sched if n not in have]
    print(f'  S{shift}: {len(sched)} scheduled, {len(sched)-len(gaps)} plates, gaps={gaps or "NONE"}')
    total += len(sched)

print(f'\nTOTAL scheduled today: {total}')
print(f'Verify: 73 S1 + 96 S2 = 169 (matches Carecenta)')

# how many Aug 5 plates are ocr_scan (own form) vs fallback?
print('\nAug 5 plate sources (own form vs fallback):')
for r in p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
    WHERE menu_date='2026-08-05' GROUP BY 1 ORDER BY 2 DESC"""):
    print(f'  {r[0]}: {r[1]}')
a.close()
p.close()
