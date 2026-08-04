#!/usr/bin/env python3
"""Full inventory sweep: search ALL name crops for the 22 surnames (fuzzy)."""
import json
import re
import sqlite3
from pathlib import Path

names22 = ['Bolotin Marina', 'Dovgalyuk Zelda', 'Gamkrelidze Mikhail', 'Krayz Raisa',
           'Lazovskiy Lina', 'Lazovskiy Valeriy', 'Matanseva Ofelia', 'Mikhaylova Sofiya',
           'Minogina Ninel', 'Nikolaeva Galina', 'Safonov Anatoliy', 'Sekh Stefaniia',
           'Shadkhan Bella', 'Shkolnik Betya', 'Shteyman Faina', 'Shumaeva Anna',
           'Shvayko Nelli', 'Umanskaya Yelena', 'Volov Boris', 'Yermakov Marat',
           'Zabizhin Grigoriy', 'Zhelabovska Nadia']
surnames = {n.split()[0].lower() for n in names22}

# unreadable guesses (focr read names for 190/232)
guesses = json.load(open('/tmp/unreadable_guesses.json'))
hits = []
for k, v in guesses.items():
    nm = v.get('name', '') if isinstance(v, dict) else ''
    if nm and nm.split() and nm.split()[0].lower() in surnames:
        hits.append((nm, k, v.get('doc', '')))
print('unreadable_guesses hits:')
for h in hits:
    print(f'  {h}')

# also the full manifest
um = json.load(open('/tmp/unreadable_full_manifest.json'))
hits2 = []
for r in um:
    nm = r.get('name', '') or ''
    if nm.split() and nm.split()[0].lower() in surnames:
        hits2.append((nm, r.get('n'), str(r.get('doc'))[:24], r.get('page')))
print(f'\nmanifest hits ({len(hits2)}):')
for h in hits2:
    print(f'  {h}')
