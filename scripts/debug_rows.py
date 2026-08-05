#!/usr/bin/env python3
"""Debug: 149 Day5 cells with time vs 61 parsed clients. Check row structure."""
import re

html = open('/tmp/clients_full.html').read()

# count Last spans vs Day5 cells
last_spans = re.findall(r'<span class="Last">', html)
print(f'Last spans: {len(last_spans)}')
day5_cells = re.findall(r'<td class="Day5"', html)
print(f'Day5 cells: {len(day5_cells)}')

# show a client block that HAS Day5 time but might be cut: sample around a Day5 cell
# find all clientLink rows
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
print(f'table rows: {len(rows)}')
day5_in_rows = sum(1 for r in rows if 'class="Day5"' in r and re.search(r'\d{1,2}:\d{2}', r))
print(f'rows with Day5+time: {day5_in_rows}')

# check one row structure
for r in rows:
    if 'class="Day5"' in r and re.search(r'\d{1,2}:\d{2}', r):
        # find name in this row
        nm = re.search(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', r)
        print(f'sample row name: {nm.group(1)+" "+nm.group(2) if nm else "NO NAME SPAN"}')
        print(f'row len: {len(r)}')
        print(f'  {r[:250]}')
        break
