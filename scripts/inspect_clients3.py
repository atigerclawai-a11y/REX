#!/usr/bin/env python3
"""Deep inspect Clients.aspx HTML — find name cells + day cell patterns."""
import re

txt = open('/tmp/clients_auth.html').read()
print(f'len: {len(txt)}')

# find a client name cell pattern
# look for "careday" or "apptime" occurrences
print(f'apptime count: {txt.count("apptime")}')
print(f'careday count: {txt.count("careday")}')
print(f'Day1 class count: {txt.count(chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(61)+chr(34)+chr(68)+chr(97)+chr(121)+chr(49)+chr(34))}')

# find one client row region: look for a known name
for nm in ['Aronchik', 'Agaronova', 'Adyan', 'Abramova']:
    idx = txt.find(nm)
    if idx > 0:
        print(f'\n=== {nm} at {idx} ===')
        print(txt[idx-200:idx+600].replace('\n', ' ')[:700])
        break
