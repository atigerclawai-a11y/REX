#!/usr/bin/env python3
"""Check unreadable menu status: focr recovery, manifest, review queue."""
import json
import os
import sqlite3
import subprocess

print('=== focr recovery process ===')
r = subprocess.run(['pgrep', '-fl', 'focr'], capture_output=True, text=True)
print(r.stdout.strip() or 'NOT RUNNING')

print('\n=== recovery manifest ===')
mf = '/Users/mainsobhelper/Desktop/REX/.page_guard_recover.json'
if os.path.exists(mf):
    data = json.load(open(mf))
    docs = data if isinstance(data, list) else data.get('docs', [])
    print(f'{len(docs)} docs in manifest')

print('\n=== review queue ===')
p = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db')
try:
    q = p.execute("SELECT * FROM menu_review_queue WHERE status='pending'").fetchall()
    print(f'{len(q)} pending review items')
    for r in q[:10]:
        print(f'  {r[1]} ({r[2]}) [{r[5]}]')
except Exception as e:
    print(f'no review queue: {e}')

print('\n=== unreadable guesses status ===')
if os.path.exists('/tmp/unreadable_guesses.json'):
    g = json.load(open('/tmp/unreadable_guesses.json'))
    print(f'{len(g)} focr name guesses (from the 232-form sweep)')
print('\n=== quarantine dirs ===')
for d in ['/Users/mainsobhelper/Desktop/REX/menu_ocr_quarantine',
          '/Users/mainsobhelper/Desktop/REX/quarantine']:
    if os.path.isdir(d):
        files = os.listdir(d)
        print(f'{d}: {len(files)} files')
        for f in files[:6]:
            print(f'  {f}')
p.close()
