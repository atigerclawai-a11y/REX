#!/usr/bin/env python3
"""BBG Scraper Loop — runs every 5 minutes.
Scrapes Gmail for:
  1. Owner.com reservation emails → extracts CSV → stores in CC_bbg_contacts.db
  2. Stripe payment notification emails → cross-references reservations
  3. Generates updated payment report CSV

Silent if nothing new. Sends alert if new reservations found.
"""

import json, os, sqlite3, subprocess, sys, csv, io, re
from datetime import datetime, timezone
from pathlib import Path
from email import policy
from email.parser import BytesParser

HOME = Path.home()
DB = HOME / "Desktop/REX" / "CC_bbg_contacts.db"
OUT = HOME / "Desktop" / "REX" / "output"
OUT.mkdir(parents=True, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────

imap = ["/opt/homebrew/bin/himalaya"]

def get_latest_uid():
    """Get the highest email UID we've processed."""
    conn = sqlite3.connect(str(DB))
    cur = conn.execute("SELECT MAX(email_uid) FROM reservations")
    uid = cur.fetchone()[0]
    conn.close()
    return int(uid) if uid else 0

def set_latest_uid(new_uid):
    """Store the highest UID in a simple file."""
    Path(HOME / ".bbg_last_uid").write_text(str(new_uid))

def get_saved_uid():
    p = HOME / ".bbg_last_uid"
    if p.exists():
        return int(p.read_text().strip())
    return 0

def fetch_emails(since_uid=0):
    """Fetch Owner.com and Stripe payment emails since last UID."""
    result = subprocess.run(
        [*imap, "envelope", "list", "--page-size", "500"],
        capture_output=True, text=True, timeout=30
    )
    lines = result.stdout.strip().split("\n")
    # extract UID from each line and check if it's new
    new_emails = []
    for line in lines:
        parts = line.split("|")
        if len(parts) < 3:
            continue
        try:
            uid = int(parts[0].strip())
        except ValueError:
            continue
        if uid > since_uid:
            # Check subject
            subject = ""
            if len(parts) >= 4:
                # Extract subject from between | marks
                subject = parts[2].strip() if len(parts) > 2 else ""
            new_emails.append({"uid": uid, "subject": subject, "line": line})
    return new_emails

def read_email_body(uid):
    """Read full email body."""
    result = subprocess.run(
        [*imap, "message", "read", str(uid)],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout

def extract_reservation_from_subject(subject):
    """Try to parse reservation from Subjects like:
    'New Reservations Form Submission' or 'BBG Owner.com...'
    """
    # Match "X new" pattern
    m = re.search(r'(\d+)\s+new', subject, re.I)
    return int(m.group(1)) if m else 0

def update_reservation_from_csv(csv_content, source="owner.com"):
    """Parse CSV from Owner.com and update reservations table."""
    reader = csv.DictReader(io.StringIO(csv_content))
    conn = sqlite3.connect(str(DB))
    added = 0
    for row in reader:
        name = row.get("Name", "").strip() or row.get("name", "").strip()
        date_str = row.get("Date", "").strip() or row.get("date", "").strip()
        time_str = row.get("Time", "").strip() or row.get("time", "").strip()
        guests = row.get("Guests", row.get("guests", "0")).strip()
        phone = row.get("Phone", row.get("phone", "")).strip()

        if not name or not date_str:
            continue

        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO reservations (party_name, party_size, reservation_date, reservation_time, phone, status, source) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (name, int(guests) if guests.isdigit() else 0, date_str, time_str, phone, source)
            )
            if cur.rowcount > 0:
                added += 1
        except sqlite3.Error:
            pass
    conn.commit()
    conn.close()
    return added


def main():
    last_uid = get_saved_uid()
    new_emails = fetch_emails(last_uid)

    if not new_emails:
        # No new emails — silent exit
        sys.exit(0)

    max_uid = last_uid
    total_new_reservations = 0
    changes = []

    for email in sorted(new_emails, key=lambda e: e["uid"]):
        uid = email["uid"]
        subj = email["subject"]
        max_uid = max(max_uid, uid)

        # Owner.com reservation emails
        if "BBG Owner.com" in subj or "owner.com" in subj.lower():
            body = read_email_body(uid)
            # Extract CSV from attachment markers
            csv_match = re.search(r'filename="([^"]+\.csv)"', body)
            if csv_match:
                csv_path = csv_match.group(1)
                if os.path.exists(csv_path):
                    with open(csv_path) as f:
                        csv_content = f.read()
                    added = update_reservation_from_csv(csv_content)
                    total_new_reservations += added
                    if added:
                        changes.append(f"📧 Email {uid}: {added} new reservations from Owner.com")

        # Forwarded reservation emails from Allen
        elif "New Reservations Form Submission" in subj:
            body = read_email_body(uid)
            # Try to extract reservation info from body
            added = 0
            name_m = re.search(r'Name[:\s]+(.+)', body, re.I)
            date_m = re.search(r'Date[:\s]+(.+)', body, re.I)
            time_m = re.search(r'Time[:\s]+(.+)', body, re.I)
            guests_m = re.search(r'([Gg]uest[s]?|[Pp]arty)[:\s]+(\d+)', body)
            phone_m = re.search(r'[Pp]hone[:\s]+(.+)', body, re.I)

            if name_m:
                conn = sqlite3.connect(str(DB))
                try:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO reservations (party_name, party_size, reservation_date, reservation_time, phone, status, source, email_uid) "
                        "VALUES (?, ?, ?, ?, ?, 'pending', 'forwarded', ?)",
                        (name_m.group(1).strip()[:100],
                         int(guests_m.group(2)) if guests_m else 0,
                         (date_m.group(1).strip() if date_m else datetime.now().strftime("%Y-%m-%d"))[:20],
                         (time_m.group(1).strip() if time_m else "")[:20],
                         (phone_m.group(1).strip() if phone_m else "")[:20],
                         uid)
                    )
                    added = cur.rowcount
                except sqlite3.Error:
                    pass
                conn.commit()
                conn.close()
            if added:
                total_new_reservations += added
                changes.append(f"📧 Email {uid}: {added} new reservation (forwarded)")

    # Save progress
    if max_uid > last_uid:
        set_latest_uid(max_uid)

    # Generate report
    report_path = OUT / f"bbg_reservations_{datetime.now().strftime('%Y-%m-%d_%H%M')}.csv"
    conn = sqlite3.connect(str(DB))
    rows = conn.execute("""
        SELECT party_name, party_size, reservation_date, reservation_time,
               phone, payment_status, amount_paid, status
        FROM reservations
        WHERE reservation_date >= date('now', '-1 day')
        ORDER BY reservation_date, reservation_time
    """).fetchall()
    conn.close()

    with open(report_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Party Size", "Date", "Time", "Phone", "Payment", "Amount", "Status"])
        w.writerows(rows)

    # Also generate today's report
    today_path = OUT / "bbg_reservations_today.csv"
    conn = sqlite3.connect(str(DB))
    rows_today = conn.execute("""
        SELECT party_name, party_size, reservation_date, reservation_time,
               phone, payment_status, amount_paid, status
        FROM reservations
        WHERE reservation_date = date('now')
        ORDER BY reservation_time
    """).fetchall()
    conn.close()
    with open(today_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Party Size", "Date", "Time", "Phone", "Payment", "Amount", "Status"])
        w.writerows(rows_today)

    total = len(rows)
    paid = sum(1 for r in rows if r[5] == "paid")
    unpaid = total - paid

    # Output report
    print(f"BBG Scraper Update — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"📋 {total} reservations")
    print(f"✅ {paid} PAID")
    print(f"❌ {unpaid} UNPAID")
    if changes:
        print(f"\n{'—'*40}")
        for c in changes:
            print(c)
    print(f"\n📄 Report: {report_path}")
    print(f"📄 Today: {today_path}")

if __name__ == "__main__":
    main()
