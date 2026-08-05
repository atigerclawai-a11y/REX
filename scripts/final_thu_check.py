#!/usr/bin/env python3
"""Final: Thu house count + kitchen sections."""
import sqlite3
import subprocess

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
h = p.execute("SELECT COUNT(*) FROM client_menus WHERE menu_date='2026-08-06' AND source_sheet='house_standard'").fetchone()[0]
print(f'THU house_standard: {h} (expect 1 — Hurlenia Leanid only)')
for r in p.execute("SELECT client_name FROM client_menus WHERE menu_date='2026-08-06' AND source_sheet='house_standard'"):
    print(f'  {r[0]}')
p.close()

r = subprocess.run(['python3', '/Users/mainsobhelper/Desktop/REX/scripts/verify_kitchen_sections.py'],
                   capture_output=True, text=True, cwd='/Users/mainsobhelper/Desktop/REX',
                   env={'PATH': '/Users/mainsobhelper/.rex-venv/bin:/usr/bin:/bin'})
for line in r.stdout.splitlines():
    if 'TH' in line or 'Thu' in line or 'Thursday' in line:
        print(line)
