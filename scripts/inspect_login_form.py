#!/usr/bin/env python3
"""Inspect the login form field names from the live page."""
import json
import os
import re

import requests

BASE = 'https://goj.daycenta.com'
s = requests.Session()
r = s.get(BASE + '/', timeout=30)
# find all input fields
inputs = re.findall(r'<input[^>]+>', r.text)
for inp in inputs:
    name = re.search(r'name="([^"]+)"', inp)
    iid = re.search(r'id="([^"]+)"', inp)
    itype = re.search(r'type="([^"]+)"', inp)
    if name and 'VIEWSTATE' not in name.group(1) and 'EVENT' not in name.group(1):
        print(f'name={name.group(1)!r} id={iid.group(1) if iid else None!r} type={itype.group(1) if itype else None!r}')
