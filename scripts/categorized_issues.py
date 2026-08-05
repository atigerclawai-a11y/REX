#!/usr/bin/env python3
"""CLEAN SUMMARY by category: GAP / HOUSE / INCOMPLETE per day."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

DAYS = [('2026-08-03', 'day_M_actual', 'MON'), ('2026-08-04', 'day_T_actual', 'TUE'),
        ('2026-08-05', 'day_W_actual', 'WED'), ('2026-08-06', 'day_TH_actual', 'THU'),
        ('2026-08-07', 'day_F_actual', 'FRI')]

for date, col, label in DAYS:
    gaps, house, incomplete = [], [], []
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        if not sched:
            continue
        ph = ','.join('?' * len(sched))
        rows = p.execute(f"""SELECT client_name, source_sheet, salad, soup, main, side
            FROM client_menus WHERE menu_date=? AND shift=? AND client_name IN ({ph})""",
            (date, shift, *sched)).fetchall()
        have = {r[0]: r for r in rows}
        for name in sched:
            if name not in have:
                gaps.append((shift, name))
            else:
                src = have[name][1]
                cells = have[name][2:6]
                if src == 'house_standard':
                    house.append((shift, name))
                elif any(not c for c in cells):
                    incomplete.append((shift, name, cells))
    print(f'\n=== {label} ===')
    print(f'  GAPS (no plate): {len(gaps)}')
    for s, n in sorted(gaps):
        print(f'    S{s} {n}')
    print(f'  HOUSE STANDARD: {len(house)}')
    for s, n in sorted(house):
        print(f'    S{s} {n}')
    print(f'  INCOMPLETE (missing cells): {len(incomplete)}')
    for s, n, c in sorted(incomplete):
        print(f'    S{s} {n}: {c[0]}|{c[1]}|{c[2]}|{c[3]}')
a.close()
p.close()
