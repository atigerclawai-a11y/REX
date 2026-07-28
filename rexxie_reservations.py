#!/usr/bin/env python3
"""Rexxie reservation base — watches Gmail for forwarded reservations, parses them,
stores in SQLite, ready for Rexxie to query.

Usage:
  python3 rexxie_reservations.py                     # one-shot: check inbox, parse new
  python3 rexxie_reservations.py --watch              # daemon: poll every 60s
  python3 rexxie_reservations.py --query "next week"  # search reservations

Setup:
  1. Forward reservation emails to atigerclawai@gmail.com
  2. Create Gmail filter: if subject contains "[RESV]" → apply label "Reservations"
  3. Or use Gmail's plus addressing: rexxie+tigerclaw@gmail.com (still goes to same inbox)
"""

import imaplib, email, json, ssl, sqlite3, re, sys, time, os
from email import policy
from datetime import datetime, timedelta
from pathlib import Path

DB = Path.home() / "Desktop/REX/rexxie_reservations.db"
CREDS = Path.home() / ".rex_gmail_imap.json"
LABEL = "Reservations"  # Gmail label to watch

def init_db():
    db = sqlite3.connect(str(DB))
    db.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY,
            source_email TEXT,
            subject TEXT,
            date_received TEXT,
            reservation_date TEXT,
            reservation_time TEXT,
            venue TEXT,
            party_size INTEGER,
            confirmation TEXT,
            raw_body TEXT,
            parsed BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS processed_emails (
            email_uid TEXT PRIMARY KEY,
            processed_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.commit()
    return db

def connect_imap():
    cfg = json.loads(CREDS.read_text())
    ctx = ssl.create_default_context()
    mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], ssl_context=ctx, timeout=15)
    mail.login(cfg["email"], cfg["app_password"])
    return mail

