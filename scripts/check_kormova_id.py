#!/usr/bin/env python3
"""Kormova Lyubov: check canonical_ids + assign a free 4-digit ID if missing."""
import sqlite3

a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
print('=== Kormova in clients ===')
for r in a.execute("SELECT client_id, name, active FROM clients WHERE name LIKE '%Kormova%'"):
    print(f'  {r}')

print('\n=== Kormova in canonical_ids ===')
for r in a.execute("SELECT * FROM canonical_ids WHERE name LIKE '%Kormova%'"):
    print(f'  {r}')

# find max canonical id to allocate next
mx = a.execute("SELECT MAX(CAST(canonical_id AS INTEGER)) FROM canonical_ids").fetchone()[0]
print(f'\nmax canonical_id: {mx}')
print(f'count: {a.execute("SELECT COUNT(*) FROM canonical_ids").fetchone()[0]}')
a.close()
