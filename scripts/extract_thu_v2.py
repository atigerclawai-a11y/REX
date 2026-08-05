#!/usr/bin/env python3
"""RELIABLE Thursday parse: use Day5 cell IDs (C<clientid>D08062026) + clientLink
cells. Each client row has clientLink (name) + 7 day cells in one <tr>."""
import json
import re

html = open('/tmp/clients_full.html').read()

# Strategy: split by clientLink cells which contain the name
# Each client row: <tr ...><td class="clientLink"...>NAME...</td> ... day cells ... </tr>
# Find all name anchors and their positions, then the day cells between
name_re = re.compile(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>')
day5_re = re.compile(r'<td class="Day5"[^>]*>(.*?)</td>', re.S)

clients = []
for m in name_re.finditer(html):
    last, first = m.group(1).strip(), m.group(2).strip()
    name = f'{last} {first}'
    start = m.start()
    # find the enclosing row: look backwards for <tr, forward for </tr> that closes this row
    row_start = html.rfind('<tr', 0, start)
    row_end = html.find('</tr>', start)
    if row_start == -1 or row_end == -1:
        continue
    row = html[row_start:row_end]
    # Day5 cell in this row
    d5 = day5_re.search(row)
    present = False
    if d5:
        cell = d5.group(1)
        present = ('spanappt' in cell) or bool(re.search(r'\d{1,2}:\d{2}', cell))
    if present:
        clients.append(name)

print(f'Thursday attendees: {len(clients)}')
for n in clients[:15]:
    print(f'  {n}')
json.dump(clients, open('/tmp/thursday_live_full.json', 'w'), ensure_ascii=False)
print(f'saved {len(clients)} names')
