#!/usr/bin/env python3
"""Inspect Clients.aspx HTML structure — find how schedule data is rendered."""
import json
import os
import re

import requests

BASE = 'https://goj.daycenta.com'
creds = json.load(open(os.path.expanduser('~/.hermes/profiles/work/secrets/carecenta.json')))
USER = creds.get('email') or creds.get('user')
PASS = creds.get('password')

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
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

# save for inspection
open('/tmp/clients_raw.html', 'w').write(txt)

# look for common markers
print('table tags:', txt.count('<table'))
print('tr tags:', txt.count('<tr'))
print('td tags:', txt.count('<td'))
print('"Adyan" present:', 'Adyan' in txt)
print('"9AM" present:', '9AM' in txt)
print('"9:00" present:', '9:00' in txt)
print('"1:15" present:', '1:15' in txt)
print('SUN/MON headers:', re.findall(r'<th[^>]*>(SUN|MON|TUE|WED|THU|FRI|SAT)</th>', txt)[:10])

# find a sample row region
idx = txt.find('Aronchik')
if idx > 0:
    print('\n--- sample around Aronchik ---')
    print(txt[idx-200:idx+600].replace('\n', ' ')[:700])
