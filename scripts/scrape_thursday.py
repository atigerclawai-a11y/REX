#!/usr/bin/env python3
"""PROPER Thursday sync: login to live Carecenta, scrape Clients.aspx fully,
extract Thursday (Day5=Aug 6) roster with shift times, and reconcile."""
import json
import os
import pickle
import re
import requests

BASE = 'https://goj.daycenta.com'
s = requests.Session()
s.cookies = pickle.load(open('/tmp/carecenta_cookies.pkl', 'rb'))

def parse_clients(html):
    """Parse client rows: name + day cells with appointment times."""
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
    return clients

# GET Clients.aspx with ShowRecords=1000 (worked before — 399 clients)
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
    'ShowRecords': '1000',
    'ctl00$Content$Go2': 'Go',
}
r2 = s.post(f'{BASE}/Clients.aspx', data=data, timeout=90)
print(f'POST ShowRecords=1000: {len(r2.text)} bytes')
clients = parse_clients(r2.text)
print(f'parsed clients: {len(clients)}')

# Thursday = Day5 (Aug 6)
thu = [(name, days.get(5), days) for name, days in clients if days.get(5)]
print(f'\nThursday (Day5) clients with times: {len(thu)}')
for name, t, days in thu[:10]:
    print(f'  {name}: {t} (all days: {days})')

json.dump([[n, t, d] for n, t, d in thu], open('/tmp/thursday_live.json', 'w'), ensure_ascii=False)
print('\nsaved /tmp/thursday_live.json')
