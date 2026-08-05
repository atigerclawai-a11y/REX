#!/usr/bin/env python3
"""Fix 8 shift mismatches (both DBs): update client_menus.shift to auth actual.
Also fix Fedorova Olga TH: her form has no TH marks → use her own most recent
complete order (07-31 F: Салат весенний|Борщ красный|Блины с мясом|Пюре) as
last_order_fallback instead of house_standard."""
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
        c = con.execute("""UPDATE client_menus SET shift=?
            WHERE client_name=? AND menu_date=? AND day_code=?""",
            (sh, name, d, day))
        print(f'{db.split("/")[-1]} {name} {day}: {c.rowcount} row shift→{sh}')
    # Fedorova TH: replace house_standard with her own recent order
    c = con.execute("""UPDATE client_menus SET salad='Салат весенний', soup='Борщ красный',
        main='Блины с мясом', side='Пюре', source_sheet='last_order_fallback', shift=1
        WHERE client_name='Fedorova Olga' AND menu_date='2026-08-06'""")
    print(f'{db.split("/")[-1]} Fedorova Olga TH: {c.rowcount} row (own order)')
    con.commit()
    con.close()
