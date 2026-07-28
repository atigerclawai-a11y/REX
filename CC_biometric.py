#!/usr/bin/env python3
"""CC_biometric.py — PIN-based client verification system (hardware-ready for fingerprint scanners).

Usage:
  python CC_biometric.py --enroll  <client> <PIN>   # Assign PIN to a client
  python CC_biometric.py --verify <client> <PIN>   # Check a client's PIN
  python CC_biometric.py --signin <client> <PIN>   # Verify PIN + log sign-in timestamp
  python CC_biometric.py --list                     # Show all enrolled clients

Hardware-ready: swap _verify_pin() for a fingerprint-SDK callback.
Stores PIN as SHA-256 hash in auth_tracker.db clients.pin_code column.
Logs sign-in events to ~/Desktop/REX/output/biometric_log.csv.
"""

import sqlite3
import argparse
import csv
import os
import sys
import hashlib
from datetime import datetime

DB_PATH = os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db")
LOG_PATH = os.path.expanduser("~/Desktop/REX/output/biometric_log.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pin_hash(pin: str) -> str:
    """Return SHA-256 hex digest of the PIN.

    Hardware-ready: replace body with fingerprint-SDK callback
    that returns the hashed template ID instead.
    """
    return hashlib.sha256(pin.encode()).hexdigest()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Add pin_code column to clients if missing."""
    cur = conn.execute("PRAGMA table_info(clients)")
    have = {row[1] for row in cur.fetchall()}
    if "pin_code" not in have:
        conn.execute("ALTER TABLE clients ADD COLUMN pin_code TEXT")
        conn.commit()


def _open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _get_client(conn, name: str):
    """Fetch a client row by name, or print error and exit."""
    row = conn.execute(
        "SELECT client_id, name, pin_code, active FROM clients WHERE name = ?",
        (name,),
    ).fetchone()
    if not row:
        print(f"Error: client '{name}' not found in database", file=sys.stderr)
        sys.exit(1)
    return row


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_enroll(conn, client: str, pin: str) -> None:
    _get_client(conn, client)  # existence check
    conn.execute(
        "UPDATE clients SET pin_code = ? WHERE name = ?",
        (_pin_hash(pin), client),
    )
    conn.commit()
    print(f"✓ PIN enrolled for '{client}'")


def cmd_verify(conn, client: str, pin: str, quiet: bool = False) -> bool:
    row = _get_client(conn, client)
    if not row["pin_code"]:
        if not quiet:
            print(f"✗ '{client}' has no PIN enrolled — use --enroll first")
        return False
    ok = row["pin_code"] == _pin_hash(pin)
    if not quiet:
        print(f"{'✓' if ok else '✗'} PIN {'verified' if ok else 'mismatch'} for '{client}'")
    return ok


def cmd_signin(conn, client: str, pin: str) -> None:
    if not cmd_verify(conn, client, pin):
        sys.exit(1)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fresh = not os.path.isfile(LOG_PATH)
    with open(LOG_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(["client", "timestamp"])
        w.writerow([client, ts])
    print(f"✓ Sign-in logged for '{client}' at {ts}")


def cmd_list(conn) -> None:
    rows = conn.execute(
        "SELECT name, active FROM clients WHERE pin_code IS NOT NULL ORDER BY name"
    ).fetchall()
    if not rows:
        print("No clients enrolled in biometric authentication.")
        return
    print(f"{'Client':<30} {'Active':<8}")
    print("-" * 40)
    for r in rows:
        active = "✓" if r["active"] else "✗"
        print(f"{r['name']:<30} {active:<8}")
    print(f"\n{len(rows)} enrolled client(s)")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "PIN-based client verification — hardware-ready for fingerprint scanners.\n"
            "Uses auth_tracker.db (clients.pin_code) and logs sign-ins to biometric_log.csv."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=DB_PATH,
                        help=f"Path to auth_tracker.db (default: {DB_PATH})")

    # Mutually exclusive command group
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enroll", nargs=2, metavar=("CLIENT", "PIN"),
                       help="Assign a PIN code to a client")
    group.add_argument("--verify", nargs=2, metavar=("CLIENT", "PIN"),
                       help="Check a client's PIN code")
    group.add_argument("--signin", nargs=2, metavar=("CLIENT", "PIN"),
                       help="Verify PIN and log sign-in timestamp")
    group.add_argument("--list", action="store_true",
                       help="Show all clients with enrolled PINs")

    args = parser.parse_args()

    if args.list:
        conn = _open_db(args.db)
        try:
            cmd_list(conn)
        finally:
            conn.close()
        return

    # All other commands need client + pin
    client, pin = args.enroll or args.verify or args.signin
    conn = _open_db(args.db)
    try:
        if args.enroll:
            cmd_enroll(conn, client, pin)
        elif args.verify:
            cmd_verify(conn, client, pin)
        elif args.signin:
            cmd_signin(conn, client, pin)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
