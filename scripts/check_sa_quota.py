#!/usr/bin/env python3
"""Check SA Drive quota + look for an existing GOJ Change Log sheet."""
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import warnings
warnings.filterwarnings('ignore')
import googleapiclient.discovery as disc
import CC_goj_change_log as ccl

svc = disc.build('drive', 'v3', credentials=ccl.get_creds(), cache_discovery=False)
try:
    q = svc.about().get(fields='storageQuota,user').execute()
    print(f'SA user: {q.get("user", {}).get("displayName")}')
    print(f'quota: {q.get("storageQuota")}')
except Exception as e:
    print(f'about failed: {e}')

# list files the SA can see
try:
    r = svc.files().list(fields='files(id,name,mimeType)', pageSize=50).execute()
    files = r.get('files', [])
    print(f'\nSA-visible files: {len(files)}')
    for f in files:
        print(f'  {f["name"]} ({f["mimeType"].split(".")[-1]}) {f["id"][:20]}')
except Exception as e:
    print(f'list failed: {e}')
