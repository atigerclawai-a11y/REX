#!/usr/bin/env python3
"""Extract one full client row to understand Day1-Day7 mapping + times."""
import re

txt = open('/tmp/clients_raw.html').read()
# find Aronchik's row region
idx = txt.find('Aronchik')
seg = txt[idx:idx + 3000]

# extract the td cells with their Day classes
cells = re.findall(r'<td class="(Day\d)" id="C\d+D\d+"[^>]*>(.*?)</td>', seg, re.S)
for cls, body in cells:
    clean = re.sub(r'<[^>]+>', ' ', body)
    clean = re.sub(r'\s+', ' ', clean).strip()
    print(f'{cls}: {clean[:100]}')
