#!/usr/bin/env python3
"""Check why Tue orders are 0 in the JSON after rebuild."""
import json
import sqlite3

orders = json.load(open('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'))
print(f'JSON keys: {sorted(orders.keys())[-6:]}')
print(f'2026-08-04 entries: {len(orders.get("2026-08-04", {}))}')

# DB check
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
n = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date='2026-08-04'").fetchone()[0]
print(f'DB rows for 2026-08-04: {n}')
srcs = p.execute("SELECT source_sheet, COUNT(*) FROM client_menus WHERE menu_date='2026-08-04' GROUP BY 1").fetchall()
print(f'sources: {srcs}')
p.close()
