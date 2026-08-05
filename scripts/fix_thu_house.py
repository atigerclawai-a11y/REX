#!/usr/bin/env python3
"""Replace Thu house_standard plates with each client's OWN most recent order.
Order preference: most recent complete THURSDAY order → most recent complete any-day.
Only clients with NO history keep house_standard (genuine gap: Hurlenia Leanid).
Source stays honest: day_shifted if from another day, last_order_fallback if TH."""
import sqlite3

HOUSE = ['Aronchik Bronya', 'Buziashvili Galina', 'Chupikova Elvira', 'Dodik Sima',
         'Drabkin Marat', 'Elbert Milla', 'Epshtein Isaak', 'Feldman Klavdya',
         'Furman Vladimir', 'Hurlenia Leanid', 'Krivchenok Mina', 'Mazo Nina',
         'Safonov Anatoliy', 'Sekh Stefaniia', 'Shadkhan Bella', 'Shteyman Faina',
         'Zubkova Valya']

SRC = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
con = sqlite3.connect(SRC)
fixes = {}  # name -> (salad, soup, main, side, source)
for name in HOUSE:
    # 1. most recent complete TH order
    r = con.execute("""SELECT salad, soup, main, side FROM client_menus
        WHERE client_name=? AND day_code='TH' AND main != ''
        AND main NOT LIKE '%заказ не размещен%'
        AND source_sheet NOT IN ('house_standard','no_order_flag')
        AND salad != '' AND soup != '' AND side != ''
        ORDER BY menu_date DESC LIMIT 1""", (name,)).fetchone()
    src = 'last_order_fallback'
    if not r:
        # 2. any complete order
        r = con.execute("""SELECT salad, soup, main, side FROM client_menus
            WHERE client_name=? AND main != '' AND main NOT LIKE '%заказ не размещен%'
            AND source_sheet NOT IN ('house_standard','no_order_flag')
            AND salad != '' AND soup != '' AND side != ''
            ORDER BY menu_date DESC LIMIT 1""", (name,)).fetchone()
        src = 'day_shifted'
    if r:
        fixes[name] = (r[0], r[1], r[2], r[3], src)
con.close()

print(f'fixable: {len(fixes)}/17')
for name, (sal, sup, main_, side, src) in sorted(fixes.items()):
    print(f'  {name}: {sal}|{sup}|{main_}|{side} [{src}]')

# apply to both DBs
for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, (sal, sup, main_, side, src) in fixes.items():
        c = con.execute("""UPDATE client_menus SET salad=?, soup=?, main=?, side=?, source_sheet=?
            WHERE client_name=? AND menu_date='2026-08-06' AND source_sheet='house_standard'""",
            (sal, sup, main_, side, src, name))
        if c.rowcount:
            pass
    con.commit()
    con.close()
    print(f'{db.split("/")[-1]}: applied {len(fixes)} fixes')
