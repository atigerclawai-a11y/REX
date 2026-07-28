#!/usr/bin/env python3
"""
CC_owner_reservation_poller.py
================================
Polls olympusbbg@gmail.com via IMAP for owner.com reservation confirmation
emails and feeds them into CC_bbg_reservations.json (Masha's system).

Can also check atigerclawai@gmail.com as fallback / dual-watch.

Usage:
    python3 CC_owner_reservation_poller.py                # poll once
    python3 CC_owner_reservation_poller.py --dry-run      # show matches
    python3 CC_owner_reservation_poller.py --cron         # silent unless new

State: ~/Desktop/REX/CC_owner_poller_state.json
Output: ~/Desktop/REX/CC_bbg_reservations.json
"""

from __future__ import annotations

import email
import imaplib
import json
import re
import sys
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path

REX_DIR = Path.home() / "Desktop" / "REX"
RESERVATIONS_PATH = REX_DIR / "CC_bbg_reservations.json"
STATE_PATH = REX_DIR / "CC_owner_poller_state.json"

# ── IMAP credentials ───────────────────────────────────────────────────────
# olympusbbg@gmail.com forwards to atigerclawai@gmail.com — no need for separate IMAP.
# App Passwords unavailable on olympusbbg (account type restriction). Forwarding covers it.
ACCOUNTS = [
    {
        "name": "atigerclawai",
        "host": "imap.gmail.com",
        "port": 993,
        "email": "atigerclawai@gmail.com",
        "password": "ijpu cgfi tufj mqhf",
    },
]

# ── Email search criteria ─────────────────────────────────────────────────
SEARCH_SUBJECTS = ["reservations", "submission", "booking confirmed", "table booked"]
SEARCH_FROM = ["olympusbbg", "mg.owner.com"]


