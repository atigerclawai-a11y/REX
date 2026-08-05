#!/usr/bin/env python3
"""Fix Sorits Lev: 'Вингерет' → 'Винегрет' (canonical spelling).
Fix in review queue + any client_menus rows with the misspelling."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # 1. review queue
    try:
        c = con.execute("""UPDATE menu_review_queue SET issue=REPLACE(issue, 'Вингерет', 'Винегрет'),
            status='resolved', resolution='Вингерет is Винегрет (Kato 8/5)'
            WHERE client_name LIKE '%Sorits%' AND status='pending'""")
        print(f'{db.split("/")[-1]} review queue: {c.rowcount} Sorits items updated')
    except Exception as e:
        print(f'{db.split("/")[-1]} review queue: {e}')

    # 2. client_menus misspellings anywhere
    for col in ['salad', 'soup', 'main', 'side']:
        c = con.execute(f"UPDATE client_menus SET {col}=REPLACE({col}, 'Вингерет', 'Винегрет') WHERE {col} LIKE '%Вингерет%'")
        if c.rowcount:
            print(f'{db.split("/")[-1]} client_menus.{col}: {c.rowcount} fixed')
    con.commit()
    con.close()
