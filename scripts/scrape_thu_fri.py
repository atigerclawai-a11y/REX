#!/usr/bin/env python3
"""Full paginated scrape of Clients.aspx: THU (Aug 6) + FRI (Aug 7) by shift.
Uses requests session (login works). Day5=Thu Aug 6, Day6=Fri Aug 7 (Day1=Aug 2 Sun).
Shift: apptime contains 'AM' → S1, 'PM' → S2."""
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

def login():
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
    r2 = s.post(BASE + '/', data=data, timeout=30, allow_redirects=True)
    return 'home.aspx' in r2.url or 'Dashboard' in r2.text

if not login():
    print('LOGIN FAILED')
    sys.exit(1)
print('logged in')

def parse_page(html):
    """Return list of (name, thu_time, fri_time)."""
    out = []
    # split by client blocks: each starts with <tr containing clientLink
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    for row in rows:
        name_m = re.search(r'class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', row)
        if not name_m:
            continue
        name = f"{name_m.group(1).strip()}, {name_m.group(2).strip()}"
        # day cells
        thu = re.search(r'<td class="Day5"[^>]*>(.*?)</td>', row, re.S)
        fri = re.search(r'<td class="Day6"[^>]*>(.*?)</td>', row, re.S)
        thu_t = re.search(r'class="apptime">([^<]+)</span>', thu.group(1)) if thu else None
        fri_t = re.search(r'class="apptime">([^<]+)</span>', fri.group(1)) if fri else None
        out.append((name, thu_t.group(1) if thu_t else None, fri_t.group(1) if fri_t else None))
    return out

# get page 1 + page size select options
r = s.get(BASE + '/Clients.aspx', timeout=30)
html = r.text
results = parse_page(html)
print(f'page 1: {len(results)} clients (showing first: {results[0] if results else None})')

# pagination: find the page-size select and its name, plus total pages
sel_m = re.search(r'<select[^>]*name="([^"]*PageSize[^"]*)"[^>]*>(.*?)</select>', html, re.S)
print(f'pageSize select name: {sel_m.group(1) if sel_m else "NOT FOUND"}')
if sel_m:
    opts = re.findall(r'value="(\d+)"', sel_m.group(2))
    print(f'options: {opts}')
