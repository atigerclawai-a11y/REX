#!/usr/bin/env python3
"""Check remaining Thu gaps (scheduled but no plate) + verify house count now."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('=== THU plates by source (after fix) ===')
for r in p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
    WHERE menu_date='2026-08-06' GROUP BY 1 ORDER BY 2 DESC"""):
    print(f'  {r[0]}: {r[1]}')

print('\n=== THU scheduled but no plate (gaps) ===')
for shift in (1, 2):
    sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_TH_actual=?", (shift,))]
    ph = ','.join('?' * len(sched))
    have = set(r[0] for r in p.execute(f"SELECT client_name FROM client_menus WHERE menu_date='2026-08-06' AND shift=? AND client_name IN ({ph})", (shift, *sched)))
    gaps = [n for n in sched if n not in have]
    print(f'  S{shift}: {len(sched)} sched, {len(sched)-len(gaps)} plates, {len(gaps)} gaps: {gaps}')
a.close()
p.close()
