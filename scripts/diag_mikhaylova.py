#!/usr/bin/env python3
"""Mikhaylova Sofiya: find a complete canonical order from her history to fix Tuesday."""
import sqlite3

PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
name = 'Mikhaylova Sofiya'

p = sqlite3.connect(PROP)
p.row_factory = sqlite3.Row
print('=== all history for Mikhaylova Sofiya (S1) ===')
rows = p.execute("""SELECT menu_date, shift, salad, soup, main, side, source_sheet
    FROM client_menus WHERE client_name=? ORDER BY menu_date DESC LIMIT 15""", (name,)).fetchall()
for r in rows:
    complete = all([r['salad'], r['soup'], r['main'], r['side']])
    print(f"  {r['menu_date']} S{r['shift']} [{r['source_sheet']}] {'OK ' if complete else 'PART':4} {r['salad']} | {r['soup']} | {r['main']} | {r['side']}")
p.close()
