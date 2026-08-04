#!/usr/bin/env python3
"""Check recovery state: manifest status, what docs are pending/done."""
import json
import subprocess
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
mf = REX / '.page_guard_recover.json'
if mf.exists():
    data = json.load(open(mf))
    docs = data if isinstance(data, list) else data.get('docs', [])
    print(f'recovery manifest: {len(docs)} docs')
else:
    print('no manifest')

# is focr recovery still running?
r = subprocess.run(['pgrep', '-fl', 'focr_recover'], capture_output=True, text=True)
print('focr recovery process:', r.stdout.strip() or 'NOT RUNNING')

# recent page_guard log entries
lg = REX / 'page_guard.log'
if lg.exists():
    lines = lg.read_text(errors='ignore').splitlines()
    print(f'\npage_guard.log last 8 lines:')
    for l in lines[-8:]:
        print(f'  {l}')
