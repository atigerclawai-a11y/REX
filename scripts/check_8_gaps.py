#!/usr/bin/env python3
"""Check history for the 8 gap clients."""
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
for name in ['Kormov Feliks', 'Bok Lyudmila', 'Diadia Valentina', 'Karpina Taisiia',
             'Lysenko Tetiana', 'Shumaeva Anna', 'Matanseva Ofelia', 'Lvova Tamara']:
    h = p.execute("""SELECT menu_date, day_code, salad, soup, main, side, source_sheet
        FROM client_menus WHERE client_name=? AND main != ''
        AND main NOT LIKE '%заказ не размещен%'
        AND source_sheet NOT IN ('house_standard','no_order_flag')
        ORDER BY ABS(julianday(menu_date)-julianday('2026-08-06')) LIMIT 1""", (name,)).fetchone()
    if h:
        print(f'{name}: {h[0]} {h[1]}: {h[2]}|{h[3]}|{h[4]}|{h[5]} [{h[6]}]')
    else:
        print(f'{name}: NO HISTORY')
p.close()
