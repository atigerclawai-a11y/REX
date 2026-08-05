#!/usr/bin/env python3
"""Extract the LAST 34-doc manifest write block from page_guard.log.
The manifest write line is preceded by the ⚠️ list of that run's flagged docs."""
import os
import re

lg = '/Users/mainsobhelper/Desktop/REX/page_guard.log'
lines = open(lg, errors='ignore').read().splitlines()

# find the LAST "recovery manifest written (N docs)" line
last_write_idx = None
for i, l in enumerate(lines):
    if 'recovery manifest written' in l:
        last_write_idx = i

if last_write_idx is None:
    print('no manifest write found')
    raise SystemExit

# walk backwards to the "N docs with un-OCR'd pages:" line
start = last_write_idx
while start > 0 and 'docs with un-OCR' not in lines[start]:
    start -= 1

docs = []
for l in lines[start+1:last_write_idx]:
    m = re.search(r'⚠️\s+(\S+?):\s+(\d+)pp.*?\| (.+)$', l)
    if m:
        docs.append((m.group(1), int(m.group(2)), m.group(3).strip()))

print(f'{len(docs)} docs in last manifest write:')
for i, (docname, pages, path) in enumerate(docs, 1):
    print(f'{i:2d}. {docname} ({pages}pp) → {path}')

json.dump(docs, open('/tmp/manifest_34.json', 'w'))
