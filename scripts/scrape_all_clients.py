#!/usr/bin/env python3
"""Get ShowRecords options + build full paginated scrape.
Extract: client name (Last, First) + which days have appointments."""
import json
import os
import pickle
import re
import requests

BASE = 'https://goj.daycenta.com'
s = requests.Session()
s.cookies = pickle.load(open('/tmp/carecenta_cookies.pkl', 'rb'))

# get page + form fields
r = s.get(f'{BASE}/Clients.aspx', timeout=30)
txt = r.text

# ShowRecords options
opts = re.findall(r'<option value="(\d+)"', txt)
print(f'ShowRecords options: {opts}')

def parse_clients(html):
    """Extract (name, {day: True}) for each client row."""
    clients = []
    # split by clientLink anchors
    for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
        last, first = m.group(1).strip(), m.group(2).strip()
        name = f'{last} {first}'
        # find the row boundaries: from this name to the next client name
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

# page 1 (default 10)
clients = parse_clients(txt)
print(f'page1: {len(clients)} clients')

# try setting ShowRecords=200 via POST (full form)
vs = re.search(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', txt, re.S)
vsg = re.search(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', txt, re.S)
ev = re.search(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', txt, re.S)
data = {
    '__EVENTTARGET': '', '__EVENTARGUMENT': '',
    '__VIEWSTATE': vs.group(1) if vs else '',
    '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
    '__EVENTVALIDATION': ev.group(1) if ev else '',
    'ShowRecords': '200',
    'ctl00$Content$Go2': 'Go',
}
r2 = s.post(f'{BASE}/Clients.aspx', data=data, timeout=30)
txt2 = r2.text
print(f'POST ShowRecords=200: {len(txt2)} bytes')
clients2 = parse_clients(txt2)
print(f'after POST: {len(clients2)} clients')
if len(clients2) > len(clients):
    clients = clients2
    open('/tmp/clients_all.html', 'w').write(txt2)

json.dump(clients, open('/tmp/carecenta_clients_week.json', 'w'), ensure_ascii=False)
print(f'SAVED {len(clients)} clients')
for c in clients[:5]:
    print(f'  {c}')
