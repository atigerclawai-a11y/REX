#!/usr/bin/env python3
import sqlite3, json

db = '/Users/mainsobhelper/Desktop/REX/CC_bbg_contacts.db'
conn = sqlite3.connect(db)
c = conn.cursor()

# Get tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]

result = {'tables': tables}

if 'contacts' in tables:
    c.execute("SELECT COUNT(*) FROM contacts WHERE tags LIKE ?", ('%owner.com%',))
    result['owner_com_count'] = c.fetchone()[0]
    c.execute("SELECT first_name, email, phone, created_at FROM contacts WHERE tags LIKE ? ORDER BY created_at DESC LIMIT 15", ('%owner.com%',))
    result['recent'] = [{'name': r[0], 'email': r[1], 'phone': r[2], 'created': r[3]} for r in c.fetchall()]

conn.close()
print(json.dumps(result, indent=2))
