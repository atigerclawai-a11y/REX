#!/usr/bin/env python3
"""Final verification: auth day_W_actual roster vs LIVE Carecenta captured roster."""
import json
import re
import sqlite3

# Live roster captured from Carecenta sign-in page (AM/PM filters)
live = json.load(open('/tmp/wednesday_live_roster.json'))
live_am = {n.upper() for n in live['am']}
live_pm = {n.upper() for n in live['pm']}

# Definitive schedule-time roster
def_ = json.load(open('/tmp/wed_definitive.json'))
def_s1 = {n.upper() for n in def_['s1']}
def_s2 = {n.upper() for n in def_['s2']}

# Auth day_W_actual
a = sqlite3.connect('/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db')
auth_s1 = {r[0].upper() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=1")}
auth_s2 = {r[0].upper() for r in a.execute("SELECT name FROM clients WHERE active=1 AND day_W_actual=2")}
a.close()


def norm(n):
    return ' '.join(sorted(re.sub(r'[^A-Z\'\- ]', '', n.upper()).split()))


def report(tag, src, ref):
    src_n = {norm(x) for x in src}
    ref_n = {norm(x) for x in ref}
    only_src = sorted(src_n - ref_n)
    only_ref = sorted(ref_n - src_n)
    print(f'{tag}: {len(src)} vs ref {len(ref)} | only-in-src={len(only_src)} only-in-ref={len(only_ref)}')
    if only_src[:6]:
        print(f'   only-in-src: {only_src[:6]}')
    if only_ref[:6]:
        print(f'   only-in-ref: {only_ref[:6]}')


report('S1 auth vs live-AM', auth_s1, live_am)
report('S2 auth vs live-PM', auth_s2, live_pm)
report('S1 auth vs def-times', auth_s1, def_s1)
report('S2 auth vs def-times', auth_s2, def_s2)
