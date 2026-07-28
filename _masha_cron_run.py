#!/usr/bin/env python3
"""Masha reservation watcher — cron job. IMAP-based check of olympusbbg@gmail.com."""
import imaplib, email, json, sqlite3, os, re, ssl
from email.header import decode_header
from datetime import datetime, timezone, timedelta

REX_DIR = os.path.expanduser("~/Desktop/REX")
TALLY_PATH = os.path.join(REX_DIR, "bbg_reservation_tally.json")
DB_PATH = os.path.join(REX_DIR, "CC_bbg_contacts.db")
RELAY_PATH = os.path.join(REX_DIR, "masha_relay.json")

# olympusbbg@gmail.com forwards to atigerclawai@gmail.com — no separate IMAP needed.
# App Passwords unavailable on olympusbbg (account type restriction).
EMAIL_ADDR = "atigerclawai@gmail.com"
PASSWORD = "uxemapqvhkndgmsv"
IMAP_HOST = "imap.gmail.com"

RESERVATION_KEYWORDS = [
    "owner.com", "new reservation", "booking confirmed", "new booking",
    "reservation request", "table for", "booked at boardwalk",
    "reservations form submission", "boardwalk beer garden"
]

now = datetime.now(timezone.utc)
now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

# ── 1. Connect via IMAP ──────────────────────────────────────
ctx = ssl.create_default_context()
try:
    mail = imaplib.IMAP4_SSL(IMAP_HOST, 993, ssl_context=ctx, timeout=15)
    mail.login(EMAIL_ADDR, PASSWORD)
except imaplib.IMAP4.error:
    exit(0)

mail.select("INBOX")

# ── 2. Search for recent emails ──────────────────────────────
# Last 7 days
since_date = (now - timedelta(days=7)).strftime("%d-%b-%Y")
status, messages = mail.search(None, f'(SINCE "{since_date}")')
if status != "OK":
    mail.logout()
    exit(0)

msg_ids = messages[0].split()[-20:] if messages[0] else []
if not msg_ids:
    mail.logout()
    exit(0)

# ── 3. Fetch headers + body for scanning ─────────────────────
found_reservations = []

for mid in reversed(msg_ids):
    try:
        status, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date)] BODY.PEEK[TEXT])")
        if status != "OK":
            continue

        # Headers (first part)
        header_raw = data[0][1] if isinstance(data[0], tuple) and data[0][1] else b""
        msg = email.message_from_bytes(header_raw)
        from_addr = str(msg["From"] or "")
        subject_raw = msg["Subject"] or ""
        subject_parts = decode_header(subject_raw)
        subject = ""
        for part, enc in subject_parts:
            if isinstance(part, bytes):
                subject += part.decode(enc or "utf-8", errors="replace")
            else:
                subject += str(part)
        date_str = str(msg["Date"] or "")

        # Body (second part)
        body_text = ""
        if len(data) > 1 and isinstance(data[1], tuple) and data[1][1]:
            try:
                body_text = data[1][1].decode("utf-8", errors="replace")
            except:
                body_text = str(data[1][1][:500])

        # Combined for keyword scan
        combined = f"{subject} {body_text[:2000]} {from_addr}".lower()

        is_reservation = False
        for kw in RESERVATION_KEYWORDS:
            if kw.lower() in combined:
                is_reservation = True
                break

        if is_reservation:
            found_reservations.append({
                "id": mid.decode(),
                "from": from_addr,
                "subject": subject,
                "date": date_str,
                "body": body_text,
            })
    except Exception as e:
        continue

mail.logout()

# ── 4. If no reservations found, exit silently ───────────────
if not found_reservations:
    exit(0)

# ── 5. Extract reservation details ───────────────────────────
extracted = []

