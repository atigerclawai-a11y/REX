#!/usr/bin/env python3
"""Fix Sorits Lev: resolve review item (Вингерет→Винегрет) + verify his DB plate."""
import sqlite3

DB = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
con = sqlite3.connect(DB)

# 1. resolve review queue
c = con.execute("""UPDATE menu_review_queue SET status='resolved',
    resolution='Вингерет = Винегрет (confirmed by Kato 8/5)'
    WHERE client_name='Sorits Lev'""")
print(f'review queue: {c.rowcount} resolved')

# 2. check his plates this week
print('\nSorits Lev plates:')
for r in con.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Sorits Lev'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

# 3. fix any Вингерет in his rows
for col in ['salad', 'soup', 'main', 'side']:
    c = con.execute(f"""UPDATE client_menus SET {col}=REPLACE({col},'Вингерет','Винегрет')
        WHERE client_name='Sorits Lev' AND {col} LIKE '%Вингерет%'""")
    if c.rowcount:
        print(f'{col}: {c.rowcount} Вингерет→Винегрет')
con.commit()
con.close()
