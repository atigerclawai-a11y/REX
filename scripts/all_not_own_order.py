#!/usr/bin/env python3
"""COMPLETE LIST: every scheduled client NOT receiving their OWN order this week,
with the reason (house_standard = no order found / gap = no plate / wrong data).
Per day, per shift. Only days with issues."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

DAYS = [('2026-08-03', 'day_M_actual', 'MON Aug 3'), ('2026-08-04', 'day_T_actual', 'TUE Aug 4'),
        ('2026-08-05', 'day_W_actual', 'WED Aug 5'), ('2026-08-06', 'day_TH_actual', 'THU Aug 6'),
        ('2026-08-07', 'day_F_actual', 'FRI Aug 7')]

for date, col, label in DAYS:
    issues = []
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
                issues.append((name, shift, 'GAP — no plate at all'))
            else:
                src = have[name][1]
                if src == 'house_standard':
                    issues.append((name, shift, 'HOUSE STANDARD — no own order found in system'))
                elif src == 'last_order_fallback':
                    # own recent order — this IS their own order, fine
                    pass
                elif src == 'ocr_scan' or src == 'day_shifted':
                    pass
                # check incomplete plates
                cells = have[name][2:6]
                if any(not c for c in cells):
                    issues.append((name, shift, f'INCOMPLETE plate ({src}): {cells[0]}|{cells[1]}|{cells[2]}|{cells[3]}'))
    if issues:
        print(f'\n=== {label} — {len(issues)} clients with issues ===')
        for name, shift, reason in sorted(issues):
            print(f'  S{shift} {name}: {reason}')

a.close()
p.close()
