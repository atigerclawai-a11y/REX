#!/usr/bin/env python3
"""Check the 5 gap clients: their Thu rows' shift vs attendance shift."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
a = sqlite3.connect(AUTH)
p = sqlite3.connect(PROP)

for name in ['Breytman Polina', 'Coniglio Vera', 'Dmitriyeva Tamara', 'Epshteyn Yelizaveta', 'Firdman Mark']:
    att = a.execute("SELECT day_TH_actual FROM clients WHERE name=?", (name,)).fetchone()
    rows = p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND menu_date='2026-08-06'""", (name,)).fetchall()
    print(f'{name}: attend TH={att[0] if att else "?"}, rows: {rows if rows else "NONE"}'  )
a.close()
p.close()
