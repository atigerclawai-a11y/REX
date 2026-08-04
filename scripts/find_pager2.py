#!/usr/bin/env python3
"""Find the pagination control on Clients.aspx — look for page links/buttons."""
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

# search for grid navigation: links with Page numbers, "Last", "First", etc.
for pat in [r'href="[^"]*Page[^"]*"', r'ctl00\$Content\$[A-Za-z]+Page', r'__doPostBack\(&#39;ctl00\$Content\$[^)]*\)',
            r'>(Next|Last|First|Previous)<', r'Pager[^<]{0,50}', r'gridView[^"]{0,30}']:
    m = re.findall(pat, txt)
    if m:
        print(f'{pat}:\n  {m[:8]}')

# select elements with names
sels = re.findall(r'<select[^>]*name="([^"]+)"', txt)
print(f'\nall selects: {sels}')

# inputs with names (non-hidden)
inps = re.findall(r'<input[^>]*name="([^"]+)"', txt)
print(f'\ninputs: {inps[:20]}')
