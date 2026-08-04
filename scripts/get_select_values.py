#!/usr/bin/env python3
"""Get exact select values from Clients.aspx (ClientStatus, C, PR, State) + find
the grid's pager postback targets."""
import json
import os
import re

import requests

BASE = 'https://goj.daycenta.com'
creds = json.load(open(os.path.expanduser('~/.hermes/profiles/work/secrets/carecenta.json')))
USER = creds.get('email') or creds.get('user')
PASS = creds.get('password')

s = requests.Session()
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
r = s.get(BASE + '/Clients.aspx', timeout=30)
txt = r.text

# exact select markup
for sel_name in ['ClientStatus', 'C', 'PR', 'State']:
    m = re.search(r'<select[^>]*name="' + sel_name + r'"[^>]*>(.*?)</select>', txt, re.S)
    if m:
        sel = re.search(r'<option[^>]*selected[^>]*>([^<]*)</option>', m.group(1))
        first = re.search(r'<option[^>]*>([^<]*)</option>', m.group(1))
        print(f'{sel_name}: selected={sel.group(1).strip() if sel else None!r} first={first.group(1).strip() if first else None!r}')

# postback targets in the page
targs = set(re.findall(r"__doPostBack\('([^']+)'", txt))
print(f'\npostback targets ({len(targs)}):')
for t in sorted(targs):
    print(f'  {t}')

# client count text
for pat in [r'Showing\s+\d+[^<]{0,30}', r'of\s+\d+', r'Total[^<]{0,30}\d+']:
    m = re.findall(pat, txt)
    if m:
        print(f'\n{pat}: {m[:3]}')
