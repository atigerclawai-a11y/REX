#!/usr/bin/env python3
"""
CC_drive_fallback.py — Drive Failure Fallback for GOJ Document Generation
═══════════════════════════════════════════════════════════════════════════
When Google Drive is unreachable during document generation, this module
checks the local DB for recent sync data to determine if it's safe to
proceed with stale data or if generation must abort.

Rules:
  - If DB has sync data <24h old → proceed WITH WARNING
  - If DB has sync data ≥24h old → ABORT (don't generate stale docs)
  - If DB has NO sync data → ABORT

Usage:
  from CC_drive_fallback import check_drive_fallback, FallbackResult

  result = check_drive_fallback()
  if result.can_proceed:
      print(f"Proceeding with warning: data is {result.age_hours:.1f}h old")
  else:
      print(f"ABORT: {result.reason}")
      sys.exit(1)
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional


# ── Paths ───────────────────────────────────────────────────────────
DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"


@dataclass
class FallbackResult:
    """Result of drive fallback check."""
    can_proceed: bool          # True if we can use DB data
    reason: str                # Human-readable explanation
    last_sync: Optional[datetime] = None  # Timestamp of last sync
    age_hours: float = 0.0     # Hours since last sync
    warning: str = ""          # Warning message if proceeding with stale data


def check_drive_fallback(
    db_path: Optional[Path] = None,
    max_age_hours: int = 24,
) -> FallbackResult:
    """
    Check whether DB has recent enough data to fall back on when Drive is down.

    Checks the MAX(last_sync) timestamp across the clients table, as well
    as any sync_log table if it exists.

    Args:
        db_path: Path to auth_tracker.db (default: standard path)
        max_age_hours: Maximum age of sync data to consider usable (default: 24)

    Returns:
        FallbackResult with can_proceed, reason, and timing info
    """
    db = db_path or DB_PATH

    if not db.exists():
        return FallbackResult(
            can_proceed=False,
            reason=f"Database not found at {db}",
        )

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)

    try:
        # Strategy 1: Check sync_log table
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='sync_log'
        """)
        has_sync_log = cursor.fetchone() is not None

        last_sync = None

        if has_sync_log:
            cursor = conn.execute("""
                SELECT MAX(synced_at) as last_sync
                FROM sync_log
                WHERE synced_at IS NOT NULL
            """)
            row = cursor.fetchone()
            if row and row["last_sync"]:
                last_sync = datetime.fromisoformat(row["last_sync"])

        # Strategy 2: Check clients.updated_at (many sync ops update this)
        if last_sync is None:
            cursor = conn.execute("""
                SELECT MAX(updated_at) as last_update
                FROM clients
                WHERE updated_at IS NOT NULL
            """)
            row = cursor.fetchone()
            if row and row["last_update"]:
                try:
                    last_sync = datetime.fromisoformat(row["last_update"])
                except (ValueError, TypeError):
                    pass

        # Strategy 3: Check clients.last_sync column directly
        if last_sync is None:
            try:
                cursor = conn.execute("""
                    SELECT MAX(last_sync) as last_sync
                    FROM clients
                    WHERE last_sync IS NOT NULL
                """)
                row = cursor.fetchone()
                if row and row["last_sync"]:
                    try:
                        last_sync = datetime.fromisoformat(row["last_sync"])
                    except (ValueError, TypeError):
                        pass
            except sqlite3.OperationalError:
                pass  # last_sync column might not exist

        # No sync data at all
        if last_sync is None:
            return FallbackResult(
                can_proceed=False,
                reason="No sync data found in DB — cannot generate documents without Drive",
            )

        # Make timezone-aware if not
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)

        delta = now - last_sync
        age_hours = delta.total_seconds() / 3600

        if delta < timedelta(hours=max_age_hours):
            return FallbackResult(
                can_proceed=True,
                reason=f"DB sync data is {age_hours:.1f}h old (<{max_age_hours}h limit)",
                last_sync=last_sync,
                age_hours=age_hours,
                warning=f"⚠️  WARNING: Drive is unreachable. Using cached data from "
                        f"{last_sync.strftime('%Y-%m-%d %H:%M UTC')} "
                        f"({age_hours:.1f}h ago). Documents may be stale.",
            )
        else:
            return FallbackResult(
                can_proceed=False,
                reason=f"Last sync was {age_hours:.1f}h ago (>{max_age_hours}h limit). "
                       f"Refusing to generate stale documents.",
                last_sync=last_sync,
                age_hours=age_hours,
            )

    finally:
        conn.close()


def check_drive_reachable() -> bool:
    """
    Quick check if Google Drive is reachable.

    Returns True if Drive API is responsive, False otherwise.
    """
    try:
        sys.path.insert(0, str(Path.home() / "Desktop" / "REX"))
        from CC_drive_lists import list_drive_files
        files = list_drive_files(max_results=1)
        return True
    except Exception:
        return False


# ── Main ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Check Drive fallback status for GOJ document generation"
    )
    parser.add_argument(
        "--max-age", type=int, default=24,
        help="Maximum age of sync data in hours (default: 24)"
    )
    parser.add_argument(
        "--check-drive", action="store_true",
        help="Also check if Google Drive is currently reachable"
    )
    args = parser.parse_args()

    if args.check_drive:
        reachable = check_drive_reachable()
        status = "✅ REACHABLE" if reachable else "❌ UNREACHABLE"
        print(f"Google Drive: {status}\n")

    result = check_drive_fallback(max_age_hours=args.max_age)

    print(f"Fallback check: {'✅ CAN PROCEED' if result.can_proceed else '❌ ABORT'}")
    print(f"Reason: {result.reason}")

    if result.last_sync:
        print(f"Last sync: {result.last_sync.isoformat()} "
              f"({result.age_hours:.1f}h ago)")

    if result.warning:
        print(f"\n{result.warning}")

    sys.exit(0 if result.can_proceed else 1)
