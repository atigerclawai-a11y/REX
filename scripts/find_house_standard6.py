#!/usr/bin/env python3
"""Find the 6 house_standard clients on Tue/Wed and check their history."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

for date, col, dayname in [('2026-08-04', 'day_T_actual', 'TUE Aug 4'),
                           ('2026-08-05', 'day_W_actual', 'WED Aug 5')]:
    sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col} IN (1,2)")]
    if not sched:
        continue
    ph = ','.join('?' * len(sched))
    rows = p.execute(f"""SELECT client_name, shift, source_sheet FROM client_menus
        WHERE menu_date=? AND client_name IN ({ph}) AND source_sheet='house_standard'""",
        (date, *sched)).fetchall()
    for name, shift, src in rows:
        # ANY history at all?
        hist = p.execute("""SELECT COUNT(*) FROM client_menus WHERE client_name=?""", (name,)).fetchone()[0]
        # most recent rows
        recent = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
            FROM client_menus WHERE client_name=? ORDER BY menu_date DESC LIMIT 5""", (name,)).fetchall()
        print(f'\n=== {name} — {date} S{shift} [house_standard] — total history rows: {hist}')
        for r in recent:
            print(f'    {r[0]} {r[1]}: {r[2]}|{r[3]}|{r[4]}|{r[5]} [{r[6]}]')
a.close()
p.close()
