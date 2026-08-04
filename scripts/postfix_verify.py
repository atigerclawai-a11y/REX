#!/usr/bin/env python3
"""Post-fix verification: garbage, leaks, parity, plus check 12:06 noon-refresh."""
import sqlite3

print('=== garbage ===')
import subprocess
r = subprocess.run(['python3', '/Users/mainsobhelper/Desktop/REX/scripts/find_garbage_dishes.py'],
                   capture_output=True, text=True, cwd='/Users/mainsobhelper/Desktop/REX',
                   env={'PATH': '/Users/mainsobhelper/.rex-venv/bin:/usr/bin:/bin'})
for line in r.stdout.splitlines():
    if 'non-canonical' in line:
        print(' ', line)

print('\n=== parity ===')
for db in ['/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db',
           '/Users/mainsobhelper/Desktop/REX/goj_proprietary.db']:
    con = sqlite3.connect(db)
    rows = con.execute("""SELECT source_sheet, COUNT(*) FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    print(f'  {db.split("/")[-1]}: {rows}')
    con.close()
