#!/usr/bin/env python3
"""Check focr recovery progress: which docs done, extraction files produced."""
import json
import os
from datetime import datetime
from pathlib import Path

# recovery log tail
lg = '/Users/mainsobhelper/Desktop/REX/page_guard.log'
if os.path.exists(lg):
    lines = open(lg, errors='ignore').read().splitlines()
    print(f'page_guard.log: {len(lines)} lines, last 10:')
    for l in lines[-10:]:
        print(f'  {l}')

# extraction files per manifest doc
mf = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json'
docs = json.load(open(mf)) if os.path.exists(mf) else []
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
print('\nmanifest docs extraction status:')
for d in docs:
    docname = d[0] if isinstance(d, (list, tuple)) else (d if isinstance(d, str) else d.get('doc', ''))
    ddir = BASE / docname
    if ddir.is_dir():
        exts = [f.name for f in ddir.glob('extraction*.json')]
        status = f'{len(exts)} extraction files: {exts[:3]}'
    else:
        status = 'NO DIR'
    print(f'  {docname[:30]}: {status}')
