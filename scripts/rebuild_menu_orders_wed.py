#!/usr/bin/env python3
"""Rebuild GOJ_Menu_Orders.json Aug 5 entry from goj_proprietary.db (proven pattern).
Format: {date_iso: {name: {shift_str: {salad, soup, main, side}}}}"""
import json
import sqlite3
from pathlib import Path

DATE = '2026-08-05'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
ORDERS = Path('/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json')

con = sqlite3.connect(PROP)
rows = con.execute("""SELECT client_name, shift, salad, soup, main, side FROM client_menus
    WHERE menu_date=? AND main NOT LIKE '%заказ не размещен%' AND main != ''""",
    (DATE,)).fetchall()
con.close()

entry = {}
for name, shift, salad, soup, main_, side in rows:
    entry.setdefault(name, {})[str(shift)] = {
        'salad': salad or '', 'soup': soup or '', 'main': main_ or '', 'side': side or ''
    }

# merge into existing file preserving other dates
data = {}
if ORDERS.exists():
    data = json.loads(ORDERS.read_text())
data[DATE] = entry
ORDERS.write_text(json.dumps(data, ensure_ascii=False, indent=1))

n_orders = sum(len(v) for v in entry.values())
print(f'GOJ_Menu_Orders.json[{DATE}]: {len(entry)} clients, {n_orders} orders')
print(f'shift1 clients: {sum(1 for v in entry.values() if "1" in v)}  shift2: {sum(1 for v in entry.values() if "2" in v)}')
