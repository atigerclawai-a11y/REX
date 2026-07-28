#!/usr/bin/env python3
"""
CC_menu_dayshift.py <YYYY-MM-DD> — Kato rule 2026-07-27:
"If they change their day of attendance we move the menu choice with them."

For every client attending <date> (auth_tracker day_*_actual) who has NO menu row
for that date+shift, look for their ocr_scan picks on OTHER days of the SAME menu
week (Sun-Sat containing <date>). If found, copy the nearest day's picks to <date>
with source_sheet='day_shifted'. Priority chain remains:
  same-day ocr_scan -> day_shifted (same-week ocr) -> last_order_fallback -> house_standard.

Idempotent: INSERT OR IGNORE, never overwrites existing rows. Writes BOTH DBs.
--dry-run prints what would happen without writing.
"""
import sqlite3, sys
from datetime import date, timedelta

DATE = sys.argv[1] if len(sys.argv) > 1 else '2026-07-28'
DRY = '--dry-run' in sys.argv
DBS = ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
       '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'

dt = date.fromisoformat(DATE)
week_sun = dt - timedelta(days=(dt.weekday() + 1) % 7)
week_dates = [(week_sun + timedelta(days=i)).isoformat() for i in range(7)]
DAYCOL = {0: 'day_M_actual', 1: 'day_T_actual', 2: 'day_W_actual', 3: 'day_TH_actual',
          4: 'day_F_actual', 6: 'day_Su_actual'}
col = DAYCOL.get(dt.weekday())
assert col, f'no day column for weekday {dt.weekday()}'
day_code = {0: 'M', 1: 'T', 2: 'W', 3: 'TH', 4: 'F', 6: 'Su'}[dt.weekday()]

a = sqlite3.connect(AUTH)
attending = a.execute(f'SELECT name, {col} FROM clients WHERE active=1 AND {col} IN (1,2)').fetchall()
a.close()

shifted, skipped_have, no_source = [], 0, []
for db in DBS[:1]:  # compute from primary
    c = sqlite3.connect(db)
    for name, shift in attending:
        have = c.execute('SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?',
                         (name, DATE, str(shift))).fetchone()[0]
        if have:
            skipped_have += 1
            continue
        # same-week ocr rows, nearest day first
        rows = c.execute("""SELECT menu_date, salad, soup, main, side FROM client_menus
            WHERE client_name=? AND shift=? AND source_sheet='ocr_scan' AND menu_date != ?
            AND menu_date BETWEEN ? AND ? ORDER BY ABS(julianday(menu_date) - julianday(?))""",
            (name, str(shift), DATE, week_dates[0], week_dates[-1], DATE)).fetchall()
        if rows:
            src_date, salad, soup, main, side = rows[0]
            # fill missing components from client's own history (any past order, same shift)
            if not all([salad, soup, main, side]):
                hist = c.execute("""SELECT salad, soup, main, side FROM client_menus
                    WHERE client_name=? AND shift=? AND main NOT LIKE '%заказ не размещен%'
                    ORDER BY menu_date DESC LIMIT 5""", (name, str(shift))).fetchall()
                for h in hist:
                    salad = salad or h[0]
                    soup = soup or h[1]
                    main = main or h[2]
                    side = side or h[3]
                    if all([salad, soup, main, side]):
                        break
            shifted.append((name, shift, (src_date, salad, soup, main, side)))
        else:
            no_source.append(name)
    c.close()

print(f'{DATE} ({day_code}): attending={len(attending)} already-have-menu={skipped_have} '
      f'day-shift candidates={len(shifted)} no-source-at-all={len(no_source)}')
for name, shift, (src_date, salad, soup, main, side) in shifted[:40]:
    print(f'  S{shift} {name}: {src_date} picks -> {DATE} [{salad}|{soup}|{main}|{side}]')

if not DRY and shifted:
    for db in DBS:
        c = sqlite3.connect(db)
        n = 0
        for name, shift, (src_date, salad, soup, main, side) in shifted:
            cur = c.execute("""INSERT OR IGNORE INTO client_menus
                (client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'day_shifted', datetime('now'))""",
                (name, DATE, day_code, str(shift), salad, soup, main, side))
            n += cur.rowcount
        c.commit()
        c.close()
        print(f'{db.split("/")[-2]}: inserted {n} day_shifted rows')
elif DRY:
    print('(dry run — no writes)')
