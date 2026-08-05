#!/usr/bin/env python3
"""Reactivate Kormov Feliks (active=0→1 per Carecenta Thu) + set TH=1.
Also assign canonical_id (1306) if missing."""
import sqlite3

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
a = sqlite3.connect(AUTH)

# check canonical id
n = a.execute("SELECT COUNT(*) FROM canonical_ids WHERE name='Kormov Feliks'").fetchone()[0]
if not n:
    mx = a.execute("SELECT MAX(CAST(canonical_id AS INTEGER)) FROM canonical_ids").fetchone()[0]
    new_id = str(mx + 1)
    a.execute("INSERT INTO canonical_ids (canonical_id, name, auth_id, prop_id) VALUES (?, 'Kormov Feliks', 590, NULL)", (new_id,))
    print(f'canonical_id {new_id} assigned')
else:
    print('canonical_id exists')

c = a.execute("UPDATE clients SET active=1, day_TH_actual=1 WHERE client_id=590")
print(f'Kormov Feliks: {c.rowcount} row — active=1, TH=1')
a.commit()

s1 = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=1").fetchone()[0]
s2 = a.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND day_TH_actual=2").fetchone()[0]
print(f'day_TH_actual now: {s1}/{s2} = {s1+s2} (Carecenta: 149)')
a.close()
