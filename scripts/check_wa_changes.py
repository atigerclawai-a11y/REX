#!/usr/bin/env python3
"""Check: (a) were Polyak/Kravets Sima removed from Tue sheets?
(b) WhatsApp bridge recent messages about day changes."""
import json
import sqlite3
import urllib.request

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
a = sqlite3.connect(AUTH)
print('=== attendance check for today''s no-shows ===')
for name in ['Polyak', 'Kravets Sima', 'Kravets']:
    for row in a.execute("SELECT name, active, day_T_actual FROM clients WHERE name LIKE ?", (f'%{name}%',)):
        print(f'  {row}')

print('\n=== WhatsApp bridge recent messages (last 30) ===')
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/api/messages?limit=30', timeout=10) as r:
        data = json.loads(r.read().decode())
    msgs = data if isinstance(data, list) else data.get('messages', data.get('data', []))
    for m in msgs[-30:]:
        ts = m.get('timestamp', m.get('time', ''))[:16]
        text = (m.get('body') or m.get('text') or m.get('message') or '')[:140]
        if text:
            print(f'  [{ts}] {text}')
except Exception as e:
    print(f'  bridge query failed: {e}')
a.close()
