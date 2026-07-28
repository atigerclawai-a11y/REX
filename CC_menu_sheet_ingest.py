#!/usr/bin/env python3
"""
CC_menu_sheet_ingest.py — GOJ Menu Sheet → client_menus Ingestion
=================================================================
Reads the two live Google Sheets menu sources (first-shift and second-shift)
via the Sheets API and INSERTs rows into client_menus for the CURRENT and
NEXT service week.

Usage:
    python3 CC_menu_sheet_ingest.py --dry-run       # show what would be inserted
    python3 CC_menu_sheet_ingest.py                 # actually insert
    python3 CC_menu_sheet_ingest.py --week 2026-06-09   # explicit week_start override

Rules:
  - INSERT-only; never updates or deletes existing rows.
  - Dedup: SELECT before INSERT on (client_id, week_start, day).
  - source='drive_sheet', confidence=0.95
  - Fuzzy name matching via difflib SequenceMatcher, cutoff 0.55,
    last-name boost applied.
  - If >50% of sheet names are unmatched, STOP and report (don't insert garbage).
  - NO OCR, NO cloud AI calls — Sheets API read only.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

HOME      = Path.home()
TOKEN_PATH = HOME / ".rex_google_token.json"
DB_PATH   = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

MENU_SHEETS = {
    "first_shift": {
        "file_id": "1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw",
        "shift_label": "1st",
    },
    "second_shift": {
        "file_id": "18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0",
        "shift_label": "2nd",
    },
}

# Tab name patterns: the date tabs are named like "6/9 T", "6/8 M", "6/15 М" (Cyrillic M)
# Map day abbreviation (as appears in tab suffix) to client_menus 'day' column
# The tab header row 2 says "menu for the date 6/9 Tusday, 1st shift"
# Column layout for weekday tabs (A..J):
#   A=Name  B=seq#  C=Салаты(salad)  D=Супы(soup)  E=Главное(main)  F=Гарнир(side)
#   G=combined  H=supplier  I=alt_salad  J=count
# Column layout for Saturday "S" tabs:
#   A=Name  B=seq#  C=Супы(soup)  D=Главное(main) — NO salad column, NO side column
#   (Saturday menus have a simplified layout)

DAY_COL_MAP = {
    # weekday tabs
    "M":  {"salad": 2, "soup": 3, "main": 4, "side": 5},  # 0-indexed cols
    "T":  {"salad": 2, "soup": 3, "main": 4, "side": 5},
    "W":  {"salad": 2, "soup": 3, "main": 4, "side": 5},
    "TH": {"salad": 2, "soup": 3, "main": 4, "side": 5},
    "F":  {"salad": 2, "soup": 3, "main": 4, "side": 5},
    # Saturday tab: col C=soup, D=main, no salad/side
    "S":  {"salad": None, "soup": 2, "main": 3, "side": None},
}

# Tab suffix → day key
# The suffix is the part after the date number in the tab name
TAB_SUFFIX_TO_DAY = {
    " M":   "M",
    " М":   "M",   # Cyrillic М — same key
    " T":   "T",
    " W":   "W",
    " TH":  "TH",
    " F":   "F",
    " S":   "S",   # Saturday
}


# ── Google Sheets auth ─────────────────────────────────────────────────────────

def get_sheets_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds)


# ── Roster loading ─────────────────────────────────────────────────────────────

def load_roster(db_path: Path) -> list[dict]:
    """Load active clients from DB."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT client_id, name FROM clients WHERE active = 1"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── Fuzzy name matching ────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _score(sheet_name: str, roster_name: str) -> float:
    sn = _normalize(sheet_name)
    rn = _normalize(roster_name)
    base = SequenceMatcher(None, sn, rn).ratio()
    # Last-name boost: if first token of each matches exactly, +0.1
    s_parts = sn.split()
    r_parts = rn.split()
    if s_parts and r_parts and s_parts[0] == r_parts[0]:
        base = min(1.0, base + 0.10)
    return base


