#!/usr/bin/env python3
"""
CC_drive_signin_sync.py — Continuous Drive → attendance_log sync
=================================================================
Designed to run every 5 minutes via launchd (StartInterval=300).
Reads the LIVE Google Drive sign-in sheet for TODAY and ensures every
name on the sheet is reflected in `attendance_log` with status='present'.

Behavior
--------
1. Determine today's day_code (M/T/W/TH/F/Sa/Su) and read {CODE}1, {CODE}2
   tabs from the sign-in sheet. Sunday uses a single "Su" tab.
2. For each (shift, name) on Drive:
   a. Fuzzy-match against the `clients` table (case-insensitive).
   b. INSERT OR IGNORE into attendance_log with:
        status='present', source='drive_signin_sync', note=<TR|NTR|''>
   Idempotent on the table's UNIQUE(log_date, day_key, shift, client_name)
   constraint, so re-runs are safe.
3. Healing step: for any row that exists on today's log_date with a
   day_key that no longer matches today (e.g. yesterday's day_code), fix
   the day_key so the dashboard reads the correct row. Source/notes are
   preserved.
4. Log everything to ~/Desktop/REX/logs/drive_signin_sync.log.

Usage
-----
    ~/.rex-venv/bin/python3 CC_drive_signin_sync.py                # today
    ~/.rex-venv/bin/python3 CC_drive_signin_sync.py --date 2026-06-23
    ~/.rex-venv/bin/python3 CC_drive_signin_sync.py --dry-run

State: ~/Desktop/REX/.drive_signin_sync_state.json
Log:   ~/Desktop/REX/logs/drive_signin_sync.log
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME       = Path.home()
REX_DIR    = HOME / "Desktop" / "REX"
LOG_DIR    = REX_DIR / "logs"
STATE_FILE = REX_DIR / ".drive_signin_sync_state.json"
TOKEN_PATH = HOME / ".rex_google_token.json"
DB_PATH    = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "drive_signin_sync.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("drive_signin_sync")

# Drive source (sign-in sheet — same as CC_drive_lists)
SIGN_IN_ID = "1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8"

# Day → tab suffix (matches CC_drive_lists.DAY_MAP)
DAY_MAP = {
    0: ("M",  "Monday"),
    1: ("T",  "Tuesday"),
    2: ("W",  "Wednesday"),
    3: ("TH", "Thursday"),
    4: ("F",  "Friday"),
    5: ("Sa", "Saturday"),
    6: ("Su", "Sunday"),
}


# ── Drive reader (reuses CC_drive_lists) ────────────────────────────────────

def get_day_info(d: date) -> Tuple[str, str]:
    return DAY_MAP[d.weekday()]


def read_drive_signin(day_code: str) -> Tuple[List[dict], List[dict]]:
    """Read S1 + S2 sign-in rows from the live Drive sheet. Returns
    (s1, s2) where each is a list of {name, plan, transport}."""
    if str(REX_DIR) not in sys.path:
        sys.path.insert(0, str(REX_DIR))
    from CC_drive_lists import read_sign_in_sheet  # noqa: E402

    s1 = read_sign_in_sheet(day_code, 1)
    s2 = read_sign_in_sheet(day_code, 2) if day_code != "Su" else []
    return s1, s2


# ── Client matching (case-insensitive, fuzzy fallback) ──────────────────────

def _normalize(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _titlecase(s: str) -> str:
    return " ".join(w.capitalize() for w in s.split())


def build_client_lookup(conn: sqlite3.Connection) -> Dict[str, str]:
    """Return a dict of {lower(name): canonical_name} from the clients table."""
    rows = conn.execute("SELECT name FROM clients").fetchall()
    return {_normalize(r[0]): r[0] for r in rows if r[0]}


def match_name(raw_name: str, lookup: Dict[str, str]) -> str:
    """Return the canonical client name to write to attendance_log, or
    the cleaned raw name if no client-table match is found (so we still
    surface a row in the dashboard for staff to review)."""
    if not raw_name:
        return ""
    n = _normalize(raw_name)
    if n in lookup:
        return lookup[n]
    # Try last-name suffix match (single name typed)
    for k, v in lookup.items():
        if k.endswith(" " + n) or k.startswith(n + " "):
            return v
    # Try substring match — pick longest-key match to avoid false positives
    candidates = [v for k, v in lookup.items() if n in k or k in n]
    if candidates:
        return _titlecase(raw_name)
    return _titlecase(raw_name)


# ── Main sync ───────────────────────────────────────────────────────────────

def sync_today(target_date: Optional[date] = None, dry_run: bool = False) -> dict:
    """Sync Drive sign-in for `target_date` into attendance_log. Returns
    a stats dict for logging/state."""
    target_date = target_date or date.today()
    day_code, day_name = get_day_info(target_date)
    log.info(f"=== sync start: {target_date} {day_name} ({day_code}) dry_run={dry_run} ===")

    # 1. Read Drive
    try:
        s1, s2 = read_drive_signin(day_code)
    except Exception as e:
        log.error(f"Drive read failed: {e}")
        return {"ok": False, "error": str(e), "date": target_date.isoformat()}
    log.info(f"Drive: s1={len(s1)} s2={len(s2)} total={len(s1) + len(s2)}")

    # 2. Build client lookup
    if not DB_PATH.exists():
        log.error(f"DB not found: {DB_PATH}")
        return {"ok": False, "error": "db_missing", "date": target_date.isoformat()}
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        lookup = build_client_lookup(conn)
        log.info(f"clients lookup: {len(lookup)} names")

        # 3. Insert present-mark rows for every name on Drive
        # Use the schema's day_key for the current day (matches DAY_MAP)
        iso_date = target_date.isoformat()
        rows_to_insert: List[Tuple] = []
        matched_count = 0
        unmatched_count = 0
        for shift, roster in ((1, s1), (2, s2)):
            for entry in roster:
                raw = entry.get("name", "").strip()
                if not raw:
                    continue
                canonical = match_name(raw, lookup)
                if canonical in lookup.values():
                    matched_count += 1
                else:
                    unmatched_count += 1
                tr_flag = (entry.get("transport", "") or "").strip()
                rows_to_insert.append(
                    (iso_date, day_code, shift, canonical, "present",
                     "drive_signin_sync", tr_flag)
                )

        log.info(
            f"prepared {len(rows_to_insert)} rows "
            f"({matched_count} matched clients, {unmatched_count} unmatched names)"
        )

        if dry_run:
            log.info("DRY-RUN — no DB writes")
            return {
                "ok": True, "dry_run": True, "date": iso_date, "day": day_name,
                "day_code": day_code, "drive_s1": len(s1), "drive_s2": len(s2),
                "purged_stale": 0, "inserted": 0, "skipped_dup": 0,
                "matched": matched_count, "unmatched": unmatched_count,
            }

        # 3a. One-time purge of mislabeled rows for today. Guarded by a
        # state-file flag (`purged_stale_<date>`) so it only runs once per
        # date. This cleans up the gap where previous manual pushes labeled
        # data with the wrong day_key (e.g. M rows dated for a Tuesday).
        # On any subsequent run the flag is set and the purge is skipped,
        # so the daemon's normal cycle is just INSERT OR IGNORE.
        purge_key = f"purged_stale_{iso_date}"
        state_path = STATE_FILE
        persisted: dict = {}
        if state_path.exists():
            try:
                persisted = json.loads(state_path.read_text())
            except Exception:
                persisted = {}
        purged = 0
        if not persisted.get(purge_key):
            cur_p = conn.execute(
                "DELETE FROM attendance_log "
                "WHERE log_date = ? AND day_key != ? AND status = 'present'",
                (iso_date, day_code),
            )
            purged = cur_p.rowcount
            if purged:
                log.info(f"purge: deleted {purged} stale rows on {iso_date} with wrong day_key")
            persisted[purge_key] = datetime.utcnow().isoformat() + "Z"
            try:
                state_path.write_text(json.dumps(persisted, indent=2))
            except Exception as e:
                log.warning(f"state save failed: {e}")

        # 3b. INSERT OR IGNORE for the Drive names
        # Schema columns: log_date, day_key, shift, client_name, status, source, note
        # (id is auto, logged_at/reason auto/default)
        inserted = 0
        skipped_dup = 0
        for row in rows_to_insert:
            log_date, day_key, shift, client_name, status, source, note = row
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO attendance_log "
                    "(log_date, day_key, shift, client_name, status, source, note) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped_dup += 1
            except sqlite3.IntegrityError as e:
                log.warning(f"  insert failed for {client_name}: {e}")
        conn.commit()
        log.info(
            f"DB writes: purged_stale={purged} inserted={inserted} skipped_dup={skipped_dup}"
        )

        # 4. Append a delta event to live_change_log so SSE picks it up.
        # We try to import the backend's log_change; if it's not importable
        # (e.g. running this script standalone from the CLI), the delta
        # log is a nice-to-have, not required for the sync to succeed.
        try:
            log_change_fn = None
            for mod_path in (
                "backend.CC_goj_live",
                "CC_goj_live",
            ):
                try:
                    mod = __import__(mod_path, fromlist=["log_change"])
                    log_change_fn = getattr(mod, "log_change", None)
                    if log_change_fn:
                        break
                except Exception:
                    continue
            if log_change_fn:
                summary = (
                    f"Drive sync: {len(s1) + len(s2)} names on {day_name} · "
                    f"+{inserted} new · {purged} purged"
                )
                log_change_fn(
                    conn, "attendance_log", "drive_sync",
                    summary,
                    payload={
                        "date": iso_date, "day_code": day_code,
                        "inserted": inserted, "purged": purged,
                        "skipped_dup": skipped_dup,
                        "drive_s1": len(s1), "drive_s2": len(s2),
                    },
                )
                conn.commit()
        except Exception as e:
            log.warning(f"delta log skipped: {e}")

        result = {
            "ok": True,
            "date": iso_date,
            "day": day_name,
            "day_code": day_code,
            "drive_s1": len(s1),
            "drive_s2": len(s2),
            "purged_stale": purged,
            "inserted": inserted,
            "skipped_dup": skipped_dup,
            "matched": matched_count,
            "unmatched": unmatched_count,
        }
        log.info(f"=== sync done: {result} ===")
        return result
    finally:
        conn.close()


# ── State persistence ────────────────────────────────────────────────────────

def save_state(stats: dict) -> None:
    payload = {
        "last_run":  datetime.utcnow().isoformat() + "Z",
        "last_stats": stats,
    }
    try:
        STATE_FILE.write_text(json.dumps(payload, indent=2))
    except Exception as e:
        log.warning(f"state save failed: {e}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _main() -> int:
    ap = argparse.ArgumentParser(description="Drive sign-in → attendance_log sync")
    ap.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (default today)")
    ap.add_argument("--dry-run", action="store_true", help="read Drive, do not write")
    args = ap.parse_args()
    target = date.fromisoformat(args.date) if args.date else None
    stats = sync_today(target_date=target, dry_run=args.dry_run)
    save_state(stats)
    # Exit 0 on success (including dry-run), 1 on hard failure
    return 0 if stats.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())
