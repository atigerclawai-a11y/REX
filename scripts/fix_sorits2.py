#!/usr/bin/env python3
"""Fix Sorits Lev review item with correct schema columns."""
import sqlite3
from datetime import datetime

DB = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
con = sqlite3.connect(DB)

c = con.execute("""UPDATE menu_review_queue SET status='resolved',
    resolved_pick='Винегрет', resolved_by='Kato (8/5): Вингерет = Винегрет',
    resolved_at=?
    WHERE client_name='Sorits Lev'""", (datetime.now().isoformat(),))
print(f'review queue: {c.rowcount} resolved')

# check plates + fix misspellings in his rows
print('\nSorits Lev plates:')
for r in con.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Sorits Lev'
    AND menu_date BETWEEN '2026-08-03' AND '2026-08-07' ORDER BY menu_date"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')

for col in ['salad', 'soup', 'main', 'side']:
    c = con.execute(f"""UPDATE client_menus SET {col}=REPLACE({col},'Вингерет','Винегрет')
        WHERE client_name='Sorits Lev' AND {col} LIKE '%Вингерет%'""")
    if c.rowcount:
        print(f'{col}: {c.rowcount} Вингерет→Винегрет')
con.commit()
con.close()
