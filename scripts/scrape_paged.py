#!/usr/bin/env python3
"""ShowRecords=1000 with Page pagination — get all clients."""
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

# first GET to establish form state
r = s.get(f'{BASE}/Clients.aspx', timeout=30)
all_clients = []
for page in [0, 1, 2, 3, 4]:
    vs = re.search(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', r.text, re.S)
    vsg = re.search(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', r.text, re.S)
    ev = re.search(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', r.text, re.S)
    data = {
        '__EVENTTARGET': '', '__EVENTARGUMENT': '',
        '__VIEWSTATE': vs.group(1) if vs else '',
        '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
        '__EVENTVALIDATION': ev.group(1) if ev else '',
        'ShowRecords': '1000',
        'Page': str(page),
        'ctl00$Content$Go2': 'Go',
    }
    try:
        r2 = s.post(f'{BASE}/Clients.aspx', data=data, timeout=90)
    except Exception as e:
        print(f'page {page}: timeout {e}')
        break
    clients = parse_clients(r2.text)
    seen = {c[0] for c in all_clients}
    new = [c for c in clients if c[0] not in seen]
    all_clients.extend(new)
    print(f'page {page}: {len(clients)} parsed, {len(new)} new (total {len(all_clients)})')
    if len(clients) < 1000:
        break
    r = r2  # reuse VIEWSTATE for next page

json.dump(all_clients, open('/tmp/carecenta_clients_week.json', 'w'), ensure_ascii=False)
print(f'TOTAL: {len(all_clients)} clients saved')
tue = [c[0] for c in all_clients if c[1].get(3)]
wed = [c[0] for c in all_clients if c[1].get(4)]
print(f'Carecenta Tue: {len(tue)}, Wed: {len(wed)}')
