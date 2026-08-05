#!/usr/bin/env python3
"""Map all 34 manifest docs to their Google Drive file IDs (SA can see them)."""
import json
import os
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import warnings
warnings.filterwarnings('ignore')
import googleapiclient.discovery as disc
import CC_goj_change_log as ccl

svc = disc.build('drive', 'v3', credentials=ccl.get_creds(), cache_discovery=False)

docs = json.load(open('/tmp/manifest_34.json'))

# get all SA-visible files
files = {}
page = None
while True:
    q = svc.files().list(pageSize=1000, pageToken=page,
                         fields='files(id,name),nextPageToken').execute()
    for f in q.get('files', []):
        files[f['name']] = f['id']
    page = q.get('nextPageToken')
    if not page:
        break
print(f'SA sees {len(files)} files')

# map each doc by its full filename (doc + timestamp)
mapping = []
for i, (docname, pages, path) in enumerate(docs, 1):
    base = os.path.basename(path) if path else f'{docname}.pdf'
    # also try docname.pdf
    fid = files.get(base) or files.get(f'{docname}.pdf')
    if not fid:
        # try partial match on doc number
        num = docname.split('_')[0]
        for name, id_ in files.items():
            if num in name:
                fid = id_
                break
    mapping.append({'n': i, 'doc': docname, 'pages': pages, 'drive_id': fid or None,
                    'file': base})

json.dump(mapping, open('/tmp/manifest_34_drive.json', 'w'), indent=1)
missing = [m for m in mapping if not m['drive_id']]
print(f'mapped: {len(mapping)-len(missing)}/34, missing: {len(missing)}')
for m in missing:
    print(f'  MISSING: #{m["n"]} {m["doc"]} ({m["file"]})')
