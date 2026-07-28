#!/usr/bin/env python3
"""BBG Payment Watchdog — runs every 5 min, silently reports only on changes."""
import json, os, sys
from pathlib import Path

RES_FILE = Path.home() / "Desktop/REX/CC_bbg_reservations.json"
CACHE_FILE = Path.home() / "Desktop/REX/.bbg_watch_cache.json"
TODAY = "2026-07-19"
DEPOSIT = 45

# Known Stripe payments (email -> amount, name)
STRIPE = {
    "maxikny@gmail.com": (540, "Max Goldenko"),
    "kirill.likovv@gmail.com": (225, "Kirill Likov"),
    "alexander.zhik@gmail.com": (225, "Alexander Zhik"),
    "stevenr303@gmail.com": (90, "Steven Reyser"),
    "benjaminwmourier@gmail.com": (180, "Benjamin Mourier"),
    "ednovo64@gmail.com": (540, "Edward Novogrudsky"),
    "valery013013@gmail.com": (360, "Valery Streltsov"),
    "cashcashwinnie@gmail.com": (135, "Ping"),
    "romanice9999@gmail.com": (90, "Roman Melnyk"),
    "bossangeles1@yahoo.com": (90, "Anjelika Boss"),
    "eleonorapankratova@gmail.com": (45, "Eleonora Pankratova"),
    "spivas@gmail.com": (315, "Vasile Spinei"),
    "anevryanskiy@gmail.com": (41, "Alex"),
    "kahany15@aim.com": (680, "N/A"),
    "jamiemichellecohen@gmail.com": (40, "Jamie Cohen"),
    "lucia_stein@yahoo.com": (15, "Lucia Stein"),
    "aquace4@yahoo.com": (106, "N/A"),
}

if not RES_FILE.exists():
    sys.exit(0)

with open(RES_FILE) as f:
    res = json.load(f)

today = [r for r in res if r.get('reservation_date') == TODAY]

# Count paid
paid_names = set()
for r in today:
    email = r.get('email', '')
    notes = r.get('notes', '')
    name = r.get('party_name', '')
    for semail, (amt, sname) in STRIPE.items():
        if email and semail.lower() in email.lower(): paid_names.add(name); break
        if semail.lower() in notes.lower(): paid_names.add(name); break
        uname = semail.split('@')[0].lower()
        for part in name.lower().split():
            if len(part) > 2 and part in uname: paid_names.add(name); break

total = len(today)
paid = len(paid_names)

# Compare with cache
prev = {"total": 0, "paid": 0}
if CACHE_FILE.exists():
    with open(CACHE_FILE) as f:
        prev = json.load(f)

with open(CACHE_FILE, 'w') as f:
    json.dump({"total": total, "paid": paid}, f)

# Only output if changed
if prev.get('total') == total and prev.get('paid') == paid:
    sys.exit(0)  # silent — no change

# Output
print(f"🏖️ BBG: {paid}/{total} PAID — {total - paid} UNPAID")
if total != prev.get('total', 0):
    diff = total - prev.get('total', 0)
    print(f"📋 {abs(diff)} new reservation{'s' if abs(diff)>1 else ''}" if diff>0 else f"📋 {abs(diff)} fewer reservation{'s' if abs(diff)>1 else ''}")
if paid != prev.get('paid', 0):
    diff = paid - prev.get('paid', 0)
    if diff > 0:
        print(f"🆕 {diff} NEW PAYMENT{'S' if diff>1 else ''}!")
