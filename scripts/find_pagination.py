#!/usr/bin/env python3
"""Find pagination control + visible time text in Clients.aspx."""
import re

txt = open('/tmp/clients_raw.html').read()

# pagination: look for "Next", page numbers, __doPostBack targets
for pat in [r'__doPostBack\([^)]*\)', r'>\s*Next\s*<', r'>\s*[0-9]+\s*<', r'Page[^<]{0,30}']:
    m = re.findall(pat, txt)
    if m:
        print(f'{pat}: {m[:6]}')

# look for grid pager
idx = txt.find('Pager')
if idx > 0:
    print('\nPager region:', re.sub(r'\s+', ' ', txt[idx-100:idx+400])[:400])

# visible time text — find where "9AM" appears in a day cell
for m in re.finditer(r'9AM|1:15', txt):
    s = max(0, m.start()-150)
    seg = re.sub(r'\s+', ' ', txt[s:m.end()+80])
    print(f'\nTIME CONTEXT @{m.start()}: ...{seg[-200:]}')
    break

# any "Showing" or "of" pager text
for pat in [r'Showing[^<]{0,40}', r'\d+\s*of\s*\d+', r'Page\s*\d+\s*of']:
    m = re.findall(pat, txt)
    if m:
        print(f'{pat}: {m[:5]}')
