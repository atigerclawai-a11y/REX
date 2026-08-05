#!/usr/bin/env python3
"""Extract the 34-doc list from page_guard.log (last recovery manifest write)."""
import os
import re

lg = '/Users/mainsobhelper/Desktop/REX/page_guard.log'
lines = open(lg, errors='ignore').read().splitlines()

# find recovery manifest write lines
docs = []
for l in lines:
    # format: [date] ⚠️ docXXX: Npp → ~M forms expected, 0 extracted | /path
    m = re.search(r'⚠️\s+(\S+?):\s+(\d+)pp.*?(\d+) extracted \| (.+)$', l)
    if m:
        docname = m.group(1)
        pages = int(m.group(2))
        path = m.group(4).strip()
        docs.append((docname, pages, path))

# dedupe keeping last occurrence
seen = {}
for d in docs:
    seen[d[0]] = d
docs = list(seen.values())
print(f'{len(docs)} unique docs from log:')
for i, (docname, pages, path) in enumerate(docs, 1):
    print(f'{i:2d}. {docname} ({pages}pp) → {path}')
