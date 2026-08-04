#!/usr/bin/env python3
"""Fetch Clients.aspx weekly table, count THU (idx 6) and FRI (idx 7) columns by shift time."""
import json
import os
import pickle
import re
import sys

import requests

BASE = 'https://goj.daycenta.com'
creds = json.load(open(os.path.expanduser('~/.hermes/profiles/work/secrets/carecenta.json')))
USER = creds.get('email') or creds.get('user')
PASS = creds.get('password')

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})

# login
r = s.get(BASE + '/', timeout=30)
vs = re.search(r'id="__VIEWSTATE" value="([^"]+)"', r.text)
vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]+)"', r.text)
ev = re.search(r'id="__EVENTVALIDATION" value="([^"]+)"', r.text)
data = {
    '__EVENTTARGET': '', '__EVENTARGUMENT': '',
    '__VIEWSTATE': vs.group(1), '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
    '__EVENTVALIDATION': ev.group(1) if ev else '',
    'txtLogin': USER, 'Password': PASS, 'aliasOK': '1',
    'docookie': '1', 'Page': '', 'ctl00$Content$btnLogin': ' Sign In ',
}
s.post(BASE + '/', data=data, timeout=30, allow_redirects=True)

# Clients.aspx — set page size 50
r = s.get(BASE + '/Clients.aspx', timeout=30)
print(f'Clients.aspx: {r.status_code}, {len(r.text)} bytes')

# find the table — look for weekly schedule cells with time ranges
# names are in "Last, First" format; columns 2-8 = SUN..SAT; times like 9AM-1PM
# Count THU (idx 6) and FRI (idx 7)
thu_s1 = thu_s2 = fri_s1 = fri_s2 = 0
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.S)
names_with_days = []
for row in rows:
    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
    cells = [c for c in cells if c]
    if len(cells) < 8:
        continue
    name = cells[0]
    if not re.search(r'[A-Za-z]', name):
        continue
    thu_cell = cells[6] if len(cells) > 6 else ''
    fri_cell = cells[7] if len(cells) > 7 else ''
    # shift by time
    for cell, counters in ((thu_cell, ['THU_S1', 'THU_S2']), (fri_cell, ['FRI_S1', 'FRI_S2'])):
        m = re.search(r'(\d{1,2}:\d{2}[AP]M)', cell)
        if not m:
            continue
        t = m.group(1)
        # S1 = 9AM-1PM / 10AM-2PM ; S2 = 1:15PM-5:15PM
        if 'AM' in t:
            counters_ref = counters[0]
        else:
            counters_ref = counters[1]
        if counters_ref == 'THU_S1':
            thu_s1 += 1
        elif counters_ref == 'THU_S2':
            thu_s2 += 1
        elif counters_ref == 'FRI_S1':
            fri_s1 += 1
        else:
            fri_s2 += 1
        names_with_days.append((name, counters_ref))

print(f'\nTHU: S1={thu_s1} S2={thu_s2} total={thu_s1+thu_s2}')
print(f'FRI: S1={fri_s1} S2={fri_s2} total={fri_s1+fri_s2}')
print(f'rows parsed: {len(names_with_days)}')
# save for verification
json.dump(names_with_days, open('/tmp/thu_fri_roster.json', 'w'))
