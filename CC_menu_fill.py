#!/usr/bin/env python3
"""
CC_menu_fill.py <YYYY-MM-DD> — complete per-attendee menu fill (Kato 2026-07-27):
EVERY Carecenta-attending client gets a menu row for each attended day. Chain:
  1. ocr_scan (real form — untouched)
  2. day_shifted (their picks from another day this week — Kato's travel rule)
  3. last_order_fallback (their own most recent order)
  4. house_standard (mode of valid orders for that shift/date)
Attendance source: auth_tracker day_*_actual (Carecenta-truth, set by preflight).
Idempotent. Writes BOTH DBs. Reports counts per tier + per-shift totals.
"""
import sqlite3, sys
from datetime import date, timedelta
from collections import Counter

DATE = sys.argv[1] if len(sys.argv) > 1 else '2026-07-28'
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

dt = date.fromisoformat(DATE)
week_sun = dt - timedelta(days=(dt.weekday() + 1) % 7)
week_dates = [(week_sun + timedelta(days=i)).isoformat() for i in range(7)]
DAYCOL = {0: 'day_M_actual', 1: 'day_T_actual', 2: 'day_W_actual', 3: 'day_TH_actual',
          4: 'day_F_actual', 6: 'day_Su_actual'}
col = DAYCOL[dt.weekday()]
day_code = {0: 'M', 1: 'T', 2: 'W', 3: 'TH', 4: 'F', 6: 'Su'}[dt.weekday()]

a = sqlite3.connect(AUTH)
attending = a.execute(f'SELECT name, {col} FROM clients WHERE active=1 AND {col} IN (1,2)').fetchall()
a.close()
s1 = sum(1 for _, s in attending if s == 1)
s2 = sum(1 for _, s in attending if s == 2)

stats = Counter()
for db in DBS:
    c = sqlite3.connect(db)
    # house standard per shift from the day's valid orders
    std = {}
    for shift in ('1', '2'):
        combos = c.execute("""SELECT salad, soup, main, side FROM client_menus
            WHERE menu_date=? AND shift=? AND source_sheet IN ('ocr_scan','last_order_fallback','day_shifted')
            AND main NOT LIKE '%заказ не размещен%' AND main != ''""", (DATE, shift)).fetchall()
        if combos:
            std[shift] = Counter(combos).most_common(1)[0][0]
    for name, shift in attending:
        sh = str(shift)
        have = c.execute('SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?',
                         (name, DATE, sh)).fetchone()[0]
        if have:
            stats['already'] += 1
            continue
        # 2. day-shift: same-week ocr picks, nearest day
        row = c.execute("""SELECT menu_date, salad, soup, main, side FROM client_menus
            WHERE client_name=? AND shift=? AND source_sheet='ocr_scan' AND menu_date != ?
            AND menu_date BETWEEN ? AND ? ORDER BY ABS(julianday(menu_date)-julianday(?)) LIMIT 1""",
            (name, sh, DATE, week_dates[0], week_dates[-1], DATE)).fetchone()
        if row:
            src, salad, soup, main_, side = row
            # complete missing components from own history
            if not all([salad, soup, main_, side]):
                for h in c.execute("""SELECT salad, soup, main, side FROM client_menus
                    WHERE client_name=? AND shift=? AND main NOT LIKE '%заказ не размещен%' AND main != ''
                    ORDER BY menu_date DESC LIMIT 5""", (name, sh)):
                    salad, soup, main_, side = salad or h[0], soup or h[1], main_ or h[2], side or h[3]
                    if all([salad, soup, main_, side]): break
            c.execute("""INSERT OR IGNORE INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at)
                VALUES (?,?,?,?,?,?,?,?,'day_shifted',datetime('now'))""",
                (name, DATE, day_code, sh, salad or '', soup or '', main_ or '', side or ''))
            stats['day_shifted'] += 1
            continue
        # 3. own last order
        lw = c.execute("""SELECT salad, soup, main, side FROM client_menus
            WHERE client_name=? AND shift=? AND main NOT LIKE '%заказ не размещен%' AND main != ''
            ORDER BY menu_date DESC LIMIT 1""", (name, sh)).fetchone()
        if lw:
            c.execute("""INSERT OR IGNORE INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at)
                VALUES (?,?,?,?,?,?,?,?,'last_order_fallback',datetime('now'))""",
                (name, DATE, day_code, sh, lw[0] or '', lw[1] or '', lw[2] or '', lw[3] or ''))
            stats['fallback'] += 1
        elif sh in std:
            c.execute("""INSERT OR IGNORE INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at)
                VALUES (?,?,?,?,?,?,?,?,'house_standard',datetime('now'))""",
                (name, DATE, day_code, sh, std[sh][0], std[sh][1], std[sh][2], std[sh][3]))
            stats['house'] += 1
        else:
            stats['UNFILLED'] += 1
    c.commit()
    c.close()

per_db = {k: v // 2 for k, v in stats.items()}
total = len(attending)
covered = total - per_db.get('UNFILLED', 0)
print(f'{DATE} ({day_code}): attending S1={s1} S2={s2} total={total}')
print(f'  already had row: {per_db.get("already",0)} | day_shifted: {per_db.get("day_shifted",0)} '
      f'| fallback: {per_db.get("fallback",0)} | house: {per_db.get("house",0)} | UNFILLED: {per_db.get("UNFILLED",0)}')
print(f'  coverage: {covered}/{total} = {100*covered//total}%')
