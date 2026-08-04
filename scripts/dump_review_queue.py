#!/usr/bin/env python3
"""Full menu_review_queue + menu_quarantine dump — every unreadable/unmatched form."""
import sqlite3

PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
con = sqlite3.connect(PROP)
con.row_factory = sqlite3.Row

print('=== menu_review_queue (ALL) ===')
rows = con.execute("SELECT * FROM menu_review_queue ORDER BY id").fetchall()
print(f'total: {len(rows)}')
for r in rows:
    print(dict(r))

print('\n=== menu_quarantine — reason contains name/unread (ALL) ===')
rows = con.execute("""SELECT id, client_name, menu_date, shift, salad, soup, main, side, source_sheet, reason, ts
    FROM menu_quarantine ORDER BY id""").fetchall()
print(f'total: {len(rows)}')
from collections import Counter
reasons = Counter(r['reason'] for r in rows)
print('reasons:', dict(reasons))
con.close()
