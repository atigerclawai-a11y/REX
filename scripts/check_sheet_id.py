#!/usr/bin/env python3
"""Check change_log_sheet_id.txt + try to access the existing sheet."""
import os

p = '/Users/mainsobhelper/Desktop/REX/data/change_log_sheet_id.txt'
print(f'sheet id file exists: {os.path.exists(p)}')
if os.path.exists(p):
    sid = open(p).read().strip()
    print(f'sheet id: {sid}')
else:
    print('NO SHEET ID — will try to create (quota exceeded!)')
    print('fix: use an existing sheet or clear the SA quota')
