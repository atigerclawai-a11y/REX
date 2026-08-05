#!/usr/bin/env python3
"""Assign Kormova Lyubov canonical_id 1305 (next free) in both auth + proprietary DBs."""
import sqlite3

NEW_ID = '1305'

for db in ['/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    # does canonical_ids table exist in this DB?
    try:
        has = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='canonical_ids'").fetchone()
        if has:
            n = con.execute("SELECT COUNT(*) FROM canonical_ids WHERE canonical_id=?", (NEW_ID,)).fetchone()[0]
            if n == 0:
                con.execute("""INSERT INTO canonical_ids (canonical_id, name, auth_id, prop_id)
                    VALUES (?, 'Kormova Lyubov', 589, NULL)""", (NEW_ID,))
                print(f'{db.split("/")[-1]}: inserted canonical_id {NEW_ID} for Kormova Lyubov')
            else:
                print(f'{db.split("/")[-1]}: {NEW_ID} already exists')
        else:
            print(f'{db.split("/")[-1]}: no canonical_ids table')
    except Exception as e:
        print(f'{db.split("/")[-1]}: {e}')
    con.commit()
    con.close()
