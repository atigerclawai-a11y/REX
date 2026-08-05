#!/usr/bin/env python3
"""Check what Clients.aspx actually returned (login redirect?)."""
import re

txt = open('/tmp/clients_live_p1.html').read()
# title and key markers
t = re.search(r'<title>([^<]*)</title>', txt)
print(f'title: {t.group(1) if t else "none"}')
if 'login' in txt.lower() or 'Login' in txt:
    print('CONTAINS LOGIN MARKER')
    # find the form fields
    inputs = re.findall(r'<input[^>]*name="([^"]+)"', txt)
    print(f'inputs: {inputs[:10]}')
else:
    print('no login marker — checking body text')
    body = re.sub(r'<[^>]+>', ' ', txt)
    print(body[:300])
