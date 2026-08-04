#!/usr/bin/env python3
"""Parse the saved Clients.aspx HTML — count clients on page, find pagination,
extract Day6/7 (THU/FRI) cells for visible clients."""
import re

txt = open('/tmp/clients_raw.html').read()

# client blocks: each has class="Last" + class="First" + clientid
clients = re.findall(r'class="Last">([^<]+)</span>\s*,\s*<span class="First">([^<]+)</span>\s*<span class="greytxt clientid">(\d+)</span>', txt)
print(f'clients on page: {len(clients)}')

# day cells: id="C<id>D<MMDDYYYY>"
daycells = re.findall(r'id="C(\d+)D(\d{8})"', txt)
print(f'day cells: {len(daycells)}')
# sample distinct day IDs
print('sample day IDs:', daycells[:8])

# pagination?
for pat in ['PageSize', 'pageSize', 'page-size', 'ctl00$Content$', '__PAGER', 'Page$', 'pager']:
    m = re.findall(r'.{0,40}' + pat + r'.{0,60}', txt)
    if m:
        print(f'\n{pat}: {m[:3]}')

# dropdown for page size?
sel = re.findall(r'<select[^>]*>(.*?)</select>', txt, re.S)
print(f'\nselects: {len(sel)}')
for s in sel[:2]:
    opts = re.findall(r'<option[^>]*>([^<]*)</option>', s)
    print('  options:', opts[:10])

# viewstate size
vs = re.search(r'id="__VIEWSTATE" value="([^"]+)"', txt)
print(f'\nVIEWSTATE len: {len(vs.group(1)) if vs else 0}')

# Day classes present
days = set(re.findall(r'class="(Day\d)"', txt))
print(f'Day classes: {sorted(days)}')
