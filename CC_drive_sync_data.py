#!/usr/bin/env python3
"""
CC_drive_sync_data.py — Sync Google Drive → local JSON data files
══════════════════════════════════════════════════════════════════
Populates the two files that generate_tomorrow.py needs:

  ~/Documents/goj files/clients.json
  ~/Documents/goj files/data/GOJ_Menu_Orders.json

Run this before generating daily PDFs. Safe to re-run: never deletes
existing menu data, only adds/updates.

Usage:
  python3 CC_drive_sync_data.py                  # sync next 14 days
  python3 CC_drive_sync_data.py --dry-run        # parse only, no writes
  python3 CC_drive_sync_data.py --days 7         # sync next 7 days
  python3 CC_drive_sync_data.py --date 2026-07-01 # anchor date
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import os
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
HOME        = Path.home()
REX_DIR     = HOME / "Desktop" / "REX"
LOG_DIR     = REX_DIR / "logs"
GOJ_DIR     = HOME / "Documents" / "goj files"
CLIENTS_JSON = GOJ_DIR / "clients.json"
DATA_DIR    = GOJ_DIR / "data"
MENU_JSON   = DATA_DIR / "GOJ_Menu_Orders.json"
DB_PATH     = GOJ_DIR / "dashboard" / "auth_tracker.db"

LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "drive_sync_data.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("drive_sync_data")

# ── Import drive helpers from CC_drive_lists.py ────────────────────────────────
sys.path.insert(0, str(REX_DIR))
from CC_drive_lists import (
    read_sign_in_sheet,
    read_menu_sheet,
    get_services,
    MENU_S1_ID,
    MENU_S2_ID,
    DAY_MAP,
)

# ── Day codes for sign-in tabs ─────────────────────────────────────────────────
# All sign-in tabs to read (each has shift 1 and shift 2, except Su)
SIGN_IN_DAYS = ["M", "T", "W", "TH", "F", "Sa"]   # GOJ is closed Sunday
# "Su" tab exists but GOJ is effectively closed — skip

# Clients that must NEVER appear on transport/driver lists (hard rule)
TRANSPORT_BLOCKLIST = {"Larry"}


# ══════════════════════════════════════════════════════════════════════════════
# PART A: BUILD clients.json
# ══════════════════════════════════════════════════════════════════════════════

def _larry_filter(name: str) -> bool:
    """Return True if this client should be excluded from all lists."""
    first = name.strip().split()[-1] if name.strip() else ""  # last word = first name (LastName First format)
    # Also check first word as some records are First Last
    first_word = name.strip().split()[0] if name.strip() else ""
    return first.lower() == "larry" or first_word.lower() == "larry"


def _load_db_supplement() -> dict:
    """
    Load plan_canonical and transportation from auth_tracker.db for fuzzy matching.
    Returns {normalized_name: {plan, transportation}} keyed by lowercase name.
    """
    if not DB_PATH.exists():
        log.warning(f"DB not found at {DB_PATH} — skipping plan/transport supplement")
        return {}

    import sqlite3
    import difflib

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, plan_canonical, plan_raw, transportation FROM clients WHERE active=1"
        ).fetchall()
        conn.close()
        return {
            row["name"].strip(): {
                "plan": row["plan_canonical"] or row["plan_raw"] or "",
                "transportation": row["transportation"] or "",
                "name_lower": row["name"].strip().lower(),
            }
            for row in rows
            if row["name"]
        }
    except Exception as e:
        log.warning(f"DB supplement load failed: {e}")
        return {}


def _fuzzy_lookup(name: str, db_map: dict, threshold: float = 0.80) -> dict | None:
    """Find best fuzzy match in db_map for the given name. Returns db row or None."""
    import difflib
    name_lower = name.strip().lower()
    # Exact match first
    for db_name, row in db_map.items():
        if db_name.lower() == name_lower:
            return row
    # Fuzzy
    best_score, best_row = 0.0, None
    for db_name, row in db_map.items():
        score = difflib.SequenceMatcher(None, name_lower, db_name.lower()).ratio()
        if score > best_score:
            best_score, best_row = score, row
    if best_score >= threshold:
        return best_row
    return None


def build_clients_json(dry_run: bool = False) -> dict:
    """
    Read all sign-in tabs from Drive and merge into clients.json format.

    clients.json format:
    {
      "LastName FirstName": {
        "active": true,
        "days": {"M": {"actual": 1}, "TH": {"actual": 1}},
        "shift": 1,           # primary shift (lowest shift number seen)
        "plan": "Anthem",
        "ch": "",
        "transportation": "TR"
      }
    }

    Transport flag comes from the sign-in sheet directly (most reliable).
    Plan comes from DB fuzzy match when available; falls back to sign-in sheet value.
    Larry is permanently excluded.
    """
    log.info("=== Building clients.json from Drive sign-in tabs ===")

    # Load existing clients.json if present (preserve manual overrides)
    existing: dict = {}
    if CLIENTS_JSON.exists():
        try:
            existing = json.loads(CLIENTS_JSON.read_text(encoding="utf-8"))
            log.info(f"  Loaded existing clients.json: {len(existing)} entries")
        except Exception as e:
            log.warning(f"  Could not load existing clients.json: {e}")

    # Load DB supplement for plan/transport enrichment
    db_map = _load_db_supplement()
    log.info(f"  DB supplement: {len(db_map)} active clients")

    # Accumulate: name -> {days set, shift set, plan, transport}
    merged: dict[str, dict] = {}

    for day_code in SIGN_IN_DAYS:
        for shift in [1, 2]:
            try:
                clients = read_sign_in_sheet(day_code, shift)
                log.info(f"  {day_code}{shift}: {len(clients)} clients")
            except Exception as e:
                log.warning(f"  {day_code}{shift}: read failed — {e}")
                continue

            for c in clients:
                name = c["name"].strip()
                if not name:
                    continue

                # Hard block: Larry never on any list
                if _larry_filter(name):
                    log.info(f"  BLOCKED (Larry rule): {name}")
                    continue

                plan_from_sheet = c.get("plan", "").strip()
                transport_from_sheet = c.get("transport", "").strip()

                # Normalize transport to "TR" or ""
                transport = "TR" if transport_from_sheet.upper() in ("TR", "T/R", "TR VIS", "VIS TR") else transport_from_sheet

                if name not in merged:
                    merged[name] = {
                        "days": {},
                        "shifts": set(),
                        "plan": plan_from_sheet,
                        "transportation": transport,
                    }

                merged[name]["days"][day_code] = {"actual": shift}
                merged[name]["shifts"].add(shift)

                # Prefer non-empty plan
                if not merged[name]["plan"] and plan_from_sheet:
                    merged[name]["plan"] = plan_from_sheet

                # Transport: if any tab shows TR, mark as TR
                if transport == "TR":
                    merged[name]["transportation"] = "TR"

    # Enrich with DB fuzzy match (plan_canonical is more reliable than sheet OCR)
    enriched_count = 0
    for name in merged:
        db_row = _fuzzy_lookup(name, db_map)
        if db_row:
            if db_row.get("plan"):
                merged[name]["plan"] = db_row["plan"]
                enriched_count += 1

    log.info(f"  Enriched {enriched_count} clients with DB plan data")

    # Build final dict
    result: dict = {}
    for name, info in merged.items():
        shifts_seen = sorted(info["shifts"])
        primary_shift = shifts_seen[0] if shifts_seen else 1
        result[name] = {
            "active": True,
            "days": info["days"],
            "shift": primary_shift,
            "plan": info["plan"],
            "ch": existing.get(name, {}).get("ch", ""),  # preserve manual ch flag
            "transportation": info["transportation"],
        }

    # Preserve any entries that were in the old clients.json but not in Drive
    # (could be temporarily inactive — keep with active=False)
    for name, old_entry in existing.items():
        if name not in result and old_entry.get("active"):
            result[name] = {**old_entry, "active": False}
            log.info(f"  Preserved (not in Drive, marked inactive): {name}")

    log.info(f"  Total: {len(result)} clients ({sum(1 for v in result.values() if v['active'])} active)")

    if dry_run:
        log.info("  [dry-run] Would write clients.json — not writing")
        sample = list(result.items())[:3]
        for n, v in sample:
            log.info(f"    {n}: days={list(v['days'].keys())} shift={v['shift']} plan={v['plan']} tr={v['transportation']}")
        return result

    CLIENTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CLIENTS_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"  Written: {CLIENTS_JSON}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PART B: BUILD GOJ_Menu_Orders.json
# ══════════════════════════════════════════════════════════════════════════════

def build_menu_orders(anchor: date, days: int = 14, dry_run: bool = False) -> dict:
    """
    Read menu tabs for the next `days` days (skipping Sundays) and merge
    into GOJ_Menu_Orders.json.

    GOJ_Menu_Orders.json format:
    {
      "2026-06-25": {
        "Adyan Ludmila": {
          "1": {"salad": "Vinaigrette", "soup": "Borsch", "main": "Chicken", "side": "Rice"}
        }
      }
    }

    Shift 1 reads from MENU_S1_ID, shift 2 from MENU_S2_ID.
    Existing weeks are preserved — only adds/updates.
    """
    log.info(f"=== Building GOJ_Menu_Orders.json: {days} days from {anchor} ===")

    # Load existing orders
    existing: dict = {}
    if MENU_JSON.exists():
        try:
            existing = json.loads(MENU_JSON.read_text(encoding="utf-8"))
            log.info(f"  Loaded existing GOJ_Menu_Orders.json: {len(existing)} date entries")
        except Exception as e:
            log.warning(f"  Could not load existing GOJ_Menu_Orders.json: {e}")

    days_synced = 0
    clients_found = set()
    menus_loaded = 0
    errors = 0

    # Map shift number to sheet ID
    shift_sheet = {1: MENU_S1_ID, 2: MENU_S2_ID}

    target = anchor
    for _ in range(days * 2):  # iterate more than `days` to skip Sundays
        if days_synced >= days:
            break

        # Skip Sundays (weekday 6)
        if target.weekday() == 6:
            target += timedelta(days=1)
            continue

        date_iso = target.isoformat()

        if date_iso not in existing:
            existing[date_iso] = {}

        for shift, sheet_id in shift_sheet.items():
            shift_key = str(shift)
            try:
                menus = read_menu_sheet(sheet_id, target)
                if menus:
                    for name, order in menus.items():
                        if not name:
                            continue
                        # Larry block
                        if _larry_filter(name):
                            continue
                        if name not in existing[date_iso]:
                            existing[date_iso][name] = {}
                        existing[date_iso][name][shift_key] = {
                            "salad": order.get("salad", ""),
                            "soup":  order.get("soup", ""),
                            "main":  order.get("main", ""),
                            "side":  order.get("side", ""),
                        }
                        clients_found.add(name)
                        menus_loaded += 1
            except Exception as e:
                err_str = str(e)
                # 404-style errors = tab doesn't exist = no menu for that date/shift; skip silently
                if "Unable to parse range" in err_str or "404" in err_str or "invalid" in err_str.lower():
                    log.debug(f"  {date_iso} S{shift}: no tab — {err_str[:60]}")
                else:
                    log.warning(f"  {date_iso} S{shift}: error — {err_str[:100]}")
                    errors += 1

        days_synced += 1
        target += timedelta(days=1)

    log.info(f"  Days synced: {days_synced} | Unique clients: {len(clients_found)} | Menu entries: {menus_loaded} | Errors: {errors}")

    if dry_run:
        log.info("  [dry-run] Would write GOJ_Menu_Orders.json — not writing")
        return existing

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MENU_JSON.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"  Written: {MENU_JSON}")
    return existing


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Sync Google Drive → clients.json + GOJ_Menu_Orders.json")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no file writes")
    parser.add_argument("--days", type=int, default=14, help="Number of days to sync menus for (default: 14)")
    parser.add_argument("--date", type=str, default=None, help="Anchor date YYYY-MM-DD (default: today)")
    parser.add_argument("--clients-only", action="store_true", help="Only sync clients.json")
    parser.add_argument("--menus-only", action="store_true", help="Only sync GOJ_Menu_Orders.json")
    args = parser.parse_args()

    anchor = date.fromisoformat(args.date) if args.date else date.today()
    dry_run = args.dry_run

    log.info("=" * 60)
    log.info(f"CC_drive_sync_data.py starting — anchor={anchor} days={args.days} dry_run={dry_run}")

    ok = True

    if not args.menus_only:
        try:
            build_clients_json(dry_run=dry_run)
        except Exception as e:
            log.error(f"clients.json build FAILED: {e}")
            ok = False

    if not args.clients_only:
        try:
            build_menu_orders(anchor=anchor, days=args.days, dry_run=dry_run)
        except Exception as e:
            log.error(f"GOJ_Menu_Orders.json build FAILED: {e}")
            ok = False

    if ok:
        log.info("=== Sync complete ===")
    else:
        log.error("=== Sync finished with errors (see above) ===")

    # Exit 0 regardless — launchd must not restart on Drive errors
    sys.exit(0)


if __name__ == "__main__":
    main()
