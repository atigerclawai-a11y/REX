#!/usr/bin/env python3
"""Inspect the ShowRecords select markup to get its exact name + event target."""
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

# find ShowRecords select raw markup
idx = txt.find('ShowRecords')
print('ShowRecords context:')
print(re.sub(r'\s+', ' ', txt[idx-300:idx+400])[:700])

# grid ID — look for the table with clientLink rows
g = re.search(r'<table[^>]*id="([^"]*grd[^"]*)"', txt, re.I)
print(f'\ngrid table id: {g.group(1) if g else "not found"}')
# datagrid client IDs
g2 = re.findall(r'id="ctl00_Content_(\w+)"', txt)
print(f'ctl00_Content_* ids: {sorted(set(g2))[:20]}')
