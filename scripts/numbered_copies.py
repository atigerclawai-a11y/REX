#!/usr/bin/env python3
"""Create numbered copies: ~/Desktop/REX/unreadable_34/NN_docXXX.pdf + generate
Drive share links (reader) for each."""
import json
import os
import shutil
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import warnings
warnings.filterwarnings('ignore')
import googleapiclient.discovery as disc
import CC_goj_change_log as ccl

svc = disc.build('drive', 'v3', credentials=ccl.get_creds(), cache_discovery=False)

mapping = json.load(open('/tmp/manifest_34_drive.json'))
OUT = '/Users/mainsobhelper/Desktop/REX/unreadable_34'
os.makedirs(OUT, exist_ok=True)

links = []
for m in mapping:
    n = m['n']
    src = None
    # find the actual source file
    docs34 = json.load(open('/tmp/manifest_34.json'))
    src = docs34[n-1][2]
    dst = os.path.join(OUT, f'{n:02d}_{m["doc"]}.pdf')
    if os.path.exists(src):
        shutil.copy2(src, dst)
    # make Drive file shareable (reader) and get link
    try:
        svc.permissions().create(fileId=m['drive_id'], body={
            'type': 'anyone', 'role': 'reader'}).execute()
        link = f'https://drive.google.com/file/d/{m["drive_id"]}/view'
    except Exception as e:
        link = f'(share failed: {str(e)[:60]})'
    links.append((n, m['doc'], m['pages'], link, dst))

json.dump(links, open('/tmp/manifest_34_links.json', 'w'), indent=1)
print(f'numbered copies in {OUT}:')
for n, doc, pages, link, dst in links:
    ok = os.path.exists(dst)
    print(f'{n:2d}. {doc} ({pages}pp) {"✅" if ok else "❌"} {link[:70]}')
