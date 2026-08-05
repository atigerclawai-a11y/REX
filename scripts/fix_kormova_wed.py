#!/usr/bin/env python3
"""Fix Kormova Lyubov Wed plate: garbage (Вин|Кур|MP) → her real order.
Her TH pattern: Винегрет|Куриный суп|Поперечка|Пюре (consistent)."""
import sqlite3

for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    c = con.execute("""UPDATE client_menus SET salad='Винегрет', soup='Куриный суп',
        main='Поперечка', side='Пюре', source_sheet='last_order_fallback'
        WHERE client_name='Kormova Lyubov' AND menu_date='2026-08-05'""")
    print(f'{db.split("/")[-1]}: {c.rowcount} row fixed')
    con.commit()
    con.close()
