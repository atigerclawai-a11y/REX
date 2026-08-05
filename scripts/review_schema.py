#!/usr/bin/env python3
"""Check menu_review_queue schema."""
import sqlite3

DB = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
con = sqlite3.connect(DB)
for r in con.execute("PRAGMA table_info(menu_review_queue)"):
    print(r)
con.close()
