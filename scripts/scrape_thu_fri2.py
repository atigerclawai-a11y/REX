#!/usr/bin/env python3
"""Complete THU/FRI scraper: ShowRecords=50, extract all pages via POST with
VIEWSTATE cycling. Day5=Thu Aug 6, Day6=Fri Aug 7. S1=AM time, S2=PM time."""
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
    return 'home.aspx' in r2.url

login()
print('logged in')

def fetch_clients():
    """GET Clients.aspx, return (html, viewstate, validation, generator)."""
    r = s.get(BASE + '/Clients.aspx', timeout=30)
    html = r.text
    vs = re.search(r'id="__VIEWSTATE" value="([^"]+)"', html)
    ev = re.search(r'id="__EVENTVALIDATION" value="([^"]+)"', html)
    vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]+)"', html)
    return html, (vs.group(1) if vs else ''), (ev.group(1) if ev else ''), (vsg.group(1) if vsg else '')

def post_clients(data_extra, vs, ev, vsg):
    """POST to Clients.aspx with extra form data, return (html, vs, ev, vsg)."""
    data = {
        '__EVENTTARGET': '', '__EVENTARGUMENT': '',
        '__VIEWSTATE': vs, '__VIEWSTATEGENERATOR': vsg, '__EVENTVALIDATION': ev,
        'ClientStatus': 'Active', 'C': '', 'PR': '', 'State': '', 'Key': '',
        'clientName': '', 'LocationID': '',
        'ctl00$Content$Go2': '',
    }
    data.update(data_extra)
    r = s.post(BASE + '/Clients.aspx', data=data, timeout=30, allow_redirects=True)
    html = r.text
    vs2 = re.search(r'id="__VIEWSTATE" value="([^"]+)"', html)
    ev2 = re.search(r'id="__EVENTVALIDATION" value="([^"]+)"', html)
    vsg2 = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]+)"', html)
    return html, (vs2.group(1) if vs2 else vs), (ev2.group(1) if ev2 else ev), (vsg2.group(1) if vsg2 else vsg)

def parse_page(html):
    out = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    for row in rows:
        name_m = re.search(r'class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', row)
        if not name_m:
            continue
        name = f"{name_m.group(1).strip()}, {name_m.group(2).strip()}"
        thu = re.search(r'<td class="Day5"[^>]*>(.*?)</td>', row, re.S)
        fri = re.search(r'<td class="Day6"[^>]*>(.*?)</td>', row, re.S)
        thu_t = re.search(r'class="apptime">([^<]+)</span>', thu.group(1)) if thu else None
        fri_t = re.search(r'class="apptime">([^<]+)</span>', fri.group(1)) if fri else None
        out.append({'name': name, 'thu': thu_t.group(1) if thu_t else None,
                    'fri': fri_t.group(1) if fri_t else None})
    return out

# 1. set ShowRecords=50 first
html, vs, ev, vsg = fetch_clients()
html, vs, ev, vsg = post_clients({'ShowRecords': '50'}, vs, ev, vsg)
results = parse_page(html)
print(f'after ShowRecords=50: {len(results)} clients on page')

# 2. paginate: look for page buttons — try __doPostBack targets on the grid
#    Common pattern: grid pager posts 'ctl00$Content$grdClients$ctlNN$ctlMM'
#    Find the grid ID from the HTML
grid = re.search(r'id="ctl00_Content_([A-Za-z]+)"', html)
print(f'grid id: {grid.group(1) if grid else "?"}')

all_results = list(results)
page = 1
max_pages = 50
while page < max_pages:
    # find next-page link in this html
    nxt = re.findall(r"__doPostBack\('([^']+)'\)", html)
    candidates = [n for n in nxt if 'Page' in n or '$ctl' in n]
    if not candidates:
        break
    # look for the NEXT button specifically
    nxt_btn = re.search(r"__doPostBack\('([^']+Next[^']*)'\)|href=\"javascript:__doPostBack\('([^']+)'", html)
    target = None
    for cand in candidates:
        if 'Next' in cand or 'ctl1' in cand.lower():
            target = cand
            break
    if not target:
        print(f'no next target found on page {page}: {candidates[:5]}')
        break
    print(f'page {page}: target={target}')
    html, vs, ev, vsg = post_clients({'__EVENTTARGET': target, '__EVENTARGUMENT': ''}, vs, ev, vsg)
    page += 1
    rows = parse_page(html)
    if not rows:
        break
    all_results.extend(rows)
    print(f'  page {page}: +{len(rows)} (total {len(all_results)})')

print(f'\nTOTAL clients scraped: {len(all_results)}')
json.dump(all_results, open('/tmp/thu_fri_scrape.json', 'w'), indent=1)

thu_s1 = sum(1 for r in all_results if r['thu'] and 'AM' in r['thu'])
thu_s2 = sum(1 for r in all_results if r['thu'] and 'PM' in r['thu'])
fri_s1 = sum(1 for r in all_results if r['fri'] and 'AM' in r['fri'])
fri_s2 = sum(1 for r in all_results if r['fri'] and 'PM' in r['fri'])
print(f'\nTHU Aug 6: S1={thu_s1} S2={thu_s2} total={thu_s1+thu_s2}')
print(f'FRI Aug 7: S1={fri_s1} S2={fri_s2} total={fri_s1+fri_s2}')
