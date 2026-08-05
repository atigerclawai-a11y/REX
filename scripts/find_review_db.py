#!/usr/bin/env python3
"""Find which DB has menu_review_queue + show Sorits row."""
import sqlite3
import glob

cands = [
    '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
    '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db',
    '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db',
    '/Users/mainsobhelper/Desktop/REX/continuity/goj_corpus.db',
]
for db in cands:
    try:
        con = sqlite3.connect(db)
        t = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='menu_review_queue'").fetchone()
        if t:
            n = con.execute("SELECT COUNT(*) FROM menu_review_queue").fetchone()[0]
            print(f'{db}: HAS menu_review_queue ({n} rows)')
            for r in con.execute("SELECT * FROM menu_review_queue WHERE client_name LIKE '%Sorits%'"):
                print(f'  SORITS: {r}')
        else:
            print(f'{db}: no table')
        con.close()
    except Exception as e:
        print(f'{db}: {e}')
