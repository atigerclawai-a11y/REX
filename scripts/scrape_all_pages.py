#!/usr/bin/env python3
"""PAGINATED scrape: get ALL clients from Carecenta (page through)."""
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

all_clients = []
page = 1
while True:
    r = s.get(f'{BASE}/Clients.aspx?page={page}', timeout=30)
    txt = r.text
    clients = parse_clients(txt)
    if not clients:
        # try POST-based pagination (Page field)
        vs = re.search(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', txt, re.S)
        vsg = re.search(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', txt, re.S)
        ev = re.search(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', txt, re.S)
        data = {
            '__EVENTTARGET': '', '__EVENTARGUMENT': '',
            '__VIEWSTATE': vs.group(1) if vs else '',
            '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
            '__EVENTVALIDATION': ev.group(1) if ev else '',
            'ShowRecords': '1000',
            'Page': str(page),
            'ctl00$Content$Go2': 'Go',
        }
        r2 = s.post(f'{BASE}/Clients.aspx', data=data, timeout=30)
        txt = r2.text
        clients = parse_clients(txt)
    print(f'page {page}: {len(clients)} clients')
    if not clients:
        break
    # dedupe
    seen = {c[0] for c in all_clients}
    new = [c for c in clients if c[0] not in seen]
    all_clients.extend(new)
    if len(new) == 0 or len(clients) < 1000:
        break
    page += 1

print(f'\nTOTAL: {len(all_clients)} unique clients')
json.dump(all_clients, open('/tmp/carecenta_clients_week.json', 'w'), ensure_ascii=False)
print('saved /tmp/carecenta_clients_week.json')
