#!/usr/bin/env python3
"""Carecenta live login helper — reads creds from secrets file (never prints),
does the ASP.NET WebForms login, prints only session status."""
import json
import os
import re
import sys

import requests

BASE = 'https://goj.daycenta.com'
creds = json.load(open(os.path.expanduser('~/.hermes/profiles/work/secrets/carecenta.json')))
USER = creds.get('email') or creds.get('user')
PASS = creds.get('password')

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})

# 1. GET login page for VIEWSTATE
r = s.get(BASE + '/', timeout=30)
print(f'GET / -> {r.status_code}, {len(r.text)} bytes')
vs = re.search(r'id="__VIEWSTATE" value="([^"]+)"', r.text)
vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]+)"', r.text)
ev = re.search(r'id="__EVENTVALIDATION" value="([^"]+)"', r.text)
print(f'VIEWSTATE found: {bool(vs)} {bool(vsg)} {bool(ev)}')

if not vs:
    sys.exit('login page structure unexpected')

# 2. POST login
data = {
    '__EVENTTARGET': '', '__EVENTARGUMENT': '',
    '__VIEWSTATE': vs.group(1),
    '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else '',
    '__EVENTVALIDATION': ev.group(1) if ev else '',
    'txtLogin': USER, 'Password': PASS,
    'aliasOK': '1',
    'docookie': '1',
    'Page': '',
    'ctl00$Content$btnLogin': ' Sign In ',
}
r2 = s.post(BASE + '/', data=data, timeout=30, allow_redirects=True)
print(f'POST / -> {r2.status_code}, final URL: {r2.url}')
print(f'still on login: {"Password:" in r2.text and "ID:" in r2.text}')
# save session for reuse
import pickle
pickle.dump(s.cookies, open('/tmp/carecenta_cookies.pkl', 'wb'))
print('cookies saved')
