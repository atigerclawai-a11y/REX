#!/opt/homebrew/bin/python3.12
"""
CC_resy_moa.py — MOA Reservation Orchestrator (resy-overseer)

Change detection engine for BBG event payment reconciliation.
Monitors CC_bbg_reservations.json and Stripe payments for new activity,
then signals the /resy pipeline dispatch when changes are detected.

Usage:
  python3 CC_resy_moa.py                  # Check for changes, output JSON if changed
  python3 CC_resy_moa.py --force          # Force dispatch regardless of changes
  python3 CC_resy_moa.py --event DATE     # Check specific event date only
  python3 CC_resy_moa.py --quiet          # Suppress all output (even on change)
  python3 CC_resy_moa.py --reset          # Reset state file (fresh start)

Exit codes:
  0 — no changes detected (or handled successfully with --force)
  1 — changes detected (so cron can react)
  2 — error occurred

Environment:
  Python: /opt/homebrew/bin/python3.12 (macOS TCC blocks system /usr/bin/python3)
  Workdir: ~/ (NOT /tmp — TCC blocks Desktop file access from /tmp)
  Cron: Hermes cron agent launches with full permissions

Design:
  - 30-second detection engine (no heavy scraping)
  - Only scrapes data when changes are confirmed
  - State file tracks per-event reservation + payment hashes
  - 5-minute debounce on re-dispatch
  - $45-multiple filter for event deposits
  - 48-hour payment window
"""

import json
import sys
import os
import hashlib
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict


# ── Configuration ──────────────────────────────────────────────────────────

REX_DIR = Path.home() / "Desktop" / "REX"
RES_FILE = REX_DIR / "CC_bbg_reservations.json"
CROSSREF_FILE = REX_DIR / "bbg_payments_crossref.csv"
SKILL_DIR = Path.home() / ".hermes" / "profiles" / "work" / "skills" / "moa-reservation"
STATE_FILE = SKILL_DIR / ".moa_state.json"

DEPOSIT_PER_PERSON = 45
PAYMENT_WINDOW_HOURS = 48  # today + yesterday
DEBOUNCE_MINUTES = 5       # suppress re-dispatch within this window
OUTPUT_DIR = REX_DIR / "output"


# ── Helpers ────────────────────────────────────────────────────────────────

def load_json(path):
    """Load a JSON file, return {} or [] on failure."""
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return [] if path.suffix == ".json" and path.name.endswith("reservations.json") else {}


def save_json(path, data):
    """Save data as JSON, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def compute_hash(data, sort_keys=True):
    """SHA-256 hash of JSON-serializable data."""
    raw = json.dumps(data, sort_keys=sort_keys, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_state():
    """Load MOA state from .moa_state.json."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"events": {}, "last_check": None, "stripe_last_pi": None, "stripe_payment_count": 0}


