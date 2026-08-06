#!/usr/bin/env python3
"""Check attendance.db schema + how signin_attendance_bridge writes."""
import sqlite3
import os

# attendance.db schema
for db in ['/Users/mainsobhelper/Desktop/REX/attendance.db']:
    if os.path.exists(db):
        con = sqlite3.connect(db)
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f'{db}: tables {tables}')
        for (t,) in tables:
            cols = con.execute(f"PRAGMA table_info({t})").fetchall()
            print(f'  {t}: {[c[1] for c in cols]}')
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f'    rows: {n}')
        con.close()
    else:
        print(f'{db}: MISSING')
