#!/usr/bin/env python3
"""Extract the FULL Thursday roster from clients_full.html (2.88MB, all 399 rows).
Day5 cells with time = Thursday attendees. Map to names."""
import json
import re

html = open('/tmp/clients_full.html').read()

# find all client blocks: Last,First + their day cells
clients = []
for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
    last, first = m.group(1).strip(), m.group(2).strip()
    name = f'{last} {first}'
    start = m.start()
    end = html.find('<span class="Last">', start + 10)
    if end == -1:
        end = len(html)
    seg = html[start:end]
    days = {}
    for d in range(1, 8):
        cell = re.search(rf'class="Day{d}"[^>]*>(.*?)(?:</td>|$)', seg, re.S)
        if cell:
            c = cell.group(1)
            t = re.search(r'(\d{1,2}:\d{2}(?:AM|PM)[^<]*)', c)
            if t:
                days[d] = t.group(1).strip()
    clients.append((name, days))

print(f'parsed: {len(clients)} clients')
thu = [(n, d[5]) for n, d in clients if d.get(5)]
print(f'Thursday (Day5): {len(thu)} clients')
for name, t in thu:
    print(f'  {name}: {t}')

json.dump([[n, t] for n, t in thu], open('/tmp/thursday_live_full.json', 'w'), ensure_ascii=False)
print(f'\nsaved {len(thu)} to /tmp/thursday_live_full.json')
