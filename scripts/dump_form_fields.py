#!/usr/bin/env python3
"""Extract ALL form fields from Clients.aspx (names + values) to replicate the
ShowRecords submit correctly."""
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

# all inputs with name + value
print('=== inputs ===')
for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*>', txt):
    name = m.group(1)
    val_m = re.search(r'value="([^"]*)"', m.group(0))
    typ_m = re.search(r'type="([^"]+)"', m.group(0))
    print(f'  {name} = {val_m.group(1)[:50] if val_m else ""!r} (type={typ_m.group(1) if typ_m else "?"})')

print('\n=== selects ===')
for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', txt, re.S):
    name = m.group(1)
    sel = re.search(r'selected[^>]*>([^<]+)', m.group(2))
    print(f'  {name} = {sel.group(1).strip() if sel else "?"}')
