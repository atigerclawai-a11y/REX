#!/usr/bin/env python3
"""Plate truth for Tue Aug 4 + Wed Aug 5 (and full week): how many scheduled
clients get their OWN order (real form picks) vs fallbacks."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

for date, col, dayname in [('2026-08-04', 'day_T_actual', 'TUE Aug 4'),
                           ('2026-08-05', 'day_W_actual', 'WED Aug 5')]:
    print(f'\n{"="*58}\n{dayname} — {date}\n{"="*58}')
    for shift in (1, 2):
        sched = [r[0] for r in a.execute(f"SELECT name FROM clients WHERE active=1 AND {col}=?", (shift,))]
        rows = p.execute("""SELECT client_name, source_sheet FROM client_menus
            WHERE menu_date=? AND shift=? AND client_name IN (%s)"""
            % ','.join('?' * len(sched)), (date, shift, *sched)).fetchall() if sched else []
        by_src = {}
        for name, src in rows:
            by_src[src] = by_src.get(src, 0) + 1
        own = by_src.get('ocr_scan', 0) + by_src.get('day_shifted', 0) + by_src.get('last_order_fallback', 0)
        print(f'\n  S{shift}: {len(sched)} scheduled')
        for src in ['ocr_scan', 'day_shifted', 'last_order_fallback', 'house_standard']:
            print(f'    {src:<22} {by_src.get(src, 0)}')
        print(f'    {"OWN ORDER (real picks)":<22} {own}  ({100*own//max(len(sched),1)}%)')
        print(f'    {"HOUSE STANDARD (generic)":<22} {by_src.get("house_standard", 0)}')
a.close()
p.close()
