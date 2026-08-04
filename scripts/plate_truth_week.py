#!/usr/bin/env python3
"""PLATE TRUTH — full analysis of every scheduled client's order (Aug 3-7).
Classes: A=this-week form (ocr_scan) B=own picks other day (day_shifted)
C=own last order (last_order_fallback) D=house standard E=NO PLATE (true gap)."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

DAYS = [('2026-08-03', 'day_M_actual', 'MON'), ('2026-08-04', 'day_T_actual', 'TUE'),
        ('2026-08-05', 'day_W_actual', 'WED'), ('2026-08-06', 'day_TH_actual', 'THU'),
        ('2026-08-07', 'day_F_actual', 'FRI')]

tot_sched = tot_plate = 0
for date, col, label in DAYS:
    print(f'\n{"="*62}\n{label} {date}\n{"="*62}')
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
        n_plate = sum(by_src.values())
        n_gap = len(sched) - n_plate
        own = by_src.get('ocr_scan', 0) + by_src.get('day_shifted', 0) + by_src.get('last_order_fallback', 0)
        pct = 100 * own // max(len(sched), 1)
        print(f'  S{shift}: {len(sched)} sched | plates {n_plate} | '
              f'ocr={by_src.get("ocr_scan",0)} shifted={by_src.get("day_shifted",0)} '
              f'fallback={by_src.get("last_order_fallback",0)} house={by_src.get("house_standard",0)} '
              f'GAP={n_gap} | own-order {own} ({pct}%)')
        tot_sched += len(sched)
        tot_plate += n_plate

print(f'\n{"="*62}\nTOTALS: {tot_sched} scheduled, {tot_plate} plates, {tot_sched - tot_plate} gaps')
a.close()
p.close()
