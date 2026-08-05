#!/usr/bin/env python3
"""Debug: print the last_spans count vs day5 count, and examine a row with Day5."""
import json
import re

html = open('/tmp/clients_full.html').read()
last_spans = len(re.findall(r'<span class="Last">', html))
print(f'Last spans: {last_spans}')
day5 = len(re.findall(r'<td class="Day5"[^>]*id="C\d+D\d+"', html))
print(f'Day5 cells (with id): {day5}')

# The table structure: tr.tblrow > td clientLink + 7 day tds
rows = re.findall(r'<tr class="tblrow">(.*?)</tr>', html, re.S)
print(f'tblrow rows: {len(rows)}')
thu = []
for row in rows:
    nm = re.search(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', row)
    if not nm:
        continue
    d5 = re.search(r'class="Day5"[^>]*>(.*?)</td>', row, re.S)
    has_time = d5 and re.search(r'\d{1,2}:\d{2}(?:AM|PM)', d5.group(1))
    if has_time:
        thu.append((nm.group(1) + ' ' + nm.group(2), d5.group(1).strip()[:60]))
print(f'rows with name + Day5 time: {len(thu)}')
for name, t in thu[:5]:
    print(f'  {name}: {t}')
json.dump([[n, t] for n, t in thu], open('/tmp/thursday_live_full.json', 'w'), ensure_ascii=False)
print(f'saved {len(thu)}')
