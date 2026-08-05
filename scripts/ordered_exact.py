#!/usr/bin/env python3
"""How many clients receive EXACTLY what they ordered (their own form picks)?
Classes: ocr_scan = exact form mark (what they specifically ordered this week)
day_shifted = their own picks from another day they attend
last_order_fallback = their own MOST RECENT order from history (not this week's form)
house_standard = generic house plate (NOT what they ordered)"""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

DAYS = [('2026-08-03', 'day_M_actual', 'MON'), ('2026-08-04', 'day_T_actual', 'TUE'),
        ('2026-08-05', 'day_W_actual', 'WED'), ('2026-08-06', 'day_TH_actual', 'THU'),
        ('2026-08-07', 'day_F_actual', 'FRI')]

grand = {'ocr_scan': 0, 'day_shifted': 0, 'last_order_fallback': 0, 'house_standard': 0, 'GAP': 0, 'sched': 0}
for date, col, label in DAYS:
    print(f'\n{label} {date}:')
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        if not sched:
            continue
        ph = ','.join('?' * len(sched))
        rows = p.execute(f"""SELECT client_name, source_sheet FROM client_menus
            WHERE menu_date=? AND shift=? AND client_name IN ({ph})""",
            (date, shift, *sched)).fetchall()
        by_src = {}
        for name, src in rows:
            by_src[src] = by_src.get(src, 0) + 1
        n_gap = len(sched) - sum(by_src.values())
        exact = by_src.get('ocr_scan', 0)
        own_other_day = by_src.get('day_shifted', 0)
        own_recent = by_src.get('last_order_fallback', 0)
        house = by_src.get('house_standard', 0)
        print(f'  S{shift} ({len(sched)}): EXACT={exact} own-other-day={own_other_day} '
              f'own-recent={own_recent} house={house} gap={n_gap}')
        grand['ocr_scan'] += exact
        grand['day_shifted'] += own_other_day
        grand['last_order_fallback'] += own_recent
        grand['house_standard'] += house
        grand['GAP'] += n_gap
        grand['sched'] += len(sched)

print(f'\n{"="*62}')
print(f'WEEK TOTAL ({grand["sched"]} scheduled):')
print(f'  EXACTLY what they ordered this week (ocr_scan): {grand["ocr_scan"]} '
      f'({100*grand["ocr_scan"]//grand["sched"]}%)')
print(f'  Their own picks from another day (day_shifted): {grand["day_shifted"]} '
      f'({100*grand["day_shifted"]//grand["sched"]}%)')
print(f'  Their own most-recent order (fallback): {grand["last_order_fallback"]} '
      f'({100*grand["last_order_fallback"]//grand["sched"]}%)')
print(f'  THEIR OWN FOOD total: {grand["ocr_scan"]+grand["day_shifted"]+grand["last_order_fallback"]} '
      f'({100*(grand["ocr_scan"]+grand["day_shifted"]+grand["last_order_fallback"])//grand["sched"]}%)')
print(f'  House standard (NOT their order): {grand["house_standard"]} '
      f'({100*grand["house_standard"]//grand["sched"]}%)')
print(f'  TRUE GAPS (no plate): {grand["GAP"]}')
a.close()
p.close()
