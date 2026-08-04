#!/usr/bin/env python3
"""Find unreadable-name forms: extraction JSONs + recovery manifest + garbled batches."""
import json
import os
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')

# 1. Recovery manifest — what docs are being recovered (may contain unreadable names)
m = REX / '.page_guard_recover.json'
if m.exists():
    d = json.load(open(m))
    docs = d.get('docs', d) if isinstance(d, dict) else d
    print(f'=== recovery manifest: {len(docs)} docs ===')
    for x in docs[:40]:
        print(f'  {x if isinstance(x, str) else x}')

# 2. extraction JSONs in blank_parse — find entries with garbled/empty names
print('\n=== extraction JSONs with unreadable names ===')
found = []
for base in [REX / 'blank_parse', Path('/Users/mainsobhelper/Documents/goj files/blank_parse')]:
    if not base.exists():
        continue
    for jf in sorted(base.glob('*.json')):
        try:
            d = json.load(open(jf))
        except Exception:
            continue
        entries = d if isinstance(d, list) else d.get('forms', d.get('extractions', []))
        if isinstance(entries, list):
            for e in entries:
                nm = str(e.get('name', '') if isinstance(e, dict) else e).strip()
                if not nm or len(nm) < 3 or any(ch.isdigit() for ch in nm[:6]):
                    found.append((jf.name, nm, str(e)[:80]))

print(f'unreadable/empty names in extraction JSONs: {len(found)}')
for f in found[:30]:
    print(f'  {f[0]}: name={f[1]!r}  {f[2]}')