def parse_reservation(text, subject):
    """Extract reservation details from email body. Handles common formats."""
    result = {
        "reservation_date": None,
        "reservation_time": None,
        "venue": None,
        "party_size": None,
        "confirmation": None,
    }

    # Date patterns: "July 15, 2026", "07/15/2026", "15 Jul 2026", "Monday, July 15"
    date_patterns = [
        r'(?:Date|When|Reservation\s+for)[:\s]*([A-Z][a-z]+ \d{1,2},?\s*\d{4})',
        r'(?:Date|When|Reservation\s+for)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})',
        r'([A-Z][a-z]+day,?\s+[A-Z][a-z]+\s+\d{1,2})',
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["reservation_date"] = m.group(1)
            break

    # Time patterns: "7:00 PM", "19:00", "7pm"
    time_patterns = [
        r'(?:Time|at)[:\s]*(\d{1,2}:\d{2}\s*(?:AM|PM))',
        r'(\d{1,2}:\d{2}\s*(?:AM|PM))',
        r'(\d{1,2}\s*(?:AM|PM))',
    ]
    for pat in time_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["reservation_time"] = m.group(1)
            break

    # Venue: "at [Restaurant Name]", "Location: X"
    venue_patterns = [
        r'at\s+([A-Z][A-Za-z\s&]+?)(?:,|\.|\s+on|\s+for|\s+Date|\s+Time|\s+Confirmation|\s+\d)',
        r'(?:Venue|Restaurant|Location)[:\s]+([A-Z][A-Za-z\s&]+?)(?:,|\.|\n)',
    ]
    for pat in venue_patterns:
        m = re.search(pat, text)
        if m and len(m.group(1).strip()) > 3:
            result["venue"] = m.group(1).strip()
            break

    # Party size: "2 guests", "party of 4", "Table for 2"
    size_pat = r'(?:for|party of|table for|(\d+)\s*(?:guests|people|persons))'
    m = re.search(r'(\d+)\s*(?:guests?|people|persons|pax)', text, re.IGNORECASE)
    if m:
        result["party_size"] = int(m.group(1))
    else:
        m = re.search(r'(?:party of|table for|for)\s*(\d+)', text, re.IGNORECASE)
        if m:
            result["party_size"] = int(m.group(1))

    # Confirmation number
    conf_pat = r'(?:Confirmation|Conf#|Ref#?|Booking\s*ID)[:\s#]*([A-Z0-9]{4,20})'
    m = re.search(conf_pat, text, re.IGNORECASE)
    if m:
        result["confirmation"] = m.group(1)

    return result

def process_email(db, uid, msg):
    """Parse one email and store if it looks like a reservation."""
    uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)

    # Skip already processed
    if db.execute("SELECT 1 FROM processed_emails WHERE email_uid=?", (uid_str,)).fetchone():
        return None

    subject = str(msg["Subject"] or "")
    date_str = str(msg["Date"] or "")

    # Get body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode(errors="replace") + "\n"
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors="replace")
        except Exception:
            pass

    full_text = subject + "\n" + body
    parsed = parse_reservation(full_text, subject)

    # Only store if we found at least a date or venue
    if parsed["reservation_date"] or parsed["venue"]:
        from_addr = str(msg["From"] or "")
        db.execute("""
            INSERT INTO reservations (source_email, subject, date_received,
                reservation_date, reservation_time, venue, party_size,
                confirmation, raw_body, parsed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (from_addr, subject, date_str,
              parsed["reservation_date"], parsed["reservation_time"],
              parsed["venue"], parsed["party_size"],
              parsed["confirmation"], body[:5000]))

    db.execute("INSERT INTO processed_emails (email_uid) VALUES (?)", (uid_str,))
    db.commit()
    return parsed

def check_inbox(db, mail):
    """Check inbox for reservation emails from akhiger@gmail.com or with [RESV] prefix."""
    mail.select("INBOX", readonly=False)
    
    # Search strategies — try each
    strategies = [
        '(FROM "akhiger@gmail.com")',           # Direct forwards
        '(SUBJECT "[RESV]")',                     # Prefixed
        '(SUBJECT "Fwd" FROM "akhiger")',        # Forward from akhiger
    ]
    
    all_uids = set()
    for strategy in strategies:
        try:
            status, msgs = mail.search(None, strategy)
            if status == "OK" and msgs[0]:
                all_uids.update(msgs[0].split())
        except Exception:
            pass
    
    if not all_uids:
        return 0

    uids = sorted(all_uids)[-30:]  # Last 30 matching emails
    new_count = 0

    for uid in uids[-20:]:  # Last 20 emails max
        try:
            status, data = mail.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(data[0][1], policy=policy.default)
            result = process_email(db, uid, msg)
            if result:
                new_count += 1
        except Exception as e:
            print(f"  Error processing email: {e}", file=sys.stderr)

    return new_count

def query_reservations(query_str):
    """Search reservations. Understands 'next week', 'today', 'July', venue names."""
    db = sqlite3.connect(str(DB))
    now = datetime.now()

    query_lower = query_str.lower()

    if "today" in query_lower:
        date_filter = now.strftime("%Y-%m-%d")
        rows = db.execute(
            "SELECT * FROM reservations WHERE reservation_date LIKE ? ORDER BY reservation_date",
            (f"%{date_filter}%",)
        ).fetchall()
    elif "tomorrow" in query_lower:
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        rows = db.execute(
            "SELECT * FROM reservations WHERE reservation_date LIKE ? ORDER BY reservation_date",
            (f"%{tomorrow}%",)
        ).fetchall()
    elif "next week" in query_lower:
        # Next Monday to Sunday
        days_until_monday = (7 - now.weekday()) % 7 or 7
        monday = now + timedelta(days=days_until_monday)
        sunday = monday + timedelta(days=6)
        rows = db.execute(
            "SELECT * FROM reservations ORDER BY reservation_date"
        ).fetchall()
        rows = [r for r in rows if r[4] and monday.strftime("%Y-%m-%d") <= r[4] <= sunday.strftime("%Y-%m-%d")]
    elif "this week" in query_lower:
        monday = now - timedelta(days=now.weekday())
        rows = db.execute(
            "SELECT * FROM reservations ORDER BY reservation_date"
        ).fetchall()
        rows = [r for r in rows if r[4] and r[4] >= monday.strftime("%Y-%m-%d")]
    elif any(m in query_lower for m in ["month", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]):
        rows = db.execute(
            "SELECT * FROM reservations WHERE subject LIKE ? OR venue LIKE ? OR raw_body LIKE ? ORDER BY reservation_date",
            (f"%{query_str}%", f"%{query_str}%", f"%{query_str}%")
        ).fetchall()
    else:
        # Generic search
        rows = db.execute(
            "SELECT * FROM reservations WHERE subject LIKE ? OR venue LIKE ? ORDER BY reservation_date DESC LIMIT 20",
            (f"%{query_str}%", f"%{query_str}%")
        ).fetchall()

    if not rows:
        print("No reservations found.")
        return

    print(f"{'Date':<18} {'Venue':<25} {'Party':<6} {'Conf#':<12} {'Time'}")
    print("-" * 80)
    for r in rows:
        date = (r[4] or "?")[:17]
        venue = (r[5] or "?")[:24]
        party = str(r[6]) if r[6] else "?"
        conf = (r[7] or "")[:11]
        time = (r[8] or "?")[:10] if len(r) > 8 else "?"
        print(f"{date:<18} {venue:<25} {party:<6} {conf:<12} {time}")

    print(f"\n{len(rows)} reservation(s) found.")

def list_all(db):
    """Show all reservations."""
    rows = db.execute(
        "SELECT id, reservation_date, reservation_time, venue, party_size, confirmation, subject FROM reservations ORDER BY reservation_date"
    ).fetchall()
    if not rows:
        print("No reservations in database yet.")
        print("Forward reservation emails to atigerclawai@gmail.com with subject '[RESV] ...'")
        return
    print(f"{'Date':<18} {'Time':<10} {'Venue':<25} {'Party':<6} {'Conf#':<12}")
    print("-" * 80)
    for r in rows:
        print(f"{(r[1] or '?'):<18} {(r[2] or '?'):<10} {(r[3] or '?'):<25} {(str(r[4]) if r[4] else '?'):<6} {(r[5] or ''):<12}")

def watch_loop():
    """Run as daemon, polling every 60s."""
    db = init_db()
    print(f"Watching Gmail label '{LABEL}' for new reservations...")

    while True:
        try:
            mail = connect_imap()
            new = check_inbox(db, mail)
            mail.logout()
            if new:
                print(f"  Parsed {new} new reservation(s) at {datetime.now().strftime('%H:%M')}")
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
        time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch_loop()
    elif len(sys.argv) > 1 and sys.argv[1] == "--query":
        query_str = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if query_str:
            query_reservations(query_str)
        else:
            db = init_db()
            list_all(db)
    elif len(sys.argv) > 1 and sys.argv[1] == "--list":
        db = init_db()
        list_all(db)
    else:
        db = init_db()
        try:
            mail = connect_imap()
            new = check_inbox(db, mail)
            mail.logout()
            print(f"Parsed {new} new reservation(s).")
            list_all(db)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
