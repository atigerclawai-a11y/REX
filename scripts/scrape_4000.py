#!/usr/bin/env python3
"""Use ShowRecords=4000 to get ALL clients in one POST."""
import json
import os
import pickle
import re
import requests

BASE = 'https://goj.daycenta.com'
s = requests.Session()
s.cookies = pickle.load(open('/tmp/carecenta_cookies.pkl', 'rb'))

def parse_clients(html):
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
            if cell and ('spanappt' in cell.group(1) or 'careday' in cell.group(1) or 'visit' in cell.group(1)):
                days[d] = True
        clients.append((name, days))
    return clients

r = s.get(f'{BASE}/Clients.aspx', timeout=30)
txt = r.text
vs = re.search(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', txt, re.S)
vsg = re.search(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', txt, re.S)
ev = re.search(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', txt, re.S)
data = {
    '__EVENTTARGET': '', '__EVENTARGUMENT': '',
    '__VIEWSTATE': vs.group(1) if vs else '',
    '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
    '__EVENTVALIDATION': ev.group(1) if ev else '',
    'ShowRecords': '4000',
    'ctl00$Content$Go2': 'Go',
}
r2 = s.post(f'{BASE}/Clients.aspx', data=data, timeout=60)
print(f'POST ShowRecords=4000: {len(r2.text)} bytes')
clients = parse_clients(r2.text)
print(f'clients parsed: {len(clients)}')
json.dump(clients, open('/tmp/carecenta_clients_week.json', 'w'), ensure_ascii=False)
print('saved')
# show day distribution for our key days: Day3=Tue(4), Day4=Wed(5)
tue = [c[0] for c in clients if c[1].get(3)]
wed = [c[0] for c in clients if c[1].get(4)]
print(f'Carecenta Tuesday attendees: {len(tue)}')
print(f'Carecenta Wednesday attendees: {len(wed)}')
