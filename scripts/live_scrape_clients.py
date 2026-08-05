#!/usr/bin/env python3
"""Live Carecenta scrape: full client list with weekly attendance (all days).
Login via requests (works), fetch Clients.aspx, extract all rows via pagination
if needed, or read the current-page table + count rows."""
import json
import os
import re
import sqlite3

import requests

BASE = 'https://goj.daycenta.com'
creds = json.load(open(os.path.expanduser('~/.hermes/profiles/work/secrets/carecenta.json')))
USER = creds.get('email') or creds.get('login')
PASS = creds.get('password')

s = requests.Session()
r = s.get(f'{BASE}/', timeout=30)
vs = re.search(r'name="__VIEWSTATE" value="([^"]+)"', r.text)
vsg = re.search(r'name="__VIEWSTATEGENERATOR" value="([^"]+)"', r.text)
ev = re.search(r'name="__EVENTVALIDATION" value="([^"]+)"', r.text)
data = {
    '__EVENTTARGET': '', '__EVENTARGUMENT': '',
    '__VIEWSTATE': vs.group(1), '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
    '__EVENTVALIDATION': ev.group(1) if ev else '',
    'login': USER, 'password': PASS,
}
r = s.post(f'{BASE}/Default.aspx', data=data, timeout=30)
print(f'login POST → {r.url}')

# now fetch Clients.aspx
r = s.get(f'{BASE}/Clients.aspx', timeout=30)
print(f'Clients.aspx: {r.status_code}, {len(r.text)} bytes')
open('/tmp/clients_live.html', 'w').write(r.text)

# parse the weekly table rows
# Day1=Aug2(Sun) Day2=Aug3(Mon) Day3=Aug4(Tue) Day4=Aug5(Wed) Day5=Aug6(Thu) Day6=Aug7(Fri) Day7=Aug8(Sat)
rows = re.findall(r'<tr[^>]*>\s*<td[^>]*>.*?<td[^>]*class="[^"]*Client[^"]*"[^>]*>(.*?)</td>.*?</tr>', r.text, re.S)
print(f'client rows: {len(rows)}')

# simpler: find name cells + day cells
names = re.findall(r'<td[^>]*class="[^"]*Client[^"]*"[^>]*>.*?<b[^>]*>(.*?)</b>', r.text, re.S)
print(f'names found: {len(names)}')
for n in names[:10]:
    print(f'  {n.strip()[:60]}')