def save_state(state):
    """Save MOA state to .moa_state.json."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def is_deposit_amount(amount):
    """Check if an amount is an event deposit ($45 multiple, >= $45)."""
    try:
        amt = float(amount)
        return amt >= DEPOSIT_PER_PERSON and amt % DEPOSIT_PER_PERSON == 0
    except (ValueError, TypeError):
        return False


def is_within_payment_window(date_str):
    """Check if a payment date is within the 48-hour window (today or yesterday)."""
    if not date_str:
        return True  # no date = include (e.g., cash, unknown)
    try:
        # Try various date formats
        for fmt in ["%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%b %d %Y"]:
            try:
                dt = datetime.strptime(date_str.strip(), fmt).date()
                today = date.today()
                window_start = today - timedelta(days=1)
                return window_start <= dt <= today
            except ValueError:
                continue
        # If no format matched, try extracting date parts
        import re
        match = re.search(r'(\w{3})\s+(\d{1,2}),?\s+(\d{4})', date_str)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%b %d %Y").date()
                today = date.today()
                window_start = today - timedelta(days=1)
                return window_start <= dt <= today
            except ValueError:
                pass
    except Exception:
        pass
    return False  # can't parse = exclude to be safe


def extract_payments_from_crossref():
    """Extract Stripe payment data from crossref CSV (no Chrome required)."""
    payments = []
    if not CROSSREF_FILE.exists():
        return payments

    try:
        import csv
        with open(CROSSREF_FILE) as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = row.get("Status", "").strip().upper()
                stripe_id = row.get("Stripe ID", "").strip()
                amount = row.get("Payment", "0").strip()

                if status == "PAID" and stripe_id:
                    try:
                        amt_clean = float(amount.replace("$", "").replace(",", ""))
                    except (ValueError, AttributeError):
                        amt_clean = 0.0

                    if is_deposit_amount(amt_clean):
                        payments.append({
                            "pi_id": stripe_id,
                            "email": row.get("Payment Email", "").strip(),
                            "amount": amt_clean,
                            "name": row.get("Name", "").strip(),
                        })
    except Exception:
        pass

    return payments


# ── Detection Logic ────────────────────────────────────────────────────────

def analyze_reservations(reservations, state, event_date=None):
    """
    Analyze reservations for changes since last check.
    Returns: (changed, new_entries, events_dict)
    """
    # Group by date
    events = defaultdict(list)
    for r in reservations:
        rdate = r.get("reservation_date", "unknown")
        events[rdate].append(r)

    # If a specific event date was requested, only check that one
    if event_date:
        events = {event_date: events.get(event_date, [])}

    state_events = state.get("events", {})
    changed_dates = []
    all_new_names = []

    for edate, entries in events.items():
        current_hash = compute_hash(entries)
        event_state = state_events.get(edate, {})
        prev_hash = event_state.get("reservation_hash", "")
        prev_count = event_state.get("reservation_count", 0)

        if current_hash != prev_hash:
            changed_dates.append(edate)
            # Find new entries by ID
            prev_ids = set(event_state.get("reservation_ids", []))
            current_ids = set(r.get("id") for r in entries if r.get("id"))
            new_ids = current_ids - prev_ids

            if new_ids:
                new_names = [r.get("party_name", "?") for r in entries if r.get("id") in new_ids]
                all_new_names.extend(new_names)

    new_count = len(all_new_names)
    changed = bool(changed_dates)

    return changed, new_count, all_new_names, dict(events), changed_dates


def analyze_payments(state):
    """
    Check for new Stripe payments (via crossref CSV only — no Chrome scrape).
    Returns: (changed, new_payments, payment_data)
    """
    payments = extract_payments_from_crossref()
    if not payments:
        return False, 0, [], []

    prev_pi = state.get("stripe_last_pi", "")
    prev_count = state.get("stripe_payment_count", 0)

    # Find new payments (PI IDs we haven't seen)
    current_pi_ids = [p["pi_id"] for p in payments]
    new_pis = []

    if prev_pi and prev_pi in current_pi_ids:
        idx = current_pi_ids.index(prev_pi)
        new_pis = current_pi_ids[:idx]  # everything before the last known PI
    else:
        # Last known PI not found — count difference
        new_pis = current_pi_ids[:max(0, len(payments) - prev_count)]

    new_payment_count = len(new_pis)
    changed = new_payment_count > 0 or len(payments) != prev_count

    return changed, new_payment_count, new_pis, payments


def should_debounce(state):
    """Check if we're within the debounce window from last dispatch."""
    last_dispatch = state.get("last_dispatch")
    if not last_dispatch:
        return False
    try:
        last_dt = datetime.fromisoformat(last_dispatch)
        delta = (datetime.now() - last_dt).total_seconds()
        return delta < (DEBOUNCE_MINUTES * 60)
    except (ValueError, TypeError):
        return False


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MOA Reservation Orchestrator — change detection for BBG events"
    )
    parser.add_argument("--force", action="store_true", help="Force dispatch regardless of changes")
    parser.add_argument("--quiet", action="store_true", help="Suppress all output")
    parser.add_argument("--reset", action="store_true", help="Reset state file to fresh")
    parser.add_argument("--event", type=str, default=None, help="Check specific event date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Reset if requested
    if args.reset:
        save_state({"events": {}, "last_check": None, "stripe_last_pi": None, "stripe_payment_count": 0})
        if not args.quiet:
            print(json.dumps({"changed": False, "action": "reset", "message": "State file reset"}))
        return 0

    # Load current state
    state = load_state()
    state["last_check"] = datetime.now().isoformat()

    # Check debounce
    if should_debounce(state) and not args.force:
        save_state(state)
        return 0  # silent — too soon

    # Load reservations
    reservations = load_json(RES_FILE)
    if not reservations:
        save_state(state)
        return 0  # no data, nothing to do

    # Detect reservation changes
    res_changed, new_res_count, new_names, events_dict, changed_dates = analyze_reservations(
        reservations, state, args.event
    )

    # Detect payment changes
    pay_changed, new_pay_count, new_pis, all_payments = analyze_payments(state)

    # Force mode
    if args.force:
        res_changed = True
        pay_changed = True
        if not changed_dates:
            # Force on today's date
            today_str = date.today().isoformat()
            changed_dates = [today_str]

    # Determine overall change
    overall_changed = res_changed or pay_changed

    if not overall_changed:
        # No changes, update state and exit silently
        save_state(state)
        if args.quiet:
            return 0
        # Even on no-change, output nothing (silent is the default)
        return 0

    # Build output
    result = {
        "changed": True,
        "timestamp": datetime.now().isoformat(),
        "source": "CC_resy_moa.py",
        "action": "dispatch_resy",
        "reservations": {
            "changed": res_changed,
            "new_count": new_res_count,
            "new_names": new_names,
        },
        "payments": {
            "changed": pay_changed,
            "new_count": new_pay_count,
            "new_ids": new_pis,
            "total_count": len(all_payments),
        },
        "events": changed_dates,
    }

    # Update state
    state["last_dispatch"] = datetime.now().isoformat()
    state["stripe_last_pi"] = all_payments[0]["pi_id"] if all_payments else state.get("stripe_last_pi")
    state["stripe_payment_count"] = len(all_payments)

    for edate, entries in events_dict.items():
        if edate not in state["events"]:
            state["events"][edate] = {}
        state["events"][edate]["reservation_hash"] = compute_hash(entries)
        state["events"][edate]["reservation_count"] = len(entries)
        state["events"][edate]["reservation_ids"] = [r.get("id") for r in entries if r.get("id")]
        state["events"][edate]["last_dispatch"] = datetime.now().isoformat()

    save_state(state)

    # Output
    if not args.quiet:
        print(json.dumps(result, indent=2))

    return 1  # exit 1 = changes detected


if __name__ == "__main__":
    sys.exit(main())
