#!/usr/bin/env python3
"""Inspect recovery manifest structure."""
import json

mf = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json'
data = json.load(open(mf))
print(f'top type: {type(data).__name__}')
if isinstance(data, dict):
    for k, v in data.items():
        print(f'  {k}: {type(v).__name__} = {str(v)[:150]}')
elif isinstance(data, list):
    print(f'list len {len(data)}')
    for item in data[:5]:
        print(f'  {str(item)[:150]}')
