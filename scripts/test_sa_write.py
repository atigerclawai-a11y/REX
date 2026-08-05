#!/usr/bin/env python3
"""Check: is there a GOJ Change Log sheet? Can SA write to SIGN IN sheet?"""
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import warnings
warnings.filterwarnings('ignore')
import googleapiclient.discovery as disc
import CC_goj_change_log as ccl

svc = disc.build('drive', 'v3', credentials=ccl.get_creds(), cache_discovery=False)
sheets = disc.build('sheets', 'v4', credentials=ccl.get_creds(), cache_discovery=False)

# search for change log
try:
    r = svc.files().list(q="name contains 'Change Log' or name contains 'change log'",
                         fields='files(id,name,mimeType)').execute()
    print(f'Change Log files: {r.get("files", [])}')
except Exception as e:
    print(f'search failed: {e}')

# test write to SIGN IN sheet (append a test row then delete)
try:
    sid = '1ko7aVBhzLMngCuWmIZu'
    r = sheets.spreadsheets().values().append(
        spreadsheetId=sid, range='A1:A1', valueInputOption='RAW',
        body={'values': [['__sa_write_test__']]}).execute()
    print(f'SIGN IN write: OK {r.get("updates", {}).get("updatedCells")} cells')
    # clean up test row
    sheets.spreadsheets().values().clear(spreadsheetId=sid, range='A1:A1').execute()
    print('test row cleared')
except Exception as e:
    print(f'SIGN IN write FAILED: {e}')
