#!/usr/bin/env python3
"""Rigorous check of the 24 auth-Thu extras:
(a) are they in the full portal HTML (any day) under variant spelling?
(b) if yes, do they have a Day5 cell? (genuine spelling-variant attendee)
(c) if not in portal at all → auth row may be stale OR portal incomplete."""
import re
import sqlite3

html = open('/tmp/clients_full.html').read()

# Build portal roster: name -> day cells present
portal = {}
for m in re.finditer(r'<span class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>', html):
    last, first = m.group(1).strip(), m.group(2).strip()
    name = f'{last} {first}'
    start = m.start()
    row_start = html.rfind('<tr', 0, start)
    row_end = html.find('</tr>', start)
    if row_start == -1 or row_end == -1:
        continue
    row = html[row_start:row_end]
    days = {}
    for d in range(1, 8):
        cell = re.search(rf'class="Day{d}"[^>]*>(.*?)</td>', row, re.S)
        if cell and ('spanappt' in cell.group(1) or re.search(r'\d{1,2}:\d{2}', cell.group(1))):
            days[d] = True
    portal[name.lower()] = days

print(f'portal clients: {len(portal)}')

from rapidfuzz import fuzz

targets = ['Aronchik Bronya', 'Astrakhan Bella', 'Breicher Larisa', 'Britavskaya Sofiya',
           'Brodskaya Lidiya', 'Buslayeva Alisa', 'Chebotareva Galina', 'Chepizhko Raya',
           'Chupikova Elvira', 'Coniglio Vera', 'Diadia Valentina', 'Dirul Serghei',
           'Dmitriyeva Tamara', 'Dodik Sima', 'Dovgalyuk Zelda', 'Dranikov Berta',
           'Drochik Oleg', 'Elbert Milla', 'Erlikhman Rita', 'Fedorova Olga',
           'Feldman Klavdya', 'Firdman Mark', 'Fridman Mikhail', 'Furman Vladimir']

print('\n=== 24 auth-Thu extras: portal status ===')
for t in targets:
    low = t.lower()
    if low in portal:
        print(f'  {t}: IN PORTAL, days={sorted(portal[low].keys())}')
        continue
    # fuzzy whole-name
    best, bs = None, 0
    for pn, days in portal.items():
        s = fuzz.WRatio(low, pn)
        if s > bs:
            best, bs = pn, s
    if bs >= 85:
        print(f'  {t}: FUZZY={best} ({bs:.0f}) days={sorted(portal[best].keys())}')
    else:
        # surname-only match
        sur = low.split()[0]
        sur_hits = [pn for pn in portal if pn.split()[0] == sur]
        if sur_hits:
            print(f'  {t}: SURNAME {sur} → {sur_hits} (none Thu? )')
        else:
            print(f'  ⚠️ {t}: ABSENT from portal entirely')
