#!/usr/bin/env python3
"""Check focr recovery name reads for the 22 attending no-form clients.
The recovery reads names from each page pair — if a name appears, the form EXISTS."""
import json
import sqlite3
from pathlib import Path

# attending no-form surnames
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
noform = set(r[0] for r in p.execute("""SELECT DISTINCT client_name FROM client_menus
    WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07'
    AND client_name NOT IN (
        SELECT DISTINCT client_name FROM client_menus
        WHERE menu_date BETWEEN '2026-08-03' AND '2026-08-07' AND source_sheet='ocr_scan')"""))
p.close()

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
attending = set()
for n in noform:
    r = a.execute("SELECT day_T_actual, day_W_actual FROM clients WHERE name=?", (n,)).fetchone()
    if r and (r[0] in (1, 2) or r[1] in (1, 2)):
        attending.add(n)
a.close()

surnames = {n.split()[0].lower() for n in attending if n.split()}
print(f'attending no-form: {len(attending)}, surnames: {len(surnames)}')

# search focr recovery outputs (JSON files in blank_parse + /tmp/focr_scan)
found = {}
candidates = list(Path('/Users/mainsobhelper/Desktop/REX/blank_parse').glob('*/focr*.json')) + \
            list(Path('/tmp/focr_scan').glob('*.json')) if Path('/tmp/focr_scan').exists() else []
print(f'focr json files: {len(candidates)}')
for f in candidates:
    try:
        data = json.load(open(f))
        # could be dict of name->..., list, or {name:...}
        names = []
        if isinstance(data, dict):
            names = [k for k in data.keys() if isinstance(k, str)]
            for v in data.values():
                if isinstance(v, dict) and 'name' in v:
                    names.append(str(v['name']))
        elif isinstance(data, list):
            for v in data:
                if isinstance(v, dict) and 'name' in v:
                    names.append(str(v['name']))
        for nm in names:
            if nm and nm.split() and nm.split()[0].lower() in surnames:
                found.setdefault(nm, []).append(f.name[:20])
    except Exception:
        pass

print(f'matches in focr files: {len(found)}')
for nm, fs in sorted(found.items()):
    print(f'  {nm}: {fs[:3]}')
