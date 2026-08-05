#!/usr/bin/env python3
"""Inspect the live login page structure."""
import json
import os
import re
import requests

BASE = 'https://goj.daycenta.com'
r = requests.get(f'{BASE}/Login.aspx', timeout=30)
print(f'Login.aspx: {r.status_code}, {len(r.text)} bytes')
# find all form fields
inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*>', r.text)
print(f'inputs: {inputs}')
m = re.search(r'<form[^>]*action="([^"]*)"', r.text)
print(f'form action: {m.group(1) if m else "NONE"}')
m2 = re.search(r'<form[^>]*method="([^"]*)"', r.text)
print(f'form method: {m2.group(1) if m2 else "NONE"}')