for r in found_reservations:
    body = r["body"]
    subject = r["subject"]
    full_text = f"{subject}\n{body}"

    # Try to extract: name, date, guests, phone, email
    name = ""
    guests = 0
    date_str_found = ""
    phone = ""
    email_addr = ""

    # --- Parse owner.com format ---
    # Pattern 1: "Name: First Last" or "Name:  First Last"
    name_matches = re.findall(r'(?:Name|Guest Name|Customer)[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)', full_text)
    if name_matches:
        name = name_matches[0].strip()

    # Pattern 2: Date: MM/DD/YYYY or Month DD, YYYY or YYYY-MM-DD
    date_patterns = [
        r'(?:Date|Reservation Date|When)[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
        r'(?:Date|Reservation Date|When)[:\s]+([A-Z][a-z]+ \d{1,2},? \d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'([A-Z][a-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4})',
    ]
    for pat in date_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            date_str_found = m.group(1)
            break

    # Pattern 3: Guests / Party size
    guest_patterns = [
        r'(?:Guests|Party Size|Number of Guests|Party of|Table for|Guest Count)[:\s]+(\d+)',
        r'(\d+)\s*(?:guests|people|persons|ppl)',
        r'party\s*(?:of|size)?\s*(\d+)',
    ]
    for pat in guest_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            guests = int(m.group(1))
            break

    # Pattern 4: Phone
    phone_match = re.search(r'(?:Phone|Telephone|Tel|Mobile)[:\s#]*\s*([\+\d][\d\s\-\(\)\.\*]{6,})', full_text, re.IGNORECASE)
    if not phone_match:
        # Owner.com forwarded format: ": +164****1796" on its own line
        phone_match = re.search(r'^:\s*(\+?[\d\*]+[-\d\*]*)\s*$', full_text, re.MULTILINE)
    if phone_match:
        phone = phone_match.group(1).strip()

    # Pattern 5: Email
    email_match = re.search(r'(?:Email|E-mail)[:\s]*\s*([\w\.\+\-]+@[\w\.\-]+\.\w+)', full_text, re.IGNORECASE)
    if not email_match:
        # Owner.com forwarded format: ": user@domain.com" on its own line
        email_match = re.search(r'^:\s*([\w\.\+\-]+@[\w\.\-]+\.\w{2,})\s*$', full_text, re.MULTILINE)
    if email_match:
        email_addr = email_match.group(1).strip()

    # Fallback: look for any email in the body
    if not email_addr:
        email_match2 = re.search(r'([\w\.\+\-]+@[\w\.\-]+\.\w{2,})', body)
        if email_match2 and "owner.com" not in email_match2.group(1):
            email_addr = email_match2.group(1).strip()

    # If date not found in body, extract from subject or try to parse from email date
    if not date_str_found:
        # Try "July 4" type patterns
        m = re.search(r'(?:on\s+)?([A-Z][a-z]+ \d{1,2}(?:st|nd|rd|th)?)', body)
        if m:
            date_str_found = m.group(1).strip()

    # Normalize date to YYYY-MM-DD
    normalized_date = ""
    if date_str_found:
        for fmt in ["%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%Y-%m-%d", "%B %d", "%b %d, %Y", "%b %d %Y"]:
            try:
                if fmt in ("%B %d",):
                    # Add current year
                    dt = datetime.strptime(date_str_found.strip(","), fmt)
                    dt = dt.replace(year=now.year)
                    if dt < now:
                        dt = dt.replace(year=now.year + 1)
                    normalized_date = dt.strftime("%Y-%m-%d")
                else:
                    dt = datetime.strptime(date_str_found.strip(","), fmt)
                    normalized_date = dt.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    if not normalized_date:
        continue  # Skip if we can't get a date

    # If no name, use "Guest"
    if not name:
        name = "Guest"

    # If no guest count, default to 2
    if guests == 0:
        guests = 2

    extracted.append({
        "name": name.strip(),
        "date": normalized_date,
        "guests": guests,
        "phone": phone,
        "email": email_addr,
        "notes": subject.strip()[:200],
    })

if not extracted:
    exit(0)

# ── 6. Check against existing DB for duplicates ──────────────
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Ensure tables exist
cur.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        email TEXT,
        notes TEXT,
        tags TEXT DEFAULT '',
        source TEXT DEFAULT 'manual',
        first_name TEXT,
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

new_bookings = []
new_contacts_count = 0

