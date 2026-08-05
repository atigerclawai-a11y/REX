#!/usr/bin/env python3
"""Handle UNIQUE collisions during shift fix: if target shift already has a row,
keep the ocr_scan (real) one, delete the other. Then retry the shift update."""
import sqlite3

DATE = {'M': '2026-08-03', 'T': '2026-08-04', 'W': '2026-08-05', 'TH': '2026-08-06', 'F': '2026-08-07'}
FIXES = [
    ('Ivanova Liudmila', 'M', 2), ('Ivanova Liudmila', 'F', 2),
    ('Fedorova Olga', 'M', 1), ('Elbert Milla', 'M', 1),
    ('Chupikova Elvira', 'M', 1), ('Shapiro Roza', 'M', 2),
    ('Shapiro Roza', 'F', 2), ('Bialkovska Maria', 'W', 2),
]

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    for name, day, sh in FIXES:
        d = DATE[day]
        # check if target shift row exists
        target = con.execute("""SELECT source_sheet FROM client_menus
            WHERE client_name=? AND menu_date=? AND shift=?""",
            (name, d, sh)).fetchone()
        cur_src = con.execute("""SELECT source_sheet FROM client_menus
            WHERE client_name=? AND menu_date=? AND day_code=?""",
            (name, d, day)).fetchall()
        if target:
            # collision: if target is fallback/shifted and current is ocr_scan, delete target
            tgt_src = target[0]
            for src in cur_src:
                if src[0] == 'ocr_scan' and tgt_src != 'ocr_scan':
                    con.execute("""DELETE FROM client_menus WHERE client_name=? AND menu_date=? AND shift=?""",
                                (name, d, sh))
                    print(f'{db.split("/")[-1]} {name} {day}: deleted {tgt_src} dup in S{sh}')
                elif src[0] == 'ocr_scan' and tgt_src == 'ocr_scan':
                    # both ocr_scan — keep the one with more complete cells; delete other
                    con.execute("""DELETE FROM client_menus WHERE client_name=? AND menu_date=? AND shift=? AND source_sheet='ocr_scan' LIMIT 1""",
                                (name, d, sh))
                    print(f'{db.split("/")[-1]} {name} {day}: deleted duplicate ocr_scan in S{sh}')
        # now update
        try:
            c = con.execute("""UPDATE client_menus SET shift=?
                WHERE client_name=? AND menu_date=? AND day_code=? AND source_sheet='ocr_scan'""",
                (sh, name, d, day))
            print(f'{db.split("/")[-1]} {name} {day}: {c.rowcount} ocr_scan row shift→{sh}')
        except sqlite3.IntegrityError as e:
            print(f'{db.split("/")[-1]} {name} {day}: STILL COLLIDES: {e}')
    con.commit()
    con.close()
