#!/usr/bin/env python3
"""Plate-truth audit for Tuesday Aug 4: how many scheduled clients get their
ACTUAL filled-out order (ocr_scan) vs fallbacks (day_shifted/last_order/house)."""
import sqlite3

DATE = '2026-08-04'
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

# Scheduled (attendance truth) from auth
a = sqlite3.connect(AUTH)
sched = a.execute("SELECT name, day_T_actual FROM clients WHERE active=1 AND day_T_actual IN (1,2)").fetchall()
a.close()

# Menu rows for Tuesday
p = sqlite3.connect(PROP)
rows = p.execute("""SELECT client_name, shift, source_sheet, salad, soup, main, side
    FROM client_menus WHERE menu_date=?""", (DATE,)).fetchall()
p.close()

# Map scheduled client -> best row (prefer ocr_scan > day_shifted > last_order > house)
by_client = {}
for name, shift, src, salad, soup, main_, side in rows:
    key = (name.strip().lower(), str(shift))
    complete = all([salad, soup, main_, side])
    prio = {'ocr_scan': 0, 'day_shifted': 1, 'drive_sync': 1, 'last_order_fallback': 2, 'house_standard': 3}.get(src, 4)
    if key not in by_client or prio < by_client[key][0]:
        by_client[key] = (prio, src, complete, salad, soup, main_, side)

from collections import Counter
stats = Counter()
no_row = []
for name, shift in sched:
    key = (name.strip().lower(), str(shift))
    if key not in by_client:
        no_row.append((name, shift))
        continue
    prio, src, complete, *_ = by_client[key]
    if not complete:
        stats['incomplete'] += 1
    else:
        stats[src] += 1

total = len(sched)
real = stats['ocr_scan']
shifted = stats['day_shifted'] + stats['drive_sync']
fallback = stats['last_order_fallback']
house = stats['house_standard']

print(f'Tuesday {DATE}: {total} scheduled (S1={sum(1 for _,s in sched if s==1)} S2={sum(1 for _,s in sched if s==2)})')
print(f'  REAL form order (ocr_scan):      {real}  ({100*real//total}%)')
print(f'  Same-week day-shift (day_shifted): {shifted}')
print(f'  Own history (last_order_fallback): {fallback}')
print(f'  House standard (generic):         {house}')
print(f'  Incomplete rows:                  {stats["incomplete"]}')
print(f'  No row at all:                    {len(no_row)}')
for n, s in no_row[:10]:
    print(f'    NO ROW: S{s} {n}')