for r in extracted:
    # Check for duplicate: same date+name+party size
    cur.execute("""
        SELECT c.id FROM contacts c 
        JOIN conversations cv ON cv.contact_id = c.id
        WHERE cv.body LIKE ? AND c.name = ? AND cv.body LIKE ?
    """, (f"%{r['date']}%", r['name'], f"%party of {r['guests']}%"))
    
    if cur.fetchone():
        continue  # Duplicate, skip

    # Find or create contact
    contact_id = None
    if r["email"]:
        cur.execute("SELECT id FROM contacts WHERE email = ?", (r["email"],))
        row = cur.fetchone()
        if row:
            contact_id = row[0]
    if not contact_id and r["phone"]:
        cur.execute("SELECT id FROM contacts WHERE phone LIKE ?", (f"%{r['phone'][-10:]}%",))
        row = cur.fetchone()
        if row:
            contact_id = row[0]
    if not contact_id:
        cur.execute("SELECT id FROM contacts WHERE name = ?", (r["name"],))
        row = cur.fetchone()
        if row:
            contact_id = row[0]

    if not contact_id:
        tags = json.dumps(["owner.com"])
        cur.execute("""
            INSERT INTO contacts (name, phone, email, tags, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (r["name"], r["phone"] if r["phone"] else None, 
              r["email"] if r["email"] else None, tags, "owner.com", now_str))
        contact_id = cur.lastrowid
        new_contacts_count += 1

    # Insert conversation
    date_display = datetime.strptime(r["date"], "%Y-%m-%d").strftime("%B %d, %Y")
    body = f"Reservation: {date_display}, party of {r['guests']}, Name: {r['name']}"
    if r.get("notes"):
        body += f", Notes: {r['notes'][:100]}"

    cur.execute("""
        INSERT INTO conversations (contact_id, channel, direction, body, created_at)
        VALUES (?, 'walk_in', 'inbound', ?, ?)
    """, (contact_id, body, now_str))

    new_bookings.append(r)

conn.commit()

# ── 7. Recalculate tally from ALL conversations ──────────────
cur.execute("""
    SELECT body FROM conversations 
    WHERE channel = 'walk_in' AND body LIKE 'Reservation:%'
""")
all_convs = cur.fetchall()
conn.close()

with open(TALLY_PATH) as f:
    tally = json.load(f)

tally["days"] = {}

for (body,) in all_convs:
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

with open(TALLY_PATH, "w") as f:
    json.dump(tally, f, indent=2)

# ── 8. Update relay ──────────────────────────────────────────
if os.path.exists(RELAY_PATH):
    with open(RELAY_PATH) as f:
        relay = json.load(f)
else:
    relay = {"pending": [], "responses": [], "delivered": [], "history": []}

# Today's tally
today_str = now.strftime("%Y-%m-%d")
today_data = tally["days"].get(today_str, {"bookings": 0, "guests": 0})

# Week total (Mon-Sun)
week_start = now - timedelta(days=now.weekday())
week_bookings = 0
week_guests = 0
for d in range(7):
    day_key = (week_start + timedelta(days=d)).strftime("%Y-%m-%d")
    dd = tally["days"].get(day_key, {"bookings": 0, "guests": 0})
    week_bookings += dd["bookings"]
    week_guests += dd["guests"]

# Build message
new_names = [b["name"] for b in new_bookings]
names_str = ", ".join(new_names[:3])
if len(new_names) > 3:
    names_str += f" +{len(new_names)-3} more"

message_text = (
    f"📋 New Owner.com booking(s) — {names_str}. "
    f"Today: {today_data['bookings']} bookings / {today_data['guests']} guests. "
    f"Week total ({week_start.strftime('%b %d')}–{now.strftime('%b %d')}): "
    f"{week_bookings} bookings / {week_guests} guests."
)

new_entry = {
    "from": "masha",
    "message": message_text,
    "timestamp": now_str,
    "needs_confirmation": False,
    "delivered_at": now_str,
}

# Move old delivered to history
cutoff = now - timedelta(hours=24)
cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
if "history" not in relay:
    relay["history"] = []
kept_delivered = []
for entry in relay.get("delivered", []):
    ts = entry.get("delivered_at", entry.get("timestamp", ""))
    if ts < cutoff_str:
        relay["history"].append(entry)
    else:
        kept_delivered.append(entry)

kept_delivered.append(new_entry)
relay["delivered"] = kept_delivered[-4:]
relay["pending"] = []
relay["responses"] = []
relay["last_read_by_hermes"] = now_str

with open(RELAY_PATH, "w") as f:
    json.dump(relay, f, indent=2)

# ── 9. Print results ─────────────────────────────────────────
print(f"=== MASHA CRON RUN ===")
print(f"Scanned: {len(found_reservations)} reservation emails in inbox")
print(f"New bookings extracted: {len(new_bookings)}")
print(f"New contacts saved: {new_contacts_count}")
print(f"Today ({today_str}): {today_data['bookings']} bookings / {today_data['guests']} guests")
print(f"Week total: {week_bookings} bookings / {week_guests} guests")
print()
for b in new_bookings:
    print(f"  ✅ {b['name']} — {b['date']}, party of {b['guests']}" + 
          (f", {b['phone']}" if b['phone'] else "") + 
          (f", {b['email']}" if b['email'] else ""))
print()
print("Message for Kato:")
print(message_text)