def _decode_header(val) -> str:
    """Decode email header to string."""
    if val is None:
        return ""
    parts = decode_header(val)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return [] if "reservations" in path.name else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [] if "reservations" in path.name else {}


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_body(msg) -> str:
    """Extract text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition", ""))
            if ctype in ("text/plain", "text/html") and "attachment" not in cdisp:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
        except Exception:
            pass
    return ""


def _extract_reservation(subject: str, body: str, msg_id: str, from_addr: str) -> dict | None:
    """Try to extract reservation data from email content."""
    combined = f"{subject}\n{body}"
    combined_lower = combined.lower()

    # Quick filter
    if not any(t in combined_lower for t in ["reservation", "booking", "table", "guest", "party"]):
        return None

    # Pattern 0: Owner.com form submission format (exact match)
    # ": Andy kremen\n: email\n: phone\nDate and time: June 19th 2026, 2:45:00 PM\nNumber of people: 5"
    owner_com_form = re.search(
        r'^-{3,}\s*\n\s*:\s*([^\n]+?)\s*\n\s*:\s*[^\n]*\s*\n\s*:\s*[^\n]*\s*\n'
        r'Date and time:\s*([^\n]+?)\s*\n'
        r'Number of people:\s*(\d+)',
        combined, re.IGNORECASE | re.MULTILINE)
    if owner_com_form:
        res = {
            "party_name": owner_com_form.group(1).strip(),
            "date": owner_com_form.group(2).strip(),
            "party_size": int(owner_com_form.group(3)),
            "source": "email_owner_com",
            "email_uid": msg_id,
            "email_from": from_addr,
            "email_subject": subject,
        }
        # Extract phone if present in the third ": " line
        phone_m = re.search(r'^:\s*([^\n]+)\s*\n\s*:\s*[^\n]*\s*\n\s*:\s*(\+?[\d*]+[-\d]*)\s*\n',
                           combined, re.MULTILINE)
        if phone_m:
            res["phone"] = phone_m.group(2).strip()
        # Extract time from "Date and time: June 19th 2026, 2:45:00 PM"
        time_m = re.search(r'(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)?', owner_com_form.group(2))
        if time_m:
            h = int(time_m.group(1))
            mi = time_m.group(2)
            ampm = time_m.group(4) or ''
            if ampm and ampm.upper() == 'PM' and h != 12:
                h += 12
            elif ampm and ampm.upper() == 'AM' and h == 12:
                h = 0
            res["time"] = f"{h:02d}:{mi}"
        return res

    # Pattern 1: Generic "New Reservations Form Submission"
    # Look for structured blocks like "NAME:", "DATE:", "TIME:", "GUESTS:"
    patterns = [
        # Owner.com likely format: label-value pairs
        (r"(?:Name|Guest)[:\s]+([^\n]{2,50})\n.*?(?:Date|When)[:\s]+([^\n]{5,30})\n.*?(?:Time)[:\s]+([^\n]{3,15})\n.*?(?:Guests|Party|Size|People|Covers)[:\s]+(\d+)",
         ["party_name", "date", "time", "party_size"]),
        # "Reservation for NAME on DATE at TIME for N guests"
        (r"[Rr]eservation\s+(?:for|confirmed)[:\s]+([^\n]{2,50}?)\s+on\s+([^\n]{5,30}?)\s+at\s+([^\n]{3,15}?)(?:\s+for\s+(\d+)\s+(?:guest|person|people))?",
         ["party_name", "date", "time", "party_size"]),
        # Tabular: NAME, DATE, TIME, GUESTS as table rows
        (r"([^,\n]{2,50}),?\s*(?:on\s+)?([A-Z][a-z]+ \d{1,2}[,\s]+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})[,\s]+(?:at\s+)?(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)[,\s]+(\d+)\s*(?:guest|person|people|ppl)",
         ["party_name", "date", "time", "party_size"]),
    ]

    for pattern, fields in patterns:
        match = re.search(pattern, combined, re.IGNORECASE | re.DOTALL)
        if match:
            res = {}
            for i, field in enumerate(fields):
                val = match.group(i + 1) if i + 1 <= len(match.groups()) else None
                if val:
                    res[field] = val.strip()
            res["source"] = "email"
            res["email_uid"] = msg_id
            res["email_from"] = from_addr
            res["email_subject"] = subject
            return res

    # No pattern matched — save raw for future training
    raw_dir = REX_DIR / "owner_poller_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"unmatched_{msg_id}.txt").write_text(
        f"FROM: {from_addr}\nSUBJECT: {subject}\n\n{body[:4000]}", encoding="utf-8")
    return None


def _parse_date(s: str) -> str:
    if not s:
        return datetime.now().strftime("%Y-%m-%d")
    s = s.strip()
    # Strip ordinal suffixes: June 19th 2026 → June 19 2026
    s = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', s)
    # Extract just the date part if it contains a time: "June 19 2026, 2:45:00 PM"
    s = s.split(",")[0].strip()
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y",
                "%B %d %Y", "%b %d %Y", "%A %B %d %Y", "%A %b %d %Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _parse_time(s: str) -> str:
    if not s:
        return "19:00"
    s = s.strip().upper()
    # Already 24h
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    # 12h
    m = re.match(r"(\d{1,2}):?(\d{2})?\s*(AM|PM)?", s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or "00")
        ampm = m.group(3) or ""
        if ampm == "PM" and h != 12:
            h += 12
        elif ampm == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}"
    return s


def poll(dry_run: bool = False) -> list[dict]:
    """Main polling function. Returns newly ingested reservations."""
    state = _load_json(STATE_PATH)
    seen_uids = set(state.get("seen_uids", []))
    reservations = _load_json(RESERVATIONS_PATH)
    existing = {r.get("email_uid") for r in reservations if r.get("email_uid")}

    new_reservations = []

    for account in ACCOUNTS:
        try:
            conn = imaplib.IMAP4_SSL(account["host"], account["port"])
            conn.login(account["email"], account["password"])
            conn.select("INBOX")

            for term in SEARCH_SUBJECTS + SEARCH_FROM:
                try:
                    status, data = conn.search(None, f'(SUBJECT "{term}")')
                    if status != "OK":
                        continue
                    for num in data[0].split():
                        uid = f"{account['name']}:{num.decode()}"
                        if uid in seen_uids or uid in existing:
                            continue

                        status, msg_data = conn.fetch(num, "(RFC822)")
                        if status != "OK":
                            continue

                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        subject = _decode_header(msg["Subject"])
                        from_addr = _decode_header(msg["From"])
                        body = _get_body(msg)

                        extracted = _extract_reservation(subject, body, uid, from_addr)
                        if extracted:
                            res = {
                                "party_name": (extracted.get("party_name") or "Unknown Guest").strip(),
                                "party_size": int(extracted.get("party_size") or 2),
                                "reservation_date": _parse_date(extracted.get("date", "")),
                                "reservation_time": _parse_time(extracted.get("time", "")),
                                "phone": extracted.get("phone"),
                                "notes": f"From: {from_addr} | Subject: {subject}",
                                "source": "email",
                                "email_uid": uid,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "confirmed": False,
                            }

                            if not dry_run:
                                res["id"] = len(reservations) + len(new_reservations) + 1
                                new_reservations.append(res)
                                seen_uids.add(uid)
                except imaplib.IMAP4.error:
                    continue

            conn.logout()
        except Exception as e:
            print(f"[WARN] IMAP error for {account['name']}: {e}", file=sys.stderr)

    if new_reservations and not dry_run:
        reservations.extend(new_reservations)
        _save_json(RESERVATIONS_PATH, reservations)
        state["seen_uids"] = sorted(seen_uids)
        state["last_poll"] = datetime.now(timezone.utc).isoformat()
        _save_json(STATE_PATH, state)
        print(f"[OK] Ingested {len(new_reservations)} new reservation(s)")

    return new_reservations


def main():
    dry_run = "--dry-run" in sys.argv
    cron_mode = "--cron" in sys.argv

    new = poll(dry_run=dry_run)

    if dry_run:
        print(json.dumps(new, indent=2, ensure_ascii=False))
        return

    if cron_mode and not new:
        return

    if new:
        for r in new:
            print(f"  #{r.get('id')}: {r['party_name']} x{r['party_size']} "
                  f"on {r['reservation_date']} @ {r['reservation_time']}")

    total = len(_load_json(RESERVATIONS_PATH))
    print(f"[DONE] {len(new)} new, {total} total reservations")


if __name__ == "__main__":
    main()
