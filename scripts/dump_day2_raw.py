#!/usr/bin/env python3
"""Raw dump of one day cell to find the time text pattern."""
import re

txt = open('/tmp/clients_raw.html').read()
idx = txt.find('Aronchik')
seg = txt[idx:idx + 4000]

# find the Day2 cell raw HTML
m = re.search(r'<td class="Day2" id="C\d+D\d+"[^>]*>(.*?)</td>', seg, re.S)
if m:
    raw = m.group(1)
    print('Day2 cell raw (first 1500):')
    print(raw[:1500])
