#!/usr/bin/env python3
"""Find pagination control in Clients.aspx HTML."""
import re

txt = open('/tmp/clients_auth.html').read()

# look for page navigation
for pat in ['ShowRecords', 'PageSize', 'pager', 'Go2', '__doPostBack', 'Pager', 'PageNumber']:
    idxs = [m.start() for m in re.finditer(pat, txt)]
    if idxs:
        print(f'{pat}: {len(idxs)} hits')
        for i in idxs[:3]:
            print(f'    ...{txt[max(0,i-80):i+120].replace(chr(10)," ")}...')
