#!/usr/bin/env python3
"""Reconcile my extracted Tuesday roster vs the morning sync's hardcoded lists."""
import json
import re

src = open('/tmp/sync_final_live.py').read()
TUE_AM = re.search(r'TUE_AM = """(.*?)"""', src, re.S).group(1).split('|')
TUE_PM = re.search(r'TUE_PM = """(.*?)"""', src, re.S).group(1).split('|')
am = {x.strip().upper() for x in TUE_AM}
pm = {x.strip().upper() for x in TUE_PM}
print(f'morning-sync lists: AM={len(am)} PM={len(pm)}')

def_ = json.load(open('/tmp/tue_definitive.json'))
my_s1 = {n.upper() for n in def_['s1']}
my_s2 = {n.upper() for n in def_['s2']}
print(f'my extraction: S1={len(my_s1)} S2={len(my_s2)}')


def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))


am_n, pm_n = {norm(x) for x in am}, {norm(x) for x in pm}
s1_n, s2_n = {norm(x) for x in my_s1}, {norm(x) for x in my_s2}

print(f'\n--- S1: in morning-AM but NOT in my S1 ({len(am_n - s1_n)}) ---')
for x in sorted(am_n - s1_n):
    print(f'  {x}')
print(f'--- S1: in my S1 but NOT in morning-AM ({len(s1_n - am_n)}) ---')
for x in sorted(s1_n - am_n):
    print(f'  {x}')

print(f'\n--- S2: in morning-PM but NOT in my S2 ({len(pm_n - s2_n)}) ---')
for x in sorted(pm_n - s2_n):
    print(f'  {x}')
print(f'--- S2: in my S2 but NOT in morning-PM ({len(s2_n - pm_n)}) ---')
for x in sorted(s2_n - pm_n):
    print(f'  {x}')
