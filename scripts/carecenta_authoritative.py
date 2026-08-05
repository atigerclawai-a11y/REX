#!/usr/bin/env python3
"""ONE authoritative read of Carecenta from the saved full HTML (all 399 clients,
all 7 days). Extract EVERY client's day cells WITH times. No filtering, no fuzzy.
This is the single source of truth for Thursday AND Friday."""
import json
import re

html = open('/tmp/clients_full.html').read()

clients = []
for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
    last, first = m.group(1).strip(), m.group(2).strip()
    name = f'{last} {first}'
    start = m.start()
    row_start = html.rfind('<tr', 0, start)
    row_end = html.find('</tr>', start)
    if row_start == -1 or row_end == -1:
        continue
    row = html[row_start:row_end]
    days = {}
    for d in range(1, 8):
        cell = re.search(rf'class="Day{d}"[^>]*>(.*?)</td>', row, re.S)
        if cell:
            c = cell.group(1)
            t = re.search(r'(\d{1,2}:\d{2}(?:AM|PM)[^<]*)', c)
            if t:
                days[d] = t.group(1).strip()
    clients.append({'name': name, 'days': days})

print(f'Total clients parsed: {len(clients)}')

# Day counts (which day = what weekday)
# Day1=Aug2(Sun) Day2=Aug3(Mon) Day3=Aug4(Tue) Day4=Aug5(Wed) Day5=Aug6(Thu) Day6=Aug7(Fri) Day7=Aug8(Sat)
day_names = {1: 'SUN Aug2', 2: 'MON Aug3', 3: 'TUE Aug4', 4: 'WED Aug5',
             5: 'THU Aug6', 6: 'FRI Aug7', 7: 'SAT Aug8'}
for d in range(1, 8):
    n = sum(1 for c in clients if d in c['days'])
    print(f'  {day_names[d]}: {n}')

# Time variance per day (does Carecenta distinguish shifts?)
print('\nTime values seen per day:')
for d in range(1, 8):
    times = sorted({c['days'][d] for c in clients if d in c['days']})
    print(f'  {day_names[d]}: {times}')

json.dump(clients, open('/tmp/carecenta_full_week.json', 'w'), ensure_ascii=False)
print('\nsaved /tmp/carecenta_full_week.json')
