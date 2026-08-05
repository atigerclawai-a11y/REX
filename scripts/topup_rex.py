#!/usr/bin/env python3
"""Run the same top-up on the REX copy."""
import sqlite3

SRC = '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db'
con = sqlite3.connect(SRC)
rows = con.execute("""SELECT rowid, client_name, menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND (salad IS NULL OR salad='' OR soup IS NULL OR soup=''
      OR main IS NULL OR main='' OR side IS NULL OR side='')""").fetchall()
print(f'incomplete rows in REX: {len(rows)}')

fixed = 0
for rid, name, date, day, shift, salad, soup, main_, side, src in rows:
    cells = {'salad': salad or '', 'soup': soup or '', 'main': main_ or '', 'side': side or ''}
    missing = [k for k, v in cells.items() if not v]
    if not missing:
        continue
    h = con.execute("""SELECT salad, soup, main, side FROM client_menus
        WHERE client_name=? AND main != '' AND main NOT LIKE '%заказ не размещен%'
        AND salad != '' AND soup != '' AND side != ''
        AND source_sheet NOT IN ('house_standard','no_order_flag')
        AND menu_date != ?
        ORDER BY ABS(julianday(menu_date)-julianday(?)) LIMIT 1""",
        (name, date, date)).fetchone()
    if not h:
        continue
    fills = []
    for k in missing:
        idx = {'salad': 0, 'soup': 1, 'main': 2, 'side': 3}[k]
        if h[idx]:
            cells[k] = h[idx]
            fills.append(k)
    if not fills:
        continue
    con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?
        WHERE rowid=?""",
        (cells['salad'], cells['soup'], cells['main'], cells['side'], rid))
    fixed += 1

con.commit()
print(f'REX topped up {fixed} rows')
con.close()