def match_name(sheet_name: str, roster: list[dict], cutoff: float = 0.55
               ) -> Optional[dict]:
    """Return best-matching roster entry or None."""
    best_score = 0.0
    best_client = None
    for client in roster:
        sc = _score(sheet_name, client["name"])
        if sc > best_score:
            best_score = sc
            best_client = client
    if best_score >= cutoff:
        return best_client
    return None


# ── Tab parsing ────────────────────────────────────────────────────────────────

def parse_tab_name(tab_title: str):
    """
    Parse a tab name like "6/9 T", "6/15 М", "6/14 S" into
    (date_obj, day_key) or return None if not a per-day menu tab.
    Assumes year 2026.
    """
    title = tab_title.strip()
    # Must start with a digit (date), not 'Menu', 'Jun', 'Jan', etc.
    if not title or not title[0].isdigit():
        return None

    day_key = None
    for suffix, dk in TAB_SUFFIX_TO_DAY.items():
        if title.endswith(suffix):
            day_key = dk
            date_part = title[: -len(suffix)].strip()
            break
    if day_key is None:
        return None

    # date_part like "6/9" or "6/15"
    try:
        parts = date_part.split("/")
        month = int(parts[0])
        day   = int(parts[1])
        d     = date(2026, month, day)
    except Exception:
        return None

    return d, day_key


