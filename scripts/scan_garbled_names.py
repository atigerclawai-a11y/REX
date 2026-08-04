#!/usr/bin/env python3
"""Scan all blank_parse extraction.json files for unreadable/unmatched names."""
import json
import os
import re
from pathlib import Path

BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
import sqlite3
con = sqlite3.connect(AUTH)
roster = {r[0].strip().lower() for r in con.execute("SELECT name FROM clients")}
con.close()


def norm(n):
    return re.sub(r'[^a-z\'\- ]', '', n.lower()).strip()


roster_n = {norm(x) for x in roster}

print('Scanning extraction.json files for garbled/unmatched names...\n')
for d in sorted(BASE.iterdir()):
    if not d.is_dir():
        continue
    ej = d / 'extraction.json'
    if not ej.exists():
        continue
    try:
        data = json.load(open(ej))
    except Exception:
        print(f'{d.name}: UNREADABLE extraction.json')
        continue
    entries = data if isinstance(data, list) else data.get('forms', data.get('extractions', []))
    if isinstance(data, dict) and 'days' in data:
        entries = []
        for day, forms in data['days'].items():
            if isinstance(forms, list):
                for f in forms:
                    f['_day'] = day
                    entries.append(f)
    if not isinstance(entries, list):
        print(f'{d.name}: weird structure {type(data).__name__}')
        continue
    for e in entries:
        if not isinstance(e, dict):
            continue
        nm = str(e.get('name', '')).strip()
        if not nm:
            print(f'{d.name}: EMPTY name (day={e.get("_day", e.get("day", "?"))})')
            continue
        n = norm(nm)
        # garbled if <4 chars, heavy punctuation, or no fuzzy roster match
        ok = any(n == rn or (len(n) > 4 and (n in rn or rn in n)) for rn in roster_n)
        if len(n) < 4 or (not ok and re.search(r'[·•]', nm)):
            print(f'{d.name}: GARBLED "{nm}" (day={e.get("_day", e.get("day", "?"))})')
