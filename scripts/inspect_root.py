#!/usr/bin/env python3
"""Inspect root page form structure for login."""
import re
import requests

BASE = 'https://goj.daycenta.com'
r = requests.get(f'{BASE}/', timeout=30, allow_redirects=True)
print(f'root: {r.status_code}, {len(r.text)} bytes, final url {r.url}')
inputs = re.findall(r'<input[^>]*name="([^"]+)"', r.text)
print(f'inputs: {inputs}')
m = re.search(r'<form[^>]*action="([^"]*)"', r.text)
print(f'form action: {m.group(1) if m else "NONE"}')
for f in ['login', 'password', 'txtLogin', 'Password', '__VIEWSTATE', 'btnLogin']:
    if f in r.text:
        print(f'  contains: {f}')
