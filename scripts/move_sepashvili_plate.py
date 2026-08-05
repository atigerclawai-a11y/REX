#!/usr/bin/env python3
"""Move Sepashvili's Friday plate to Tuesday (both DBs) — she attends Tue now.
Her Friday row was last_order_fallback (Свекла|Гороховый суп|Салмон|Стручковая фасоль).
Delete the Friday row (she no longer attends Fri), insert Tuesday row same order."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # get her Friday order
    row = con.execute("""SELECT salad, soup, main, side FROM client_menus
        WHERE client_name='Sepashvili Julieta' AND menu_date='2026-08-07'""").fetchone()
    if row:
        # delete Friday row
        con.execute("""DELETE FROM client_menus
            WHERE client_name='Sepashvili Julieta' AND menu_date='2026-08-07'""")
        # insert Tuesday row
        con.execute("""INSERT INTO client_menus (client_name, menu_date, day_code, shift,
            salad, soup, main, side, source_sheet)
            VALUES ('Sepashvili Julieta', '2026-08-04', 'T', '2', ?, ?, ?, ?, 'last_order_fallback')""",
            row)
        print(f'{db.split("/")[-1]}: moved Fri→Tue: {row[0]}|{row[1]}|{row[2]}|{row[3]}')
    else:
        print(f'{db.split("/")[-1]}: no Friday row found')
    con.commit()
    con.close()
