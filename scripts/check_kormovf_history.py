#!/usr/bin/env python3
"""Fix the 9 newly-added Thu clients:
- Kormov Feliks: no plate → add from his history (check first)
- 8 others: plate exists but shift mismatch (attendance S1 vs plate S2) → move to S1"""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')

# Kormov Feliks history
print('Kormov Feliks history:')
for r in p.execute("""SELECT menu_date, day_code, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name='Kormov Feliks'
    AND main != '' AND main NOT LIKE '%заказ не размещен%'
    ORDER BY menu_date DESC LIMIT 5"""):
    print(f'  {r[0]} {r[1]} S{r[2]}: {r[3]}|{r[4]}|{r[5]}|{r[6]} [{r[7]}]')
p.close()
