#!/usr/bin/env python3
"""Inspect Day5 cell raw HTML — what distinguishes present vs absent?"""
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
open('/tmp/clients_full.html', 'w').write(r2.text)
print(f'saved /tmp/clients_full.html ({len(r2.text)} bytes)')

# find a Day5 cell sample
m = re.search(r'<td class="Day5"[^>]*>.*?</td>', r2.text, re.S)
if m:
    print('Day5 cell sample:')
    print(m.group(0)[:400])
else:
    print('no Day5 td found')

# count Day5 cells with different markers
day5_cells = re.findall(r'<td class="Day5"[^>]*>.*?</td>', r2.text, re.S)
print(f'\nDay5 cells total: {len(day5_cells)}')
with_time = [c for c in day5_cells if re.search(r'\d{1,2}:\d{2}', c)]
with_span = [c for c in day5_cells if 'spanappt' in c or 'appt' in c]
print(f'with time: {len(with_time)}, with appt span: {len(with_span)}')
