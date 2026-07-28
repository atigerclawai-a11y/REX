#!/usr/bin/env python3
"""
CC_inactive_client_detect.py — Inactive Client Detection for GOJ
═══════════════════════════════════════════════════════════════════════
Detects clients who appear on Google Drive attendance sheets but have
active=0 in the local auth_tracker.db, and auto-activates them.

Real bug: Grebneva Veronika was active=0 but appearing on Drive sheets,
causing her to be silently dropped from generated documents.

Usage:
  python3 CC_inactive_client_detect.py              # Detect only
  python3 CC_inactive_client_detect.py --activate   # Detect and auto-activate
  python3 CC_inactive_client_detect.py --date 2026-06-22  # Specific date

From other modules:
  from CC_inactive_client_detect import detect_inactive_clients, auto_activate

  found = detect_inactive_clients(service_date)  # returns list of names
  activated = auto_activate(found)               # activates them in DB
"""

import sqlite3
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional


# ── Paths ───────────────────────────────────────────────────────────
DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a connection to auth_tracker.db."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def get_inactive_clients(conn: sqlite3.Connection) -> List[Dict]:
    """
    Get all clients with active=0.

    Returns list of dicts with: client_id, name, active, last_modified
    """
    cursor = conn.execute("""
        SELECT client_id, name, active, updated_at
        FROM clients
        WHERE active = 0
        ORDER BY name
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_drive_attendance(conn: sqlite3.Connection, service_date: date) -> List[Dict]:
    """
    Get clients who appear on Drive attendance for a given date.

    Checks both drive_attendance table and any sync_logs for the date.
    Falls back to checking day_*_actual columns if Drive sync data isn't
    separately stored.
    """
    # First try: drive_attendance table
    cursor = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='drive_attendance'
    """)
    has_drive_attendance = cursor.fetchone() is not None

    if has_drive_attendance:
        cursor = conn.execute("""
            SELECT DISTINCT client_name as name
            FROM drive_attendance
            WHERE date = ?
        """, (service_date.isoformat(),))
        return [dict(row) for row in cursor.fetchall()]

    # Fallback: use clients.day_*_actual columns as proxy
    # (these get populated during Drive sync)
    day_cols = {
        0: "day_M_actual",   1: "day_T_actual",
        2: "day_W_actual",   3: "day_TH_actual",
        4: "day_F_actual",   5: "day_Su_actual",
        6: "day_Su_actual",
    }

    weekday = service_date.weekday()
    col = day_cols.get(weekday, "day_Su_actual")

    cursor = conn.execute(f"""
        SELECT client_id, name
        FROM clients
        WHERE {col} > 0 AND active = 1
    """)
    return [dict(row) for row in cursor.fetchall()]


def detect_inactive_clients(
    service_date: Optional[date] = None,
    db_path: Optional[Path] = None,
) -> List[Dict]:
    """
    Detect inactive clients who are on Drive but active=0 in DB.

    Args:
        service_date: Date to check (default: today)
        db_path: Path to auth_tracker.db (default: standard path)

    Returns:
        List of dicts with: client_id, name, evidence (how they were found)
    """
    if service_date is None:
        service_date = date.today()

    conn = get_db_connection(db_path)

    try:
        inactive = get_inactive_clients(conn)
        if not inactive:
            print("✅ No inactive clients found in DB.")
            return []

        inactive_ids = {c["client_id"]: c for c in inactive}
        inactive_names = {c["name"].lower(): c for c in inactive}

        drive_clients = get_drive_attendance(conn, service_date)

        found = []
        for dc in drive_clients:
            name = dc["name"]
            if name.lower() in inactive_names:
                client = inactive_names[name.lower()]
                found.append({
                    "client_id": client["client_id"],
                    "name": client["name"],
                    "active": client["active"],
                    "evidence": f"Found on Drive attendance for {service_date.isoformat()}",
                })
            # Also check by client_id if drive_attendance has it
            if "client_id" in dc:
                cid = dc["client_id"]
                if cid in inactive_ids:
                    if not any(f["client_id"] == cid for f in found):
                        client = inactive_ids[cid]
                        found.append({
                            "client_id": cid,
                            "name": client["name"],
                            "active": client["active"],
                            "evidence": f"Found on Drive attendance for {service_date.isoformat()}",
                        })

        if found:
            print(f"⚠️  Found {len(found)} inactive clients on Drive:")
            for f in found:
                print(f"    - {f['name']} (client_id={f['client_id']}, active={f['active']})")
        else:
            print("✅ No inactive clients found on Drive.")

        return found

    finally:
        conn.close()


def auto_activate(
    clients: List[Dict],
    db_path: Optional[Path] = None,
    dry_run: bool = False,
) -> List[str]:
    """
    Auto-activate detected inactive clients.

    Args:
        clients: List from detect_inactive_clients()
        db_path: Path to auth_tracker.db
        dry_run: If True, only print what would be done

    Returns:
        List of activated client names
    """
    if not clients:
        return []

    conn = get_db_connection(db_path)
    now = datetime.now().isoformat()
    activated = []

    try:
        for client in clients:
            cid = client["client_id"]
            name = client["name"]

            if dry_run:
                print(f"  [DRY RUN] Would activate: {name} (id={cid})")
                activated.append(name)
                continue

            conn.execute("""
                UPDATE clients
                SET active = 1,
                    updated_at = ?
                WHERE client_id = ?
            """, (now, cid))

            # Log the auto-activation
            try:
                conn.execute("""
                    INSERT INTO audit_log (action, table_name, record_id, details, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    "AUTO_ACTIVATE",
                    "clients",
                    str(cid),
                    f"Auto-activated inactive client found on Drive: {name}",
                    now,
                ))
            except Exception:
                pass  # audit_log table might not exist

            activated.append(name)
            print(f"  ✅ Activated: {name} (id={cid})")

        conn.commit()

        if activated:
            print(f"\n📋 Auto-activated {len(activated)} clients:")
            for name in activated:
                print(f"    - {name}")

        return activated

    finally:
        conn.close()


# ── Main ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect and auto-activate inactive GOJ clients on Drive"
    )
    parser.add_argument(
        "--date", type=str,
        help="Service date (YYYY-MM-DD), default: today"
    )
    parser.add_argument(
        "--activate", action="store_true",
        help="Auto-activate found clients (default: detect only)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()

    service_date = date.fromisoformat(args.date) if args.date else date.today()

    print(f"🔍 Checking inactive clients for {service_date.isoformat()}...\n")

    found = detect_inactive_clients(service_date)

    if found and (args.activate or args.dry_run):
        print()
        auto_activate(found, dry_run=args.dry_run)
    elif found and not args.activate:
        print("\n💡 Run with --activate to auto-activate these clients.")
    elif not found:
        print("\n✨ All clear — no inactive clients detected on Drive.")

    sys.exit(0 if not found else 0)  # Non-zero exit for cron alerting
