#!/usr/bin/env python3
"""Check: imessage_intel.db exists? state file? what does fetch_messages return?"""
import os
import json
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import CC_goj_change_log as ccl

db = ccl.DB_PATH
print(f'DB exists: {os.path.exists(db)}')
st = ccl.STATE_PATH
print(f'state exists: {os.path.exists(st)}')
if os.path.exists(st):
    print(f'state: {open(st).read()[:200]}')

if os.path.exists(db):
    rows = ccl.fetch_messages(14)
    print(f'fetch_messages(14): {len(rows)} rows')
    for r in rows[:5]:
        print(f'  [{r["received_at"][:16]}] {r["group_name"]}: {r["text"][:60]}')
