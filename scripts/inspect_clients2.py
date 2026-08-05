#!/usr/bin/env python3
"""Inspect clients_live_p1.html structure."""
import re

txt = open('/tmp/clients_live_p1.html').read()
print(f'len: {len(txt)}')
# find Day cells
days = re.findall(r'class="Day(\d)"', txt)
print(f'Day cells: {len(days)}: {sorted(set(days))}')
# find name-ish text
names = re.findall(r'<td[^>]*>\s*<b>([^<]+)</b>', txt)
print(f'bold names: {len(names)}')
for n in names[:10]:
    print(f'  {n.strip()}')
# find tr count
trs = txt.count('<tr')
print(f'<tr count: {trs}')
# is there a ShowRecords select?
sr = re.search(r'ShowRecords[^>]*>', txt)
print(f'ShowRecords: {sr.group(0)[:80] if sr else "not found"}')
# page size info
ps = re.findall(r'option[^>]*value="(\d+)"[^>]*>(\d+)', txt)
print(f'options: {ps[:6]}')
