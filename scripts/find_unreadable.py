#!/usr/bin/env python3
"""Find every unreadable/unmatched form: review queue + quarantine + recovery manifest."""
import json
import os
import sqlite3
from pathlib import Path

PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
REX = '/Users/mainsobhelper/Desktop/REX'

# 1. Table list
con = sqlite3.connect(PROP)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print('tables:', tables)
con.close()

# 2. Review queue / quarantine files
print('\n=== candidate files ===')
for pat in ['*review*', '*quarantine*', '*unmatched*', '*unread*', '*fail*', '*queue*']:
    hits = list(Path(REX).glob(pat)) + list(Path(REX, 'scripts').glob(pat))
    for h in hits[:10]:
        print(f'  {h} ({h.stat().st_size if h.is_file() else "dir"})')

# 3. Recovery manifest
for m in ['/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json']:
    if os.path.exists(m):
        d = json.load(open(m))
        print(f'\nrecovery manifest: {len(d) if isinstance(d, list) else list(d.keys())[:5]}')
        if isinstance(d, list):
            for x in d[:5]:
                print(f'   {x}')
