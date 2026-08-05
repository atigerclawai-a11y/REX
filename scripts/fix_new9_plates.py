#!/usr/bin/env python3
"""Fix Thu plates for the 9 newly-added clients (both DBs):
- Kormov Feliks: INSERT Thu plate from his own 07-30 order
- Others: shift S2→S1 to match attendance (they attend S1 per Carecenta times
  being 1:15PM — keep their real plates, just fix shift)"""
import sqlite3

FIX_SHIFT = ['Bardenshteyn Larisa', 'Bekerman Alla', 'Berezkin Mikhail',
             'Gendelman Anatoliy', 'Gendelman Liliya', 'Kormova Lyubov',
             'Maglakelidze Mzia']

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # Kormov Feliks insert
    n = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name='Kormov Feliks' AND menu_date='2026-08-06'").fetchone()[0]
    if n:
        c = con.execute("""UPDATE client_menus SET salad='Винегрет', soup='Гороховый суп',
            main='Поперечка', side='Гречка', source_sheet='last_order_fallback', shift=1
            WHERE client_name='Kormov Feliks' AND menu_date='2026-08-06'""")
        print(f'{db.split("/")[-1]} Kormov Feliks: updated {c.rowcount}')
    else:
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Kormov Feliks', '2026-08-06', 'TH', '1',
            'Винегрет', 'Гороховый суп', 'Поперечка', 'Гречка', 'last_order_fallback')""")
        print(f'{db.split("/")[-1]} Kormov Feliks: inserted')
    # shift fixes
    for name in FIX_SHIFT:
        # check if an S1 row exists (avoid collision)
        s1 = con.execute("SELECT COUNT(*) FROM client_menus WHERE client_name=? AND menu_date='2026-08-06' AND shift=1", (name,)).fetchone()[0]
        if s1:
            # delete the S2 duplicate
            c = con.execute("DELETE FROM client_menus WHERE client_name=? AND menu_date='2026-08-06' AND shift=2", (name,))
            print(f'{db.split("/")[-1]} {name}: deleted S2 dup (S1 exists)')
        else:
            c = con.execute("UPDATE client_menus SET shift=1 WHERE client_name=? AND menu_date='2026-08-06' AND shift=2", (name,))
            print(f'{db.split("/")[-1]} {name}: {c.rowcount} shift→1')
    con.commit()
    con.close()
