#!/usr/bin/env python3
"""Verify all 34 manifest files exist + check file sizes."""
import json
import os

docs = json.load(open('/tmp/manifest_34.json'))
print(f'{len(docs)} docs:')
all_exist = True
for i, (docname, pages, path) in enumerate(docs, 1):
    exists = os.path.exists(path)
    sz = os.path.getsize(path) // 1024 if exists else 0
    if not exists:
        all_exist = False
    print(f'{i:2d}. {docname} ({pages}pp): {"✅" if exists else "❌ MISSING"} {sz} KB')
print(f'\nall exist: {all_exist}')
