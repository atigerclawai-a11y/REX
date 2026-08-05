#!/usr/bin/env python3
"""VERIFY Aug 5 (today): attendance + plates + coverage. Then cross-check:
are the 34 unreadable docs the SOURCE scans whose data was already recovered
via vision (227 confirmed forms), or are they genuinely missing data?"""
import json
import sqlite3
import os

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

print('=== AUG 5 (today) ATTENDANCE ===')
for shift in (1, 2):
    n = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_W_actual=?", (shift,)).fetchone()[0]
    print(f'  S{shift}: {n} scheduled')

print('\n=== AUG 5 PLATES ===')
for shift in (1, 2):
    sched = [r[0] for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=?", (shift,))]
    ph = ','.join('?' * len(sched))
    rows = p.execute(f"""SELECT client_name, salad, soup, main, side FROM client_menus
        WHERE menu_date='2026-08-05' AND shift=? AND client_name IN ({ph})""", (shift, *sched)).fetchall()
    have = {r[0] for r in rows}
    missing = [n for n in sched if n not in have]
    incomplete = [r[0] for r in rows if not all(r[1:5])]
    print(f'  S{shift}: {len(have)} plates / {len(sched)} scheduled, missing: {missing or "NONE"}, incomplete: {incomplete or "NONE"}')

print('\n=== SOURCES of Aug 5 plates ===')
for r in p.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
    WHERE menu_date='2026-08-05' GROUP BY 1 ORDER BY 2 DESC"""):
    print(f'  {r[0]}: {r[1]}')

print('\n=== ARE THE 34 DOCS THIS WEEK (Jul 27-31)? ===')
docs34 = json.load(open('/tmp/manifest_34.json'))
for docname, pages, path in docs34:
    d8 = docname.split('doc')[1][:8] if 'doc' in docname else '?'
    era = 'THIS-WEEK' if d8 >= '20260727' else 'OLDER'
    print(f'  {docname}: {d8} {era}')

a.close()
p.close()
