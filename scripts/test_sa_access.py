#!/usr/bin/env python3
"""Test: can the SA access the existing GOJ Change Log sheet?"""
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import json
import warnings
warnings.filterwarnings('ignore')
import googleapiclient.discovery as disc
import CC_goj_change_log as ccl

svc = disc.build('drive', 'v3', credentials=ccl.get_creds(), cache_discovery=False)
sid = '1RXS14JetSXYPZiIpwayfKrUlrLI1TTpcWujmltA0Qy0'
try:
    f = svc.files().get(fileId=sid, fields='id,name').execute()
    print(f'ACCESS OK: {f}')
except Exception as e:
    print(f'ACCESS FAILED: {e}')
    # try creating a tiny test file to confirm quota issue
    try:
        meta = {'name': 'quota_test', 'mimeType': 'application/vnd.google-apps.spreadsheet'}
        f2 = svc.files().create(body=meta, fields='id').execute()
        print(f'CREATE OK: {f2}')
        svc.files().delete(fileId=f2['id']).execute()
        print('cleaned up')
    except Exception as e2:
        print(f'CREATE ALSO FAILED: {e2}')