def get_monday(d: date) -> date:
    """Return Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def fetch_tab_rows(svc, file_id: str, tab_title: str) -> list[list[str]]:
    """Fetch up to 250 rows (A:J) from a tab."""
    resp = svc.spreadsheets().values().get(
        spreadsheetId=file_id,
        range=f"'{tab_title}'!A1:J250",
    ).execute()
    return resp.get("values", [])


def _cell(row: list, idx: Optional[int]) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def parse_client_rows(rows: list[list[str]], day_key: str) -> list[dict]:
    """
    From raw sheet rows, extract per-client menu dicts.
    Header is row index 3 (0-based), data starts at row index 4.
    Skip rows where:
      - col A is empty
      - col A looks like a header (contains "Name" or "menu for")
      - col A col B looks like a date note with no dish data (e.g. a footer line)
    """
    col = DAY_COL_MAP.get(day_key, DAY_COL_MAP["M"])
    result = []
    for row in rows[4:]:  # skip rows 0-3 (title/header)
        if not row:
            continue
        name = row[0].strip() if row else ""
        if not name:
            continue
        # Skip footer/separator rows
        name_lower = name.lower()
        if any(kw in name_lower for kw in ("name", "menu for", "garden of joy", "olimp")):
            continue
        # A row is a valid client row if name looks like a person name
        # (contains a space and is mostly Latin/Cyrillic letters)
        if len(name) < 3:
            continue

        salad = _cell(row, col["salad"])
        soup  = _cell(row, col["soup"])
        main  = _cell(row, col["main"])
        side  = _cell(row, col["side"])

        # Skip rows where all dish fields are empty (vacationing notes with no food)
        if not any([salad, soup, main, side]):
            continue

        result.append({
            "sheet_name": name,
            "salad": salad or None,
            "soup":  soup  or None,
            "main":  main  or None,
            "side":  side  or None,
        })
    return result


# ── Week targeting ─────────────────────────────────────────────────────────────

def target_weeks(explicit_monday: Optional[date] = None) -> list[date]:
    """Return [current_week_monday, next_week_monday]."""
    if explicit_monday:
        return [explicit_monday, explicit_monday + timedelta(weeks=1)]
    today = date.today()
    # next business day
    nbd = today + timedelta(days=1)
    while nbd.weekday() == 6:  # skip Sunday
        nbd += timedelta(days=1)
    current = get_monday(nbd)
    return [current, current + timedelta(weeks=1)]


# ── Main ingest logic ─────────────────────────────────────────────────────────

def run_ingest(dry_run: bool, explicit_monday: Optional[date] = None,
               db_path: Path = DB_PATH):
    weeks = target_weeks(explicit_monday)
    print(f"\nTarget weeks: {[str(w) for w in weeks]}")
    print(f"Mode: {'DRY-RUN (no DB writes)' if dry_run else 'LIVE INSERT'}\n")

    svc = get_sheets_service()
    roster = load_roster(db_path)
    print(f"Roster loaded: {len(roster)} active clients\n")

    # Load existing (client_id, week_start, day) dedup keys
    con = sqlite3.connect(str(db_path))
    existing = set(
        con.execute(
            "SELECT client_id, week_start, day FROM client_menus"
        ).fetchall()
    )
    print(f"Existing client_menus rows: {len(existing)}\n")

    weeks_set = {w.isoformat() for w in weeks}

    all_pending   = []   # list of dicts ready to insert
    skipped_match = []   # (sheet_name, tab, reason)
    skipped_dedup = 0

    total_sheet_names = 0
    matched_count     = 0

    for shift_key, sheet_info in MENU_SHEETS.items():
        file_id     = sheet_info["file_id"]
        shift_label = sheet_info["shift_label"]

        # Get tab list
        meta = svc.spreadsheets().get(spreadsheetId=file_id).execute()
        tabs = [s["properties"]["title"] for s in meta["sheets"]]
        print(f"Sheet: {shift_key} ({file_id})")
        print(f"  All tabs: {tabs}\n")

        for tab in tabs:
            parsed = parse_tab_name(tab)
            if parsed is None:
                continue  # not a per-day menu tab

            tab_date, day_key = parsed
            week_start = get_monday(tab_date)

            if week_start.isoformat() not in weeks_set:
                continue  # not a target week

            # Fetch rows
            rows = fetch_tab_rows(svc, file_id, tab)
            clients_in_tab = parse_client_rows(rows, day_key)
            total_sheet_names += len(clients_in_tab)

            unmatched_in_tab = 0
            for entry in clients_in_tab:
                client = match_name(entry["sheet_name"], roster)
                if client is None:
                    skipped_match.append((entry["sheet_name"], tab, shift_key, "no_match"))
                    unmatched_in_tab += 1
                    continue
                matched_count += 1

                dedup_key = (client["client_id"], week_start.isoformat(), day_key)
                if dedup_key in existing:
                    skipped_dedup += 1
                    continue

                all_pending.append({
                    "client_id":   client["client_id"],
                    "client_name": client["name"],
                    "week_start":  week_start.isoformat(),
                    "day":         day_key,
                    "salad":       entry["salad"],
                    "soup":        entry["soup"],
                    "main":        entry["main"],
                    "side":        entry["side"],
                    "confidence":  0.95,
                    "source":      "drive_sheet",
                    "notes":       f"sheet={shift_key} tab={tab}",
                    "_sheet_name": entry["sheet_name"],  # for dry-run display
                })
                # Mark as pending so duplicate tabs don't re-insert
                existing.add(dedup_key)

            tab_match_pct = (
                (len(clients_in_tab) - unmatched_in_tab) / len(clients_in_tab) * 100
                if clients_in_tab else 100
            )
            print(f"  Tab '{tab}' ({day_key} week={week_start}): "
                  f"{len(clients_in_tab)} rows, "
                  f"{len(clients_in_tab)-unmatched_in_tab} matched "
                  f"({tab_match_pct:.0f}%), "
                  f"{unmatched_in_tab} unmatched")

    # ── Match rate guard ──────────────────────────────────────────────────────
    overall_match_pct = (matched_count / total_sheet_names * 100
                         if total_sheet_names else 0)
    print(f"\nOverall match rate: {matched_count}/{total_sheet_names} "
          f"= {overall_match_pct:.1f}%")
    print(f"Pending inserts: {len(all_pending)}")
    print(f"Skipped (dedup): {skipped_dedup}")
    print(f"Skipped (no match): {len(skipped_match)}")

    if total_sheet_names > 0 and overall_match_pct < 50:
        print("\n⛔  ABORT: <50% match rate — not inserting (garbage protection).")
        print("    Unmatched sample:")
        for nm, tab, sh, _ in skipped_match[:20]:
            print(f"      '{nm}' in {sh}/{tab}")
        con.close()
        return

    # ── Dry-run output ────────────────────────────────────────────────────────
    if dry_run:
        # Summary per week/day
        from collections import Counter
        c = Counter((r["week_start"], r["day"]) for r in all_pending)
        print("\n--- DRY-RUN: would insert per (week_start, day) ---")
        for (ws, d), cnt in sorted(c.items()):
            print(f"  {ws}  {d:>2}  → {cnt} rows")

        print("\n--- DRY-RUN: 5 sample rows (name truncated) ---")
        seen_per_sheet: dict = {}
        samples = []
        for r in all_pending:
            key = (r["week_start"], r["day"], r["notes"])
            if len(samples) < 5 or key not in seen_per_sheet:
                seen_per_sheet[key] = True
                samples.append(r)
            if len(samples) >= 5:
                break

        for r in samples[:5]:
            raw = r["_sheet_name"]
            parts = raw.split()
            trunc = (parts[0][0] + ". " + parts[-1]) if len(parts) > 1 else raw
            print(f"  {trunc:20s}  week={r['week_start']}  {r['day']}  "
                  f"main={r['main']}  soup={r['soup']}  "
                  f"salad={r['salad']}  side={r['side']}")

        print(f"\nTotal would insert: {len(all_pending)}")

        if skipped_match:
            print(f"\n--- Unmatched names ({len(skipped_match)}) ---")
            for nm, tab, sh, _ in skipped_match[:30]:
                print(f"  '{nm}' in {sh}/{tab}")
            if len(skipped_match) > 30:
                print(f"  ... and {len(skipped_match)-30} more")
        con.close()
        return

    # ── Live insert ───────────────────────────────────────────────────────────
    inserted = 0
    now_ts = __import__("datetime").datetime.utcnow().isoformat()
    with con:
        for r in all_pending:
            con.execute("""
                INSERT INTO client_menus
                  (client_id, client_name, week_start, day,
                   salad, soup, main, side,
                   confidence, source, notes,
                   source_pdf, page_num,
                   created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r["client_id"], r["client_name"], r["week_start"], r["day"],
                r["salad"], r["soup"], r["main"], r["side"],
                r["confidence"], r["source"], r["notes"],
                None, None,
                now_ts, now_ts,
            ))
            inserted += 1

    con.close()
    print(f"\n✅ Inserted {inserted} rows into client_menus.")
    if skipped_match:
        print(f"   {len(skipped_match)} sheet names had no roster match — skipped.")
        print("   Unmatched sample (first 20):")
        for nm, tab, sh, _ in skipped_match[:20]:
            print(f"     '{nm}' in {sh}/{tab}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Ingest GOJ menu sheets into client_menus")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be inserted, don't write to DB")
    p.add_argument("--week", metavar="YYYY-MM-DD",
                   help="Explicit week_start (must be a Monday); "
                        "default = current + next week")
    p.add_argument("--db", default=str(DB_PATH),
                   help="Path to auth_tracker.db")
    args = p.parse_args()

    monday = None
    if args.week:
        from datetime import date
        monday = date.fromisoformat(args.week)
        if monday.weekday() != 0:
            print(f"ERROR: --week {args.week} is not a Monday "
                  f"(weekday={monday.weekday()})")
            sys.exit(1)

    run_ingest(
        dry_run=args.dry_run,
        explicit_monday=monday,
        db_path=Path(args.db),
    )


if __name__ == "__main__":
    main()
