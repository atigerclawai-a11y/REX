#!/usr/bin/env python3
"""For each of the 34 docs: did vision recovery already extract+apply its forms?
Check: (a) extraction files in blank_parse, (b) ocr_scan rows in DB from that doc."""
import json
import os
import re
import sqlite3

p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')

docs34 = json.load(open('/tmp/manifest_34.json'))
print('doc | extracted-forms-in-dir | ocr_scan-rows-in-DB | status')
for docname, pages, path in docs34:
    m = re.search(r'doc(\d{6})', str(docname))
    docnum = m.group(1) if m else str(docname)[:6]
    # (a) extraction files
    bdir = '/Users/mainsobhelper/Desktop/REX/blank_parse'
    n_ext = 0
    if os.path.isdir(bdir):
        for d in os.listdir(bdir):
            if d.startswith('doc' + docnum):
                for ex in ['extraction.json', 'extraction_surya.json', 'extraction_focr.json']:
                    f = os.path.join(bdir, d, ex)
                    if os.path.exists(f):
                        try:
                            j = json.load(open(f))
                            if isinstance(j, dict):
                                n_ext = max(n_ext, len(j))
                        except Exception:
                            pass
    # (b) ocr_scan rows in DB tagged from this doc (source_sheet LIKE %docnum%)
    n_db = p.execute("""SELECT COUNT(*) FROM client_menus
        WHERE source_sheet LIKE ?""", (f'%{docnum}%',)).fetchone()[0]
    status = '✅ RECOVERED' if n_ext > 0 or n_db > 0 else '❌ GENUINELY UNREAD'
    print(f'{docname} | {n_ext} | {n_db} | {status}')

p.close()
