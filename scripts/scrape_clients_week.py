#!/usr/bin/env python3
"""Fetch Clients.aspx with saved session, paginate, extract weekly attendance.
Day cells: Day1=Aug2(Sun) Day2=Aug3(Mon) Day3=Aug4(Tue) Day4=Aug5(Wed)
Day5=Aug6(Thu) Day6=Aug7(Fri) Day7=Aug8(Sat). Time in apptime spans."""
import json
import os
import pickle
import re
import requests

BASE = 'https://goj.daycenta.com'
s = requests.Session()
s.cookies = pickle.load(open('/tmp/carecenta_cookies.pkl', 'rb'))

r = s.get(f'{BASE}/Clients.aspx', timeout=30)
txt = r.text
print(f'Clients.aspx: {len(txt)} bytes')
open('/tmp/clients_auth.html', 'w').write(txt)

# parse client rows: each row contains a name cell + Day1..Day7 cells
# Structure from earlier: <td class="Day3" id="C<id>D<MMDDYYYY>"> with apptime spans
rows = re.findall(r'<tr[^>]*id="C\d+"[^>]*>(.*?)</tr>', txt, re.S)
if not rows:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', txt, re.S)
print(f'rows: {len(rows)}')

clients = []
for row in rows:
    # name: usually first td with bold or plain text
    nm = re.search(r'<td[^>]*>(?:<[^>]+>)*\s*([A-Za-zА-Яа-яЁё\'\-\s]+?)\s*(?:<|$)', row)
    name = nm.group(1).strip() if nm else ''
    # day cells with appointments
    days = {}
    for d in range(1, 8):
        cell = re.search(rf'class="Day{d}"[^>]*>(.*?)</td>', row, re.S)
        if cell and ('visit' in cell.group(1) or 'apptime' in cell.group(1) or 'careday' in cell.group(1)):
            days[d] = 'x'
    if name:
        clients.append((name, days))
print(f'parsed clients: {len(clients)}')
for c in clients[:5]:
    print(f'  {c}')
json.dump(clients, open('/tmp/carecenta_clients_week.json', 'w'), ensure_ascii=False)
print('saved /tmp/carecenta_clients_week.json')
