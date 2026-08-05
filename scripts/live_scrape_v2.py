#!/usr/bin/env python3
"""Live Carecenta scrape: login via /, fetch Clients.aspx, paginate all pages,
extract weekly day attendance. Day cells: Day1=Aug2(Sun)...Day7=Aug8(Sat).
THU=Day5 (Aug 6), FRI=Day6 (Aug 7), TUE=Day3 (Aug 4), WED=Day4 (Aug 5)."""
import json
import os
import re
import requests

BASE = 'https://goj.daycenta.com'
creds = json.load(open(os.path.expanduser('~/.hermes/profiles/work/secrets/carecenta.json')))
USER = creds.get('email') or creds.get('login')
PASS = creds.get('password')

s = requests.Session()
r = s.get(f'{BASE}/', timeout=30)
vs = re.search(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', r.text, re.S)
vsg = re.search(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', r.text, re.S)
ev = re.search(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', r.text, re.S)
print(f'VIEWSTATE found: {bool(vs)}, VSG: {bool(vsg)}, EV: {bool(ev)}')
data = {
    '__EVENTTARGET': '', '__EVENTARGUMENT': '',
    '__VIEWSTATE': vs.group(1) if vs else '',
    '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
    '__EVENTVALIDATION': ev.group(1) if ev else '',
    'txtLogin': USER, 'Password': PASS, 'docookie': 'on',
}
r = s.post(f'{BASE}/', data=data, timeout=30)
print(f'login → {r.url}')

# Clients.aspx with ShowRecords=50
r = s.get(f'{BASE}/Clients.aspx', timeout=30)
txt = r.text
open('/tmp/clients_live_p1.html', 'w').write(txt)
print(f'Clients.aspx: {len(txt)} bytes')

# find the client rows: each row has a name cell + day cells
# day cell pattern: <td class="Day3" id="C<id>D<MMDDYYYY>">
# name: usually in a td with the client name text
# extract name + which days have appointments (careday visit matched)
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', txt, re.S)
client_rows = 0
for row in rows:
    if 'Day1' in row and 'Client' in row:
        client_rows += 1
print(f'client rows detected: {client_rows}')
