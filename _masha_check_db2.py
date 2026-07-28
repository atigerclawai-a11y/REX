#!/usr/bin/env python3
import sqlite3, json

db = '/Users/mainsobhelper/Desktop/REX/CC_bbg_contacts.db'
conn = sqlite3.connect(db)
c = conn.cursor()

result = {}
for table in ['contacts', 'conversations']:
    try:
        c.execute(f"PRAGMA table_info({table})")
        result[table] = [{'name': r[1], 'type': r[2]} for r in c.fetchall()]
    except:
        result[table] = 'not found'

if result.get('contacts'):
    cols = [r['name'] for r in result['contacts']]
    c.execute(f"SELECT {', '.join(cols)} FROM contacts WHERE tags LIKE '%owner.com%' ORDER BY rowid DESC LIMIT 15")
    result['owner_com_contacts'] = [dict(zip(cols, row)) for row in c.fetchall()]

conn.close()
print(json.dumps(result, indent=2, default=str))
