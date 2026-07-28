#!/usr/bin/env python3
"""Process owner.com reservations: update tally, save contacts, update relay."""
import json
import sqlite3
import os
from datetime import datetime, timezone, timedelta

REX_DIR = os.path.expanduser("~/Desktop/REX")
TALLY_PATH = os.path.join(REX_DIR, "bbg_reservation_tally.json")
DB_PATH = os.path.join(REX_DIR, "CC_bbg_contacts.db")
RELAY_PATH = os.path.join(REX_DIR, "masha_relay.json")

# Reservation data extracted from emails (date is the RESERVATION date, not submission date)
reservations = [
    {"name": "Andy kremen", "email": "k94andy213@gmail.com", "phone": "+171****3994", "date": "2026-06-19", "guests": 5, "notes": ""},
    {"name": "Alberto Landaverde", "email": "goldenkoala2013@gmail.com", "phone": "+155****8316", "date": "2026-06-19", "guests": 3, "notes": ""},
    {"name": "Alessandra Miller", "email": "alessandra.anne.smith@gmail.com", "phone": "+131****9448", "date": "2026-06-20", "guests": 3, "notes": ""},
    {"name": "Julia", "email": "jkolchina@gmail.com", "phone": "+134****6804", "date": "2026-06-27", "guests": 4, "notes": ""},
    {"name": "Muhammad Shakur", "email": "mshakur0719@gmail.com", "phone": "+164****6785", "date": "2026-06-22", "guests": 2, "notes": ""},
    {"name": "Rutherford T Mbele", "email": "rudimbele@yahoo.com", "phone": "+134****5664", "date": "2026-06-24", "guests": 2, "notes": "South Korea vs South Africa, 8pm"},
]

now = datetime.now(timezone.utc)
now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

# --- 1. Read existing tally ---
with open(TALLY_PATH) as f:
    tally = json.load(f)

# --- 2. Update tally for each date ---
for r in reservations:
    day = r["date"]
    if day not in tally["days"]:
        tally["days"][day] = {"bookings": 0, "guests": 0}
    # Note: We don't increment blindly - check if this specific reservation is new
    # For now, tally represents ALL reservations for each date
    # We'll track new vs existing separately below

tally["last_updated"] = now_str

# --- 3. Check DB for duplicates and insert new contacts ---
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Ensure tables exist
cur.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        phone TEXT,
        email TEXT,
        tags TEXT,
        source TEXT,
        created_at TEXT
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id INTEGER,
        channel TEXT,
        direction TEXT,
        body TEXT,
        created_at TEXT
    )
""")

new_contacts = 0
new_bookings = []
existing_bookings = []

for r in reservations:
    # Check for duplicate: same date+name+party size already in conversations
    cur.execute("""
        SELECT c.id FROM conversations c 
        JOIN contacts co ON c.contact_id = co.id 
        WHERE c.body LIKE ? AND co.name = ?
    """, (f"%{r['date']}%party of {r['guests']}%Name: {r['name']}%", r["name"]))
    
    existing = cur.fetchone()
    
    if existing:
        existing_bookings.append(r)
        continue
    
    # Check if contact exists by name+email
    cur.execute("SELECT id FROM contacts WHERE name = ? AND email = ?", (r["name"], r["email"]))
    contact = cur.fetchone()
    
    if not contact:
        # Insert new contact
        tags = json.dumps(["owner.com"])
        cur.execute("""
            INSERT INTO contacts (name, phone, email, tags, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (r["name"], r["phone"], r["email"], tags, "owner.com", now_str))
        contact_id = cur.lastrowid
        new_contacts += 1
    else:
        contact_id = contact[0]
    
    # Insert conversation record
    date_display = datetime.strptime(r["date"], "%Y-%m-%d").strftime("%B %d, %Y")
    body = f"Reservation: {date_display}, party of {r['guests']}, Name: {r['name']}"
    if r["notes"]:
        body += f", Notes: {r['notes']}"
    
    cur.execute("""
        INSERT INTO conversations (contact_id, channel, direction, body, created_at)
        VALUES (?, 'walk_in', 'inbound', ?, ?)
    """, (contact_id, body, now_str))
    
    new_bookings.append(r)

conn.commit()
conn.close()

