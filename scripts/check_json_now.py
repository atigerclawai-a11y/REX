#!/usr/bin/env python3
"""Check: did generate_tomorrow's preflight overwrite the orders JSON?
Compare JSON 08-04 entries before/after a run (mtime + source)."""
import json
import os
from datetime import datetime

p = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
st = os.stat(p)
print(f'JSON mtime: {datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M:%S")}')
data = json.load(open(p))
print(f'08-04 entries: {len(data.get("2026-08-04", {}))}')
# show a sample entry
for name, shifts in list(data.get('2026-08-04', {}).items())[:2]:
    print(f'  {name}: {shifts}')
