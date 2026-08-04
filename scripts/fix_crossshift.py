#!/usr/bin/env python3
"""Fix cross-shift dups: keep ocr_scan (real) row, set its shift from auth actuals,
delete the fallback duplicate. Then re-run shift mismatch fix."""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
for name in ['Tsiklauri Donara', 'Ukhach Borbala', 'Zhuga Margarita']:
    r = a.execute("SELECT name, shift, day_T_actual, day_W_actual FROM clients WHERE name=?", (name,)).fetchone()
    print(f'{name}: shift={r[1]} day_T={r[2]} day_W={r[3]}')
a.close()

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    p = sqlite3.connect(db)
    # delete last_order_fallback rows where an ocr_scan row exists same client+date+day
    rows = p.execute("""SELECT client_name, menu_date, day_code FROM client_menus
        WHERE menu_date IN ('2026-08-04','2026-08-05')""").fetchall()
    keys = set()
    for name, d, dc in rows:
        keys.add((name, d, dc))
    deleted = 0
    for name, d, dc in keys:
        ocr = p.execute("""SELECT rowid FROM client_menus WHERE client_name=? AND menu_date=?
            AND day_code=? AND source_sheet='ocr_scan'""", (name, d, dc)).fetchone()
        fb = p.execute("""SELECT rowid FROM client_menus WHERE client_name=? AND menu_date=?
            AND day_code=? AND source_sheet='last_order_fallback'""", (name, d, dc)).fetchone()
        if ocr and fb:
            p.execute("DELETE FROM client_menus WHERE rowid=?", (fb[0],))
            deleted += 1
    p.commit()
    print(f'{db.split("/")[-1]}: deleted {deleted} fallback dups (kept ocr_scan)')
    p.close()