# --- 4. Recalculate tally based on all reservations in DB ---
# Actually, let's recalc tally from the DB conversations
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Get all reservations with dates
cur.execute("""
    SELECT c.body, c.created_at FROM conversations c 
    WHERE c.channel = 'walk_in' AND c.body LIKE 'Reservation:%'
""")
all_convs = cur.fetchall()
conn.close()

# Reset tally
tally["days"] = {}

for body, _ in all_convs:
    # Parse body: "Reservation: June 19, 2026, party of 5, Name: Andy kremen"
    import re
    m = re.match(r"Reservation: (\w+ \d+, \d{4}), party of (\d+)", body)
    if m:
        date_str = m.group(1)
        guests = int(m.group(2))
        dt = datetime.strptime(date_str, "%B %d, %Y")
        day = dt.strftime("%Y-%m-%d")
        if day not in tally["days"]:
            tally["days"][day] = {"bookings": 0, "guests": 0}
        tally["days"][day]["bookings"] += 1
        tally["days"][day]["guests"] += guests

tally["last_updated"] = now_str

# Write tally
with open(TALLY_PATH, "w") as f:
    json.dump(tally, f, indent=2)

# --- 5. Update relay ---
# Read current relay
if os.path.exists(RELAY_PATH):
    with open(RELAY_PATH) as f:
        relay = json.load(f)
else:
    relay = {"pending": [], "responses": [], "delivered": [], "history": []}

# Calculate today's tally
today_str = now.strftime("%Y-%m-%d")
today_data = tally["days"].get(today_str, {"bookings": 0, "guests": 0})

# Calculate week total (Mon-Sun of current week)
week_start = now - timedelta(days=now.weekday())  # Monday
week_start_str = week_start.strftime("%Y-%m-%d")
week_bookings = 0
week_guests = 0
for d in range(7):
    day_key = (week_start + timedelta(days=d)).strftime("%Y-%m-%d")
    dd = tally["days"].get(day_key, {"bookings": 0, "guests": 0})
    week_bookings += dd["bookings"]
    week_guests += dd["guests"]

# Build message
summary_parts = []
if new_bookings:
    summary_parts.append(f"Found {len(new_bookings)} new Owner.com bookings")
else:
    summary_parts.append(f"No new bookings (all {len(reservations)} already processed)")

summary_parts.append(f"Today's tally: {today_data['bookings']} bookings / {today_data['guests']} guests")
summary_parts.append(f"New contacts saved: {new_contacts}")
summary_parts.append(f"Week total (Mon-Sun): {week_bookings} bookings / {week_guests} guests")

message_text = "📋 " + " | ".join(summary_parts)

# New delivered entry
new_entry = {
    "from": "masha",
    "message": message_text,
    "timestamp": now_str,
    "needs_confirmation": False,
    "delivered_at": now_str,
}

# Move old delivered entries to history (older than 24h) and keep most recent 3 + new
cutoff = now - timedelta(hours=24)
cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

if "history" not in relay:
    relay["history"] = []

# Move old entries to history
kept_delivered = []
for entry in relay.get("delivered", []):
    ts = entry.get("delivered_at", entry.get("timestamp", ""))
    if ts < cutoff_str:
        relay["history"].append(entry)
    else:
        kept_delivered.append(entry)

# Keep most recent 3 + new one
kept_delivered.append(new_entry)
relay["delivered"] = kept_delivered[-4:]  # Keep at most 4 (3 old + 1 new)

# Clear pending
relay["pending"] = []
relay["responses"] = []
relay["last_read_by_hermes"] = now_str

with open(RELAY_PATH, "w") as f:
    json.dump(relay, f, indent=2)

# --- Print summary ---
print(f"=== MASHA RESERVATION WATCHER ===")
print(f"Emails scanned: {len(reservations)}")
print(f"New bookings: {len(new_bookings)}")
print(f"Already processed: {len(existing_bookings)}")
print(f"New contacts saved: {new_contacts}")
print(f"Today ({today_str}): {today_data['bookings']} bookings / {today_data['guests']} guests")
print(f"Week total: {week_bookings} bookings / {week_guests} guests")
print(f"Tally updated: {TALLY_PATH}")
print(f"Relay updated: {RELAY_PATH}")
print()
print("New bookings:")
for b in new_bookings:
    print(f"  - {b['name']} ({b['date']}, party of {b['guests']})")
print()
print("Already processed:")
for b in existing_bookings:
    print(f"  - {b['name']} ({b['date']}, party of {b['guests']})")
