#!/usr/bin/env python3
"""
CC_group_chat_scheduler.py
Gold Health Systems · Garden of Joy
Polls iMessage chat.db for attendance signals, triggers atomic 7-cascade.

Usage:
  python CC_group_chat_scheduler.py              # daemon mode, polls every 60s
  python CC_group_chat_scheduler.py --once       # single scan and exit
  python CC_group_chat_scheduler.py --dry-run    # show what would happen, no writes
  python CC_group_chat_scheduler.py --test "Maria won't be in tomorrow"
"""

import argparse
import difflib
import json
import logging
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IMESSAGE_DB = Path.home() / "Library/Messages/chat.db"
CLIENT_DB   = Path(os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db"))
STATE_FILE  = Path(__file__).parent / "CC_chat_scheduler_state.json"
LOG_FILE    = Path(__file__).parent / "logs" / "CC_group_chat_scheduler.log"
POLL_INTERVAL = 60  # seconds

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = "5587703834"

# iMessage group chat ROWIDs to watch (set these to the actual group chat IDs
# found in chat.db; use --list-chats to discover them).
# Leave empty to watch ALL chats (not recommended in production).
WATCHED_CHAT_IDS: list[int] = []

# Fuzzy match threshold (0–1); below this → alert Kato, don't act.
FUZZY_THRESHOLD = 0.72

# Attendance keywords (case-insensitive)
ABSENT_PATTERNS = [
    r"\bwon[''`]?t\s+be\s+in\b",
    r"\bnot\s+coming\b",
    r"\bwill\s+not\s+be\s+in\b",
    r"\bcalled?\s+out\b",
    r"\bcall\s+out\b",
    r"\bsick\b",
    r"\bhas\s+an?\s+appointment\b",
    r"\bno\s+{name}\b",          # filled per-candidate
    r"\bstaying\s+home\b",
    r"\bcan[''`]?t\s+make\s+it\b",
    r"\bnot\s+attending\b",
    r"\bабсент\b",               # Russian "absent"
    r"\bбольн\w+\b",            # sick/болен/больна
    r"\bне\s+придёт\b",         # "won't come" (Russian)
    r"\bне\s+приедет\b",
]

DATE_PATTERNS = [
    (r"\btoday\b",              0),
    (r"\btonight\b",            0),
    (r"\btomorrow\b",           1),
    (r"\bсегодня\b",            0),
    (r"\bзавтра\b",             1),
    (r"\bmon(?:day)?\b",        None),  # resolved by weekday
    (r"\btue(?:sday)?\b",       None),
    (r"\bwed(?:nesday)?\b",     None),
    (r"\bthu(?:rsday)?\b",      None),
    (r"\bfri(?:day)?\b",        None),
    (r"\bsat(?:urday)?\b",      None),
]

WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

REASON_KEYWORDS = {
    "sick":        ["sick", "ill", "fever", "not feeling well", "больн", "болеет"],
    "appointment": ["appointment", "doctor", "dentist", "врач", "прием"],
    "personal":    ["personal", "family", "emergency"],
    "called_out":  ["called out", "call out", "called in"],
    "unknown":     [],
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("cc_group_chat_scheduler")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_message_rowid": 0}

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def telegram_alert(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — cannot send alert: %s", text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        log.error("Telegram alert failed: %s", exc)

# ---------------------------------------------------------------------------
# iMessage reader
# ---------------------------------------------------------------------------

def fetch_new_messages(last_rowid: int, dry_run: bool = False) -> list[dict]:
    """Return messages newer than last_rowid from watched group chats."""
    if not IMESSAGE_DB.exists():
        log.error("iMessage DB not found at %s", IMESSAGE_DB)
        return []

    try:
        con = sqlite3.connect(f"file:{IMESSAGE_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        log.error("Cannot open iMessage DB: %s", exc)
        return []

    try:
        cur = con.cursor()

        chat_filter = ""
        params: list = [last_rowid]
        if WATCHED_CHAT_IDS:
            placeholders = ",".join("?" * len(WATCHED_CHAT_IDS))
            chat_filter = f"AND cm.chat_id IN ({placeholders})"
            params = [last_rowid] + list(WATCHED_CHAT_IDS)

        query = f"""
            SELECT
                m.ROWID,
                m.text,
                m.date,
                COALESCE(h.id, 'me') AS sender,
                cm.chat_id,
                c.display_name
            FROM message m
            JOIN chat_message_join cm ON cm.message_id = m.ROWID
            JOIN chat c ON c.ROWID = cm.chat_id
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            WHERE m.ROWID > ?
              AND m.text IS NOT NULL
              AND m.text != ''
              {chat_filter}
            ORDER BY m.ROWID ASC
        """
        cur.execute(query, params)
        rows = cur.fetchall()
    finally:
        con.close()

    messages = []
    for rowid, text, msg_date, sender, chat_id, chat_name in rows:
        # iMessage epoch: seconds since 2001-01-01
        ts = datetime(2001, 1, 1) + timedelta(seconds=msg_date / 1e9 if msg_date > 1e12 else msg_date)
        messages.append({
            "rowid":     rowid,
            "text":      text,
            "timestamp": ts.isoformat(),
            "sender":    sender,
            "chat_id":   chat_id,
            "chat_name": chat_name or f"chat_{chat_id}",
        })
    return messages

# ---------------------------------------------------------------------------
# Client list loader
# ---------------------------------------------------------------------------

def load_clients() -> list[dict]:
    """Return list of {id, first_name, last_name, full_name} from auth_tracker.db."""
    if not CLIENT_DB.exists():
        log.error("Client DB not found at %s", CLIENT_DB)
        return []
    try:
        con = sqlite3.connect(str(CLIENT_DB))
        cur = con.cursor()
        cur.execute("SELECT id, first_name, last_name FROM clients")
        rows = cur.fetchall()
        con.close()
    except Exception as exc:
        log.error("Cannot read clients: %s", exc)
        return []

    clients = []
    for cid, fname, lname in rows:
        fname = (fname or "").strip()
        lname = (lname or "").strip()
        clients.append({
            "id":         cid,
            "first_name": fname,
            "last_name":  lname,
            "full_name":  f"{fname} {lname}".strip(),
        })
    return clients

# ---------------------------------------------------------------------------
# NLP — signal detection
# ---------------------------------------------------------------------------

def detect_attendance_signal(text: str) -> bool:
    """Return True if text contains an absence signal."""
    lower = text.lower()
    for pattern in ABSENT_PATTERNS:
        p = pattern.replace(r"\b{name}\b", r"\b\w+\b")
        if re.search(p, lower):
            return True
    return False

def extract_reason(text: str) -> str:
    lower = text.lower()
    for reason, keywords in REASON_KEYWORDS.items():
        if reason == "unknown":
            continue
        for kw in keywords:
            if kw in lower:
                return reason
    return "unknown"

def extract_date(text: str) -> date:
    """Extract target date from message. Defaults to today."""
    lower = text.lower()
    today = date.today()

    for pattern, offset in DATE_PATTERNS:
        if offset is not None:
            if re.search(pattern, lower):
                return today + timedelta(days=offset)
        else:
            # weekday match
            m = re.search(pattern, lower)
            if m:
                abbrev = m.group(0)[:3].lower()
                if abbrev in WEEKDAY_NAMES:
                    target_wd = WEEKDAY_NAMES.index(abbrev)
                    days_ahead = (target_wd - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    return today + timedelta(days=days_ahead)

    return today

def fuzzy_match_client(text: str, clients: list[dict]) -> tuple[dict | None, float]:
    """
    Try to find a client name mentioned in text.
    Returns (client_dict, score) or (None, 0.0).
    """
    text_lower = text.lower()
    best_client = None
    best_score = 0.0

    for client in clients:
        for name_field in ("full_name", "last_name", "first_name"):
            name = client[name_field].lower()
            if not name:
                continue
            # Exact substring match → score 1.0
            if name in text_lower:
                return client, 1.0
            # Fuzzy
            score = difflib.SequenceMatcher(None, name, text_lower).ratio()
            # Also check each word in text
            for word in re.findall(r"[а-яёa-z'-]{3,}", text_lower):
                word_score = difflib.SequenceMatcher(None, name, word).ratio()
                score = max(score, word_score)
            if score > best_score:
                best_score = score
                best_client = client

    return best_client, best_score

# ---------------------------------------------------------------------------
# Atomic 7-cascade
# ---------------------------------------------------------------------------

@contextmanager
def atomic_db(db_path: Path):
    """Open DB with a savepoint so we can roll back all cascade steps at once."""
    con = sqlite3.connect(str(db_path))
    con.isolation_level = None  # autocommit off for manual control
    try:
        con.execute("BEGIN")
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()

def run_7_cascade(
    client: dict,
    target_date: date,
    reason: str,
    sender: str,
    raw_text: str,
    dry_run: bool = False,
) -> bool:
    """
    Attempt atomic 7-step cascade.
    Returns True on success, False on failure (rollback already done).
    All 7 steps operate within a single DB transaction.
    """
    client_id   = client["id"]
    client_name = client["full_name"]
    date_str    = target_date.isoformat()
    now_str     = datetime.now().isoformat(timespec="seconds")

    log.info(
        "CASCADE START | client=%s (id=%s) | date=%s | reason=%s | sender=%s",
        client_name, client_id, date_str, reason, sender,
    )

    if dry_run:
        log.info("[DRY-RUN] Would cascade for %s on %s (reason: %s)", client_name, date_str, reason)
        log.info("[DRY-RUN] Message from %s: %s", sender, raw_text)
        return True

    try:
        with atomic_db(CLIENT_DB) as con:
            # Step 1 — Calendar: mark client absent on target_date
            con.execute("""
                INSERT OR REPLACE INTO calendar_absences
                    (client_id, absence_date, reason, updated_at)
                VALUES (?, ?, ?, ?)
            """, (client_id, date_str, reason, now_str))
            log.info("Step 1 DONE — calendar absence recorded")

            # Step 2 — Attendance: mark absent
            con.execute("""
                INSERT OR REPLACE INTO attendance
                    (client_id, attendance_date, status, reason, reported_by, updated_at)
                VALUES (?, ?, 'ABSENT', ?, ?, ?)
            """, (client_id, date_str, reason, sender, now_str))
            log.info("Step 2 DONE — attendance marked absent")

            # Step 3 — Driver list: set exclude flag
            # Larry hard-block is enforced upstream (client never matched to Larry).
            con.execute("""
                INSERT OR REPLACE INTO driver_exclusions
                    (client_id, exclusion_date, reason, updated_at)
                VALUES (?, ?, ?, ?)
            """, (client_id, date_str, reason, now_str))
            log.info("Step 3 DONE — driver exclusion set")

            # Step 4 — Kitchen list: decrement / exclude
            con.execute("""
                INSERT OR REPLACE INTO kitchen_exclusions
                    (client_id, exclusion_date, reason, updated_at)
                VALUES (?, ?, ?, ?)
            """, (client_id, date_str, reason, now_str))
            log.info("Step 4 DONE — kitchen exclusion set")

            # Step 5 — Distribution logs
            con.execute("""
                INSERT OR REPLACE INTO distribution_exclusions
                    (client_id, exclusion_date, reason, updated_at)
                VALUES (?, ?, ?, ?)
            """, (client_id, date_str, reason, now_str))
            log.info("Step 5 DONE — distribution exclusion set")

            # Step 6 — Sign-in sheets: mark absent
            con.execute("""
                INSERT OR REPLACE INTO signin_status
                    (client_id, signin_date, status, updated_at)
                VALUES (?, ?, 'ABSENT', ?)
            """, (client_id, date_str, now_str))
            log.info("Step 6 DONE — sign-in sheet updated")

            # Step 7 — Client notes: timestamped entry
            note = (
                f"[{now_str}] ABSENT on {date_str}. "
                f"Reported by: {sender}. Reason: {reason}. "
                f"Original message: \"{raw_text}\""
            )
            con.execute("""
                INSERT INTO client_notes (client_id, note, created_at)
                VALUES (?, ?, ?)
            """, (client_id, note, now_str))
            log.info("Step 7 DONE — client note added")

        log.info("CASCADE COMPLETE — all 7 steps committed for %s on %s", client_name, date_str)
        return True

    except Exception as exc:
        log.error("CASCADE FAILED — rolled back all steps: %s", exc)
        telegram_alert(
            f"*GOJ SCHEDULER — CASCADE FAILURE*\n"
            f"Client: {client_name}\n"
            f"Date: {date_str}\n"
            f"Error: {exc}\n"
            f"Message: {raw_text}\n"
            f"No changes were saved."
        )
        return False

# ---------------------------------------------------------------------------
# Larry hard-block
# ---------------------------------------------------------------------------

LARRY_PATTERN = re.compile(r"\blarry\b", re.IGNORECASE)

def is_larry(client: dict) -> bool:
    return LARRY_PATTERN.search(client.get("full_name", "")) is not None

# ---------------------------------------------------------------------------
# Process a single message
# ---------------------------------------------------------------------------

def process_message(msg: dict, clients: list[dict], dry_run: bool = False) -> None:
    text   = msg["text"]
    sender = msg["sender"]
    rowid  = msg["rowid"]

    log.info("MSG rowid=%s from=%s: %s", rowid, sender, text[:120])

    if not detect_attendance_signal(text):
        log.debug("No attendance signal — skipping")
        return

    client, score = fuzzy_match_client(text, clients)

    if client is None or score < FUZZY_THRESHOLD:
        log.warning("Ambiguous client match (score=%.2f) in message: %s", score or 0, text)
        telegram_alert(
            f"*GOJ SCHEDULER — AMBIGUOUS CLIENT*\n"
            f"Message: {text}\n"
            f"From: {sender}\n"
            f"Best match score: {score:.2f} (threshold {FUZZY_THRESHOLD})\n"
            f"Action needed: please confirm client name and update manually."
        )
        return

    # Larry hard-block
    if is_larry(client):
        log.warning("HARD BLOCK — Larry cannot appear on any list. Skipping.")
        telegram_alert(
            f"*GOJ SCHEDULER — LARRY BLOCK*\n"
            f"A message matched Larry. Hard block enforced. No action taken.\n"
            f"Message: {text}"
        )
        return

    target_date = extract_date(text)
    reason      = extract_reason(text)

    log.info(
        "SIGNAL | client=%s (score=%.2f) | date=%s | reason=%s",
        client["full_name"], score, target_date, reason,
    )

    success = run_7_cascade(
        client=client,
        target_date=target_date,
        reason=reason,
        sender=sender,
        raw_text=text,
        dry_run=dry_run,
    )

    if success and not dry_run:
        telegram_alert(
            f"*GOJ SCHEDULER — ABSENCE RECORDED*\n"
            f"Client: {client['full_name']}\n"
            f"Date: {target_date}\n"
            f"Reason: {reason}\n"
            f"Reported by: {sender}\n"
            f"All 7 cascade steps completed."
        )

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(once: bool = False, dry_run: bool = False) -> None:
    state   = load_state()
    clients = load_clients()

    if not clients:
        log.error("No clients loaded — cannot proceed.")
        sys.exit(1)

    log.info(
        "Loaded %d clients. Last processed rowid: %d. dry_run=%s",
        len(clients), state["last_message_rowid"], dry_run,
    )

    while True:
        messages = fetch_new_messages(state["last_message_rowid"], dry_run=dry_run)

        if messages:
            log.info("Found %d new message(s) to process.", len(messages))
            for msg in messages:
                process_message(msg, clients, dry_run=dry_run)
                if not dry_run:
                    state["last_message_rowid"] = msg["rowid"]
                    save_state(state)
        else:
            log.debug("No new messages.")

        if once:
            break

        time.sleep(POLL_INTERVAL)

# ---------------------------------------------------------------------------
# --test mode
# ---------------------------------------------------------------------------

def run_test(sample_text: str) -> None:
    clients = load_clients()
    if not clients:
        log.warning("No clients in DB — using synthetic test client list.")
        clients = [
            {"id": 1, "first_name": "Maria",    "last_name": "Ivanova",    "full_name": "Maria Ivanova"},
            {"id": 2, "first_name": "Boris",    "last_name": "Petrov",     "full_name": "Boris Petrov"},
            {"id": 3, "first_name": "Svetlana", "last_name": "Kovalenko",  "full_name": "Svetlana Kovalenko"},
        ]

    msg = {
        "rowid":     -1,
        "text":      sample_text,
        "timestamp": datetime.now().isoformat(),
        "sender":    "test-mode",
        "chat_id":   0,
        "chat_name": "test",
    }
    process_message(msg, clients, dry_run=True)

# ---------------------------------------------------------------------------
# --list-chats helper
# ---------------------------------------------------------------------------

def list_chats() -> None:
    if not IMESSAGE_DB.exists():
        print(f"iMessage DB not found at {IMESSAGE_DB}")
        return
    try:
        con = sqlite3.connect(f"file:{IMESSAGE_DB}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("""
            SELECT c.ROWID, c.display_name, c.chat_identifier,
                   COUNT(cm.message_id) AS msg_count
            FROM chat c
            LEFT JOIN chat_message_join cm ON cm.chat_id = c.ROWID
            GROUP BY c.ROWID
            ORDER BY msg_count DESC
        """)
        rows = cur.fetchall()
        con.close()
        print(f"{'ID':>6}  {'Messages':>8}  {'Identifier':<40}  Display Name")
        print("-" * 80)
        for rowid, display, identifier, count in rows:
            print(f"{rowid:>6}  {count:>8}  {(identifier or ''):40}  {display or ''}")
    except Exception as exc:
        print(f"Error reading chat.db: {exc}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GOJ iMessage attendance scheduler")
    parser.add_argument("--once",       action="store_true", help="Single scan and exit")
    parser.add_argument("--dry-run",    action="store_true", help="Show actions without writing")
    parser.add_argument("--test",       metavar="MSG",       help="Test with a sample message string")
    parser.add_argument("--list-chats", action="store_true", help="List all iMessage chats and exit")
    args = parser.parse_args()

    if args.list_chats:
        list_chats()
        sys.exit(0)

    if args.test:
        run_test(args.test)
        sys.exit(0)

    run(once=args.once, dry_run=args.dry_run)
