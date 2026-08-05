#!/usr/bin/env python3
"""Test the exact orders lookup the generator does for Tuesday."""
import json

p = '/Users/mainsobhelper/Documents/goj files/data/GOJ_Menu_Orders.json'
data = json.load(open(p))
print(f'has 2026-08-04: {"2026-08-04" in data}')
day = data.get('2026-08-04', {})
print(f'entries: {len(day)}')
# simulate build_menu_clients for shift 1
count1 = count2 = 0
for name, co in day.items():
    if co.get('1') or co.get('S1'):
        count1 += 1
    if co.get('2') or co.get('S2'):
        count2 += 1
print(f'orders with shift-1 key: {count1}, shift-2 key: {count2}')

# check key types — maybe shift keys are ints not strings?
for name, co in list(day.items())[:3]:
    print(f'  {name}: keys={list(co.keys())} sample={str(co)[:80]}')
