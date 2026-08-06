#!/usr/bin/env python3
"""Verify backup files + check doc006889 (the one that showed 0 names earlier)."""
import json
import os

B = '/Users/mainsobhelper/Desktop/REX/attendance_backups'
for f in sorted(os.listdir(B)):
    p = os.path.join(B, f)
    sz = os.path.getsize(p)
    if f.endswith('.json'):
        d = json.load(open(p))
        print(f'{f}: {d["name_count"]} names ({sz} bytes)')
    else:
        print(f'{f}: {sz} bytes')
