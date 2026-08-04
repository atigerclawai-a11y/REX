#!/usr/bin/env python3
"""Fix category leaks for 4 clients (both DBs):
- Shuper Klavdia 08-04 T: salad ← Салат весенний (her real Tue salad)
- Khalfin Inna 08-06 TH: main ← Котлеты куриные (her real TH main)
- Matanseva Ofelia: delete garbage fallback rows (re-fill from real history)
- Minogina Ninel: delete garbage fallback rows (re-fill from real history)"""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # 1. Shuper Klavdia — fix salad cell (keep her vision soup/main)
    c = con.execute("""UPDATE client_menus SET salad='Салат весенний'
        WHERE client_name='Shuper Klavdia' AND menu_date='2026-08-04' AND salad='Борщ зеленый'""")
    print(f'{db.split("/")[-1]} Shuper: {c.rowcount} row fixed')
    # 2. Khalfin Inna — fix main cell
    c = con.execute("""UPDATE client_menus SET main='Котлеты куриные'
        WHERE client_name='Khalfin Inna' AND menu_date='2026-08-06' AND main='Оливье'""")
    print(f'{db.split("/")[-1]} Khalfin: {c.rowcount} row fixed')
    # 3+4. Delete garbage fallback rows for Matanseva/Minogina (their 08-01/02
    #     history rows are themselves leaked house_standard copies — refill will
    #     now pick their REAL ocr_scan history: 07-28/30/31)
    for name in ['Matanseva Ofelia', 'Minogina Ninel']:
        c = con.execute("""DELETE FROM client_menus WHERE client_name=?
            AND menu_date BETWEEN '2026-08-03' AND '2026-08-07'
            AND source_sheet='last_order_fallback'""", (name,))
        print(f'{db.split("/")[-1]} {name}: deleted {c.rowcount} garbage fallback rows')
    con.commit()
    con.close()
