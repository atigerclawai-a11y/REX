#!/usr/bin/env python3
"""
CC_goj_drive_ingest.py — GOJ Live Drive → Dashboard Ingestion Agent
=====================================================================
Watches the LIVE Drive files (shared with atigerclawai@gmail.com) and
transforms them into the proprietary dashboard tables in auth_tracker.db.

Replaces the old folder-based watcher (which was pointed at akhiger's
archived March folder). This agent works by FILE ID, not folder, because
all live sources are individually shared, not in a parent folder.

Source map: CC_DRIVE_SOURCE_MAP_2026-06-08.md

Usage:
    python3 CC_goj_drive_ingest.py              # full ingest pass
    python3 CC_goj_drive_ingest.py --once       # single pass then exit
    python3 CC_goj_drive_ingest.py --dry-run    # parse + show diffs, no DB write
    python3 CC_goj_drive_ingest.py --source sign_in   # only ingest one source
    python3 CC_goj_drive_ingest.py --status     # show last-seen state + exit

State: ~/Desktop/REX/.goj_drive_ingest_state.json
Log:   ~/Desktop/REX/logs/goj_drive_ingest.log
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ─────────────────────────────────────────────────────────────────────

HOME       = Path.home()
REX_DIR    = HOME / "Desktop" / "REX"
LOG_DIR    = REX_DIR / "logs"
STATE_FILE = REX_DIR / ".goj_drive_ingest_state.json"
TOKEN_PATH = HOME / ".rex_google_token.json"
CREDS_PATH = REX_DIR / "google_credentials.json"
DB_PATH    = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "goj_drive_ingest.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("goj_drive_ingest")

# ── Live source registry (from CC_DRIVE_SOURCE_MAP_2026-06-08.md) ────────────

LIVE_SOURCES: Dict[str, Dict[str, Any]] = {
    "sign_in": {
        "file_id": "1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8",
        "name":    "SIGN IN (yelenapostolova)",
        "kind":    "google_sheet",
    },
    "attendance_tracking": {
        "file_id": "1XQMusZ0-rPx50QDrpf92l1mgEZdHRvmnGwpB9-moSwQ",
        "name":    "Attendance tracking (yelenapostolova)",
        "kind":    "google_sheet",
    },
    "calendar_2026": {
        "file_id": "1giUlw82mlFFfMZOvcZWqBtyB5vNntKliAamQRWzV0IE",
        "name":    "Calendar 2026 (naumka)",
        "kind":    "google_sheet",
    },
    "menu_first_shift": {
        "file_id": "1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw",
        "name":    "2026 First shift Menu.xlsx (yelenapostolova)",
        "kind":    "xlsx",
    },
    "menu_second_shift": {
        "file_id": "18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0",
        "name":    "2026 Second Shift Menu (yelenapostolova)",
        "kind":    "google_sheet",
    },
    "carecenta_auth": {
        "file_id": "14AVRfWJH9aAuvHec0dRoZ3DgP6MWNJJt",
        "name":    "CARECENTA authorizations folder (sweetlanagoj)",
        "kind":    "folder",
    },
    "new_auth": {
        "file_id": "1SZzHuL1PYI2M39gCxoEZrcDj6s8Be8A9",
        "name":    "new auth folder (sweetlanagoj)",
        "kind":    "folder",
    },
}

# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"seen": {}, "last_run": None, "stats": {}}


def save_state(state: Dict[str, Any]) -> None:
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Google API setup ──────────────────────────────────────────────────────────

def get_services():
    """Get Google Sheets + Drive API services.

    Auth priority (OAuth is PERMANENTLY BANNED per Kato's hard rule):
      1. Service account key at ~/.rex_drive_service_account.json
         — never expires, works headlessly, NO user OAuth dependency.
      2. IMAP-forwarded documents — staff emails as attachments (future path).
      3. NO OAuth — permanently banned, tokens deleted 2026-07-03.

    To set up service account: Google Cloud Console → create service account →
    download JSON key → save as ~/.rex_drive_service_account.json →
    share target Sheets/Drive files with the service account email.
    """
    from googleapiclient.discovery import build

    SA_KEY = Path.home() / ".rex_drive_service_account.json"

    # ── 1. Service account (PRIMARY — no OAuth, never expires) ────────
    if SA_KEY.exists():
        from google.oauth2 import service_account
        SA_SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = service_account.Credentials.from_service_account_file(
            str(SA_KEY), scopes=SA_SCOPES
        )
        log.info("Using service account (no OAuth)")
        return {
            "drive":  build("drive", "v3", credentials=creds),
            "sheets": build("sheets", "v4", credentials=creds),
        }

    # ── 2. NO OAuth — it's permanently banned ─────────────────────────
    raise RuntimeError(
        "🔴 Google OAuth is PERMANENTLY BANNED (Kato hard rule, July 3 2026).\n"
        "   OAuth tokens were deleted. The only approved paths are:\n"
        "   1. Service account: create at Google Cloud Console → download JSON →\n"
        "      save as ~/.rex_drive_service_account.json\n"
        "   2. IMAP-forwarded documents: staff email sheets as attachments\n"
        "   Run: python3 ~/Desktop/REX/CC_setup_drive_service_account.py --help"
    )


def file_meta(drive, file_id: str) -> Dict[str, Any]:
    return drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,modifiedTime,size",
        supportsAllDrives=True,
    ).execute()


# ── Parser: SIGN IN → clients ────────────────────────────────────────────────

def parse_sign_in_to_clients(svc, file_id: str, dry_run: bool) -> Tuple[int, int]:
    """Read the SIGN IN 'sign in' tab and upsert into clients table.
    Returns (rows_seen, rows_changed)."""
    resp = svc["sheets"].spreadsheets().values().get(
        spreadsheetId=file_id, range="sign in",
    ).execute()
    rows = resp.get("values", [])
    log.info(f"  sign_in: {len(rows)} rows in 'sign in' tab")
    if not rows or len(rows) < 2:
        return 0, 0

    # Header: ['Name', 'plan', '', 'TR/F', 'Table', 'change']
    header = [str(c).strip().lower() for c in rows[0]]
    try:
        name_col  = header.index("name")
        plan_col  = header.index("plan")
        trf_col   = header.index("tr/f") if "tr/f" in header else 3
    except ValueError:
        log.warning(f"  sign_in: unexpected header {header}")
        return 0, 0

    entries: List[Dict[str, str]] = []
    for row in rows[1:]:
        if not row or len(row) <= name_col:
            continue
        name = str(row[name_col]).strip()
        if not name or name.startswith("AAAA"):  # separator row
            continue
        plan = str(row[plan_col]).strip() if len(row) > plan_col else ""
        trf  = str(row[trf_col]).strip()   if len(row) > trf_col  else ""
        entries.append({"name": name, "plan_raw": plan, "transportation": trf})

    log.info(f"  sign_in: parsed {len(entries)} active client rows")
    if dry_run:
        for e in entries[:5]:
            log.info(f"    sample: {e}")
        return len(entries), 0

    # Upsert into clients table
    changed = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        for e in entries:
            existing = conn.execute(
                "SELECT client_id, plan_raw, transportation FROM clients WHERE name=?",
                (e["name"],),
            ).fetchone()
            if existing:
                if (existing["plan_raw"] or "") != e["plan_raw"] or \
                   (existing["transportation"] or "") != e["transportation"]:
                    conn.execute(
                        "UPDATE clients SET plan_raw=?, transportation=? WHERE client_id=?",
                        (e["plan_raw"], e["transportation"], existing["client_id"]),
                    )
                    changed += 1
            else:
                conn.execute(
                    "INSERT INTO clients (name, plan_raw, transportation) VALUES (?,?,?)",
                    (e["name"], e["plan_raw"], e["transportation"]),
                )
                changed += 1
        conn.commit()
    return len(entries), changed


# ── Parser: Attendance tracking → attendance_log ────────────────────────────

DATE_HEADER_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})\s+([A-Za-z]+)\W+(\d+)(?:st|nd|rd|th)?\s*shift",
    re.IGNORECASE,
)

# Cells we should NEVER write into attendance_log as a client_name.
# These are header words, status markers, or reason fragments that leak when
# the bookkeeper formats sheets inconsistently.
_NAME_BLACKLIST = {
    "минус", "плюс",                                   # "minus" / "plus" headers (RU)
    "shift", "1st shift", "2nd shift", "shift 1", "shift 2",
    "transport", "tr", "vis", "tr vis", "vis tr",
    "name", "absent", "present", "scheduled",
    "?", "??", "???", "-", "—", "n/a", "na", "tbd",
}


def _norm_date(month_str: str, m: int, d: int) -> str:
    """Convert (Jun-tab, 6/1) → 2026-06-01. Year inferred."""
    year = datetime.now().year
    # Future-proof: if month in tab name is BEFORE current month, assume same year;
    # if much later, infer from current year. Simple version uses current year.
    return f"{year:04d}-{m:02d}-{d:02d}"


def _looks_like_client_name(s: str) -> bool:
    """Filter out header markers, reasons, and other non-name leaks before
    writing to attendance_log."""
    s = (s or "").strip()
    if not s or len(s) < 2:
        return False
    if s.lower() in _NAME_BLACKLIST:
        return False
    # Must have at least one alphabetic char
    if not any(c.isalpha() for c in s):
        return False
    # Pure-digit or short numeric-ish strings
    if s.replace(".", "").replace("/", "").replace(":", "").isdigit():
        return False
    # Common reason fragments — if it starts with these keywords, skip
    REASON_STARTS = (
        "sick", "starting", "till call", "high bp", "low bp", "fever",
        "covid", "doctor", "hospital", "trip", "till ", "from ", "until ",
    )
    if any(s.lower().startswith(rs) for rs in REASON_STARTS):
        return False
    return True


def parse_attendance_to_log(svc, file_id: str, dry_run: bool) -> Tuple[int, int]:
    """Read each month tab of Attendance tracking, parse `M/D Day, Nth shift минус`
    headers + the rows of absent names + reasons. Upsert into attendance_log."""
    meta = svc["sheets"].spreadsheets().get(
        spreadsheetId=file_id, fields="sheets(properties(title))",
    ).execute()
    month_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    month_tabs = [t for t in month_tabs if t in
                  ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")]
    MONTH_MAP = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                 "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

    entries: List[Dict[str, Any]] = []
    for tab in month_tabs:
        try:
            resp = svc["sheets"].spreadsheets().values().get(
                spreadsheetId=file_id, range=tab,
            ).execute()
        except Exception as ex:
            log.warning(f"  attendance: tab '{tab}' fetch failed: {ex}")
            continue
        rows = resp.get("values", [])
        if not rows:
            continue

        # Iterate rows. Each "block" starts with a header row containing date+shift markers.
        # Headers can appear in multiple columns (1st shift in col A/B, 2nd shift in col C/D).
        # Strategy: for each row, scan cells for date headers; when found, record an active
        # (date, shift) context per column-range; subsequent non-header rows in that range
        # are absent entries.
        active: Dict[int, Tuple[str, int]] = {}  # col_start -> (iso_date, shift)
        for row in rows:
            if not row:
                continue
            # Detect header cells in this row
            for col_idx, cell in enumerate(row):
                if not cell:
                    continue
                m = DATE_HEADER_RE.search(str(cell))
                if m:
                    mo, dy, _day_name, shift = m.groups()
                    iso = _norm_date(tab, int(mo), int(dy))
                    active[col_idx] = (iso, int(shift))
            # Otherwise treat each cell as potentially an absent entry under nearest active header
            # (skip if this row had a header — that's the header itself)
            row_had_header = any(
                cell and DATE_HEADER_RE.search(str(cell)) for cell in row
            )
            if row_had_header:
                continue
            # Only treat cells AT an active header column as names.
            # The cell immediately to the right is the reason.
            # (Reason cells must NOT also be treated as names.)
            for col_start, (iso, shift) in active.items():
                if col_start >= len(row):
                    continue
                cell = row[col_start]
                if not cell or not str(cell).strip():
                    continue
                name = str(cell).strip()
                if not _looks_like_client_name(name):
                    continue   # skip headers, reasons, "минус" markers, "?", etc.
                reason = ""
                if col_start + 1 < len(row) and row[col_start + 1]:
                    reason = str(row[col_start + 1]).strip()
                # Canonicalize: Title Case so ALL-CAPS and Title forms dedup.
                name = " ".join(w.capitalize() for w in name.split())
                entries.append({
                    "log_date":    iso,
                    "shift":       shift,
                    "client_name": name,
                    "status":      "absent",
                    "reason":      reason,
                })

    log.info(f"  attendance: parsed {len(entries)} absent entries across {len(month_tabs)} month tabs")
    if dry_run:
        for e in entries[:5]:
            log.info(f"    sample: {e}")
        return len(entries), 0

    # Upsert (idempotent on log_date+shift+client_name)
    changed = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        # Ensure schema accommodates these columns (no-op if already there)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(attendance_log)")}
        if "reason" not in cols:
            try:
                conn.execute("ALTER TABLE attendance_log ADD COLUMN reason TEXT")
                conn.commit()
                log.info("  attendance: added 'reason' column to attendance_log")
            except Exception:
                pass
        for e in entries:
            existing = conn.execute(
                "SELECT rowid FROM attendance_log WHERE log_date=? AND shift=? AND client_name=?",
                (e["log_date"], e["shift"], e["client_name"]),
            ).fetchone()
            if existing:
                # Update reason if it changed
                conn.execute(
                    "UPDATE attendance_log SET status=?, reason=? WHERE rowid=?",
                    (e["status"], e["reason"], existing[0]),
                )
            else:
                # Build INSERT to match whatever columns the table has
                base_cols = ["log_date", "shift", "client_name", "status"]
                base_vals = [e["log_date"], e["shift"], e["client_name"], e["status"]]
                if "reason" in cols or True:  # reason was just ensured
                    base_cols.append("reason")
                    base_vals.append(e["reason"])
                if "day_key" in cols:
                    day_key = datetime.fromisoformat(e["log_date"]).strftime("%a")[:3].lower()
                    base_cols.append("day_key")
                    base_vals.append(day_key)
                placeholders = ",".join("?" * len(base_cols))
                conn.execute(
                    f"INSERT INTO attendance_log ({','.join(base_cols)}) VALUES ({placeholders})",
                    base_vals,
                )
                changed += 1
        conn.commit()
    return len(entries), changed


# ── Parser: CARECENTA + new auth folders → authorization ────────────────────

def parse_auth_folder(svc, folder_id: str, dry_run: bool) -> Tuple[int, int]:
    """List PDFs in the auth folder. The filename pattern is
    `<CLIENT_NAME> <MM.DD.YY>[ VIS|TR|TR VIS].PDF`. Parse client + expiry.
    Does NOT OCR the PDFs (cheap pass); just records the metadata so the
    dashboard knows new authorizations exist. PDFs whose filename does NOT
    match the pattern are sent to Kato via Telegram for manual review."""
    # Paginate — the folder holds 750+ PDFs; a single pageSize=500 call missed ~290.
    files: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = svc["drive"].files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='application/pdf'",
            fields="nextPageToken,files(id,name,modifiedTime,owners(emailAddress))",
            orderBy="modifiedTime desc",
            pageSize=500,
            pageToken=page_token,
        ).execute()
        files.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    log.info(f"  auth folder {folder_id}: {len(files)} PDFs visible")

    # Pattern: 'DMITRIEVA 5.31.27.PDF' or 'POLOVITSKAYA TR VIS 3.31.27.PDF'
    FILENAME_RE = re.compile(
        r"^(?P<name>[A-Z][A-Z .'-]*?)\s+(?:(?P<flag>TR|VIS|TR VIS|VIS TR|F)\s+)?"
        r"(?P<m>\d{1,2})\.(?P<d>\d{1,2})\.(?P<y>\d{2})",
        re.IGNORECASE,
    )

    # Optional Telegram fallback for unreadable filenames
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ocr_fallback",
            os.path.expanduser("~/Desktop/REX/CC_ocr_telegram_fallback.py"),
        )
        ocr_fallback = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ocr_fallback)
    except Exception as e:
        log.warning(f"  OCR Telegram fallback not available: {e}")
        ocr_fallback = None

    # Telegram-flag throttles: don't blast Kato's phone with 165 old PDFs.
    #   - Only flag PDFs modified within FLAG_RECENT_DAYS
    #   - Cap at FLAG_MAX_PER_RUN per agent pass
    FLAG_RECENT_DAYS = 14
    FLAG_MAX_PER_RUN = 3
    flag_cutoff = (datetime.now(timezone.utc) - timedelta(days=FLAG_RECENT_DAYS)).isoformat()

    entries: List[Dict[str, Any]] = []
    flagged_count = 0
    skipped_old   = 0
    for f in files:
        m = FILENAME_RE.match(f["name"])
        if not m:
            log.debug(f"    skipped (unparseable name): {f['name']}")
            # Throttle: only flag recent PDFs and cap per-run.
            if f["modifiedTime"] < flag_cutoff:
                skipped_old += 1
                continue
            if flagged_count >= FLAG_MAX_PER_RUN:
                continue
            # Send to Kato via Telegram (idempotent — queue file prevents repeats)
            if ocr_fallback and not dry_run:
                try:
                    result = ocr_fallback.flag_for_review(
                        source=f"auth_folder_{folder_id[:8]}",
                        drive_file_id=f["id"],
                        reason=(
                            f"Auth folder PDF has unparseable filename — cannot extract "
                            f"client_name + service_end_date for dashboard sync."
                        ),
                        partial={"filename": f["name"], "modified": f["modifiedTime"][:10]},
                        bot="rex_of_gold",
                    )
                    if result.get("ok") and result.get("status") != "already_queued":
                        flagged_count += 1
                except Exception as ex:
                    log.warning(f"    fallback send failed for {f['name']}: {ex}")
            continue
        name = m.group("name").strip().title()
        mo = int(m.group("m")); dy = int(m.group("d")); yr = 2000 + int(m.group("y"))
        end_date = f"{yr:04d}-{mo:02d}-{dy:02d}"
        flag = (m.group("flag") or "").upper().strip()
        entries.append({
            "client_name": name,
            "service_end_date": end_date,
            "auth_kind": flag or "VIS",
            "source_file_id": f["id"],
            "source_file_name": f["name"],
        })

    log.info(
        f"  auth folder {folder_id}: parsed {len(entries)} authorizations from filenames; "
        f"flagged {flagged_count} unparseable for Telegram review "
        f"(skipped {skipped_old} older than {FLAG_RECENT_DAYS} days)"
    )
    if dry_run:
        for e in entries[:5]:
            log.info(f"    sample: {e}")
        return len(entries), 0

    # Record in authorization table — only insert if no row exists for this
    # client_name + service_end_date combination (filename change without
    # OCR = no real new auth content).
    changed = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        for e in entries:
            existing = conn.execute(
                "SELECT auth_id FROM authorization WHERE client_name=? AND service_end_date=?",
                (e["client_name"], e["service_end_date"]),
            ).fetchone()
            if not existing:
                # auth_id and authorization_number are NOT NULL. Use the Drive file ID
                # as the auth number so re-runs are idempotent and the audit trail
                # links back to the source PDF.
                auth_number = f"DRIVE-{e['source_file_id']}"
                conn.execute(
                    """INSERT INTO authorization
                       (client_name, service_end_date, payer_raw, source_type, status,
                        authorization_number, received_date, notes)
                       VALUES (?, ?, '', 'PORTAL', 'ACTIVE', ?, ?, ?)""",
                    (e["client_name"], e["service_end_date"], auth_number,
                     datetime.now().strftime("%Y-%m-%d"),
                     f"Drive PDF: {e['source_file_name']} (id={e['source_file_id']})"),
                )
                changed += 1
        conn.commit()
    return len(entries), changed


# ── Parser: Calendar 2026 → client_schedule ──────────────────────────────────
# Source chosen: Calendar 2026 (1giUlw82mlFFfMZOvcZWqBtyB5vNntKliAamQRWzV0IE)
# Rationale: the Jun/Jan month tabs have columns M/T/W/TH/F/Su whose cell values
# are exactly "1" or "2" (shift number) with no encoding quirks.  The SIGN IN
# "sign in" tab has the same data but occasionally encodes suspended-days as
# "0(1)", which requires extra parsing.  Calendar is cleaner and is the source
# explicitly listed in OCR plan §2 row 4.
# The Jun tab is used as the primary snapshot (most current).  Future runs will
# still fall through to Jun since it is the live month; when January becomes
# current, the dispatcher can be updated to prefer the active month tab.

# Day columns in the Calendar month tabs (order is fixed: D-I = M T W TH F Su)
_CAL_DAY_COLS = ["M", "T", "W", "TH", "F", "SU"]
# Canonical values accepted for day_of_week in client_schedule:
_VALID_DAYS = frozenset(["M", "T", "W", "TH", "F", "SU"])


def _fuzzy_match_client(name_raw: str, active_names: List[str]) -> Optional[str]:
    """Return the best-matching active client name or None if confidence < 80%.
    Uses simple normalised-lower-case prefix / token matching without third-party
    libraries so it stays consistent with the rest of the file."""
    if not name_raw:
        return None
    needle = name_raw.strip().lower()
    # Exact match (case-insensitive)
    for n in active_names:
        if n.lower() == needle:
            return n
    # Token overlap: split both on whitespace and count shared tokens
    needle_tokens = set(needle.split())
    best_name, best_score = None, 0
    for n in active_names:
        hay_tokens = set(n.lower().split())
        shared = len(needle_tokens & hay_tokens)
        total  = len(needle_tokens | hay_tokens)
        score  = shared / total if total else 0
        if score > best_score:
            best_score, best_name = score, n
    if best_score >= 0.8:
        return best_name
    return None


def parse_calendar_to_schedule(svc, file_id: str, dry_run: bool) -> Tuple[int, int]:
    """Read the Calendar 2026 'Jun' month tab and upsert into client_schedule.

    The tab layout (confirmed via read-only investigation 2026-06-11):
      Row 0:  header — [#, NAME, Plan, M, T, W, TH, F, Su, 1..31]
      Row 1:  weekday sub-header for the day-columns — skip
      Row 2+: one row per client — [seq#, name, plan, M-val, T-val, …, Su-val, …day-cols…]

    Each day value is either '1' (shift 1), '2' (shift 2), or blank (not scheduled).
    '0(1)' and similar quirky encodings are absent from the Calendar tab (confirmed
    on Jun and Jan sample reads); the parser skips any non-1/2 day value safely.

    Upsert logic:
      - SELECT before INSERT on (client_name, day_of_week, shift)
      - If row exists: UPDATE plan + updated_at only
      - If row missing: INSERT
      - No DELETE — purely additive
    Sanity gate: if >30 % of names fail fuzzy match, abort after dry-run report.

    Returns (rows_seen, rows_changed).
    """
    # ── Determine which month tab to read (prefer 'Jun' as current live tab) ──
    meta = svc["sheets"].spreadsheets().get(
        spreadsheetId=file_id,
        fields="sheets(properties(title))",
    ).execute()
    all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    MONTH_TABS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    # Pick current or most-recent available month tab
    from datetime import datetime
    now_month = datetime.now().strftime("%b")[:3].capitalize()
    preferred_order = MONTH_TABS[MONTH_TABS.index(now_month):] + MONTH_TABS[:MONTH_TABS.index(now_month)]
    preferred_order.reverse()  # start from current month, then walk back
    chosen_tab = None
    for month in preferred_order:
        if month in all_tabs:
            chosen_tab = month
            break
    if not chosen_tab:
        log.warning("  calendar: no standard month tab found in Calendar 2026; aborting")
        return 0, 0
    log.info(f"  calendar: using tab '{chosen_tab}' from Calendar 2026")

    # ── Fetch the tab ─────────────────────────────────────────────────────────
    try:
        resp = svc["sheets"].spreadsheets().values().get(
            spreadsheetId=file_id, range=chosen_tab,
        ).execute()
    except Exception as ex:
        log.error(f"  calendar: failed to fetch tab '{chosen_tab}': {ex}")
        return 0, 0

    rows = resp.get("values", [])
    if len(rows) < 3:
        log.warning(f"  calendar: tab '{chosen_tab}' has fewer than 3 rows — nothing to parse")
        return 0, 0

    # ── Parse header row ──────────────────────────────────────────────────────
    # Expected: ['', 'NAME', 'Plan', 'M', 'T', 'W', 'TH', 'F', 'Su', '1', '2', ...]
    header = [str(c).strip() for c in rows[0]]
    try:
        name_col = next(i for i, h in enumerate(header) if h.upper() == "NAME")
        plan_col = next(i for i, h in enumerate(header) if h.upper() == "PLAN")
    except StopIteration:
        log.warning(f"  calendar: could not find NAME/Plan columns in header {header[:12]}")
        return 0, 0

    # Map day abbreviation → column index
    day_col_map: Dict[str, int] = {}
    for i, h in enumerate(header):
        norm = h.strip().upper()
        if norm == "SU":
            day_col_map["SU"] = i
        elif norm in ("M", "T", "W", "TH", "F"):
            day_col_map[norm] = i

    if not day_col_map:
        log.warning(f"  calendar: no M/T/W/TH/F/Su columns found in header {header[:12]}")
        return 0, 0
    log.info(f"  calendar: day columns → {day_col_map}")

    # ── Load active client list for fuzzy matching ────────────────────────────
    with sqlite3.connect(str(DB_PATH)) as conn:
        active_clients = [
            row[0] for row in conn.execute(
                "SELECT name FROM clients WHERE active=1"
            ).fetchall()
        ]
    log.info(f"  calendar: {len(active_clients)} active clients in DB for fuzzy matching")

    # ── Parse data rows ───────────────────────────────────────────────────────
    entries: List[Dict[str, Any]] = []
    no_match_count = 0
    total_names    = 0

    for row in rows[2:]:  # skip header + weekday sub-header
        if not row or len(row) <= name_col:
            continue
        raw_name = str(row[name_col]).strip()
        if not raw_name:
            continue
        total_names += 1

        plan = str(row[plan_col]).strip() if len(row) > plan_col else ""

        # Fuzzy-match to an active client
        matched = _fuzzy_match_client(raw_name, active_clients)
        if matched is None:
            no_match_count += 1
            log.debug(f"  calendar: no fuzzy match for '{raw_name}'")
            continue

        # Extract scheduled days
        for day_key, col_idx in day_col_map.items():
            cell = str(row[col_idx]).strip() if col_idx < len(row) else ""
            if cell not in ("1", "2"):
                continue  # blank or unexpected value — skip
            shift = int(cell)
            entries.append({
                "client_name": matched,
                "plan":        plan,
                "day_of_week": day_key,
                "shift":       shift,
            })

    log.info(
        f"  calendar: parsed {len(entries)} schedule rows from {total_names} client rows "
        f"({no_match_count} name mismatches)"
    )

    # ── Sanity gate: >30 % miss → stop ───────────────────────────────────────
    if total_names > 0 and no_match_count / total_names > 0.30:
        log.error(
            f"  calendar: ABORT — {no_match_count}/{total_names} "
            f"({100*no_match_count/total_names:.1f}%) names failed fuzzy match (threshold 30%)"
        )
        return len(entries), 0

    # ── Dry-run: print 5 samples (first-name + last-initial) and return ───────
    if dry_run:
        def _redact(name: str) -> str:
            parts = name.split()
            if len(parts) >= 2:
                return f"{parts[0]} {parts[-1][0]}."
            return parts[0] if parts else name

        log.info("  calendar: DRY-RUN — 5 sample entries:")
        for e in entries[:5]:
            log.info(
                f"    {_redact(e['client_name'])} | plan={e['plan']} "
                f"| {e['day_of_week']} shift={e['shift']}"
            )
        log.info(
            f"  calendar: DRY-RUN summary — {len(entries)} schedule rows "
            f"from {total_names - no_match_count} matched clients "
            f"({no_match_count} unmatched, NOT written)"
        )
        return len(entries), 0

    # ── Real run: UPSERT ──────────────────────────────────────────────────────
    now_iso = datetime.now().isoformat()
    changed  = 0
    # Note: the DB UNIQUE constraint is (client_name, day_of_week) — shift is a stored
    # attribute, not part of the unique key. SELECT-before-INSERT on that pair; UPDATE
    # plan + shift + updated_at if either value changed (additive, never delete).
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        for e in entries:
            existing = conn.execute(
                "SELECT id, plan, shift FROM client_schedule "
                "WHERE client_name=? AND day_of_week=?",
                (e["client_name"], e["day_of_week"]),
            ).fetchone()
            if existing:
                # Update plan and/or shift if either changed
                plan_same  = (existing["plan"]  or "") == e["plan"]
                shift_same = (existing["shift"] or 0)  == e["shift"]
                if not plan_same or not shift_same:
                    conn.execute(
                        "UPDATE client_schedule SET plan=?, shift=?, updated_at=? "
                        "WHERE id=?",
                        (e["plan"], e["shift"], now_iso, existing["id"]),
                    )
                    changed += 1
            else:
                conn.execute(
                    "INSERT INTO client_schedule (client_name, plan, day_of_week, shift, updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (e["client_name"], e["plan"], e["day_of_week"], e["shift"], now_iso),
                )
                changed += 1
        conn.commit()

    log.info(f"  calendar: upserted {changed} rows into client_schedule")
    return len(entries), changed


# ── Dispatcher ────────────────────────────────────────────────────────────────

PARSERS = {
    "sign_in":             parse_sign_in_to_clients,
    "attendance_tracking": parse_attendance_to_log,
    "carecenta_auth":      parse_auth_folder,
    "new_auth":            parse_auth_folder,
    "calendar_2026":       parse_calendar_to_schedule,
}


RAW_MIRROR = Path.home() / "Desktop" / "REX" / "gdrive_mirror" / "_raw_fallback"


def mirror_raw_file(svc, key: str, src: Dict[str, Any], meta: Dict[str, Any]) -> Optional[str]:
    """Raw-file mirror fallback (Drive-independence goal): when a watched source has
    no DB parser yet, still pull a raw local copy so the mirror never misses a file.
    Google-native files (Sheets) export to .xlsx; binary files download as-is.
    Read-only on Drive (drive.readonly scope). Folders are left to the parser path."""
    if src.get("kind") == "folder":
        return None
    RAW_MIRROR.mkdir(parents=True, exist_ok=True)
    fid = src["file_id"]
    name = meta.get("name") or src.get("name") or key
    mime = meta.get("mimeType", "")
    try:
        if src.get("kind") == "google_sheet" or "spreadsheet" in mime:
            data = svc["drive"].files().export_media(
                fileId=fid,
                mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ).execute()
            safe = re.sub(r"[^\w.\- ]", "_", name)
            if not safe.lower().endswith(".xlsx"):
                safe += ".xlsx"
        else:
            data = svc["drive"].files().get_media(fileId=fid).execute()
            safe = re.sub(r"[^\w.\- ]", "_", name)
        out = RAW_MIRROR / f"{key}__{safe}"
        out.write_bytes(data)
        log.info(f"  📥 raw-mirrored {key} → {out.name} ({len(data):,} bytes)")
        return str(out)
    except Exception as e:
        log.warning(f"  raw-mirror failed for {key}: {e}")
        return None


def ingest_pass(svc, only_source: Optional[str], dry_run: bool) -> Dict[str, Any]:
    state = load_state()
    seen  = state.get("seen", {})
    stats: Dict[str, Any] = {}

    for key, src in LIVE_SOURCES.items():
        if only_source and key != only_source:
            continue
        log.info(f"▶ {key}: {src['name']}")
        try:
            meta = file_meta(svc["drive"], src["file_id"])
        except Exception as e:
            log.error(f"  meta fetch failed: {e}")
            stats[key] = {"error": str(e)}
            continue

        last_seen = seen.get(key)
        changed = (last_seen != meta["modifiedTime"])
        log.info(f"  modifiedTime={meta['modifiedTime']} · last_seen={last_seen} · changed={changed}")

        parser = PARSERS.get(key)
        if not parser:
            # No DB parser yet — but still keep a raw local copy so the mirror is
            # complete (Drive-independence). Only pull when the source changed.
            if changed and not dry_run:
                path = mirror_raw_file(svc, key, src, meta)
                seen[key] = meta["modifiedTime"]
                stats[key] = {"status": "raw_mirrored" if path else "raw_mirror_failed",
                              "path": path, "modifiedTime": meta["modifiedTime"]}
            else:
                log.info(f"  no parser for {key}; unchanged — skipping")
                stats[key] = {"status": "no_parser_unchanged", "modifiedTime": meta["modifiedTime"]}
            continue

        if not changed and not dry_run and only_source is None and src.get("kind") != "folder":
            log.info(f"  unchanged since last run — skipping")
            stats[key] = {"status": "unchanged", "modifiedTime": meta["modifiedTime"]}
            continue

        try:
            seen_rows, changed_rows = parser(svc, src["file_id"], dry_run)
            stats[key] = {
                "status": "ok",
                "seen_rows": seen_rows,
                "changed_rows": changed_rows,
                "modifiedTime": meta["modifiedTime"],
            }
            seen[key] = meta["modifiedTime"]
            log.info(f"  ✅ {seen_rows} seen, {changed_rows} changed (dry_run={dry_run})")
        except Exception as e:
            log.exception(f"  parser failed: {e}")
            stats[key] = {"status": "parser_error", "error": str(e)}

    state["seen"] = seen
    state["stats"] = stats
    if not dry_run:
        save_state(state)
        write_mirror_health(stats)
    return stats


def write_mirror_health(stats: Dict[str, Any]) -> None:
    """Phase A: emit a small health artifact the dashboard/HUD can read — proves the
    mirror is live and complete (last pass, per-source status, file count, size).
    Drive-independence needs the local copy to be observably current."""
    try:
        mirror_root = Path.home() / "Desktop" / "REX" / "gdrive_mirror"
        files = sum(1 for _ in mirror_root.rglob("*") if _.is_file())
        size = sum(p.stat().st_size for p in mirror_root.rglob("*") if p.is_file())
        health = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "sources": {k: v.get("status", "?") for k, v in stats.items()},
            "source_count": len(LIVE_SOURCES),
            "mirror_files": files,
            "mirror_bytes": size,
            "ok": all(v.get("status") in ("ok", "unchanged", "raw_mirrored", "no_parser_unchanged")
                      for v in stats.values()),
        }
        (mirror_root / "_health.json").write_text(json.dumps(health, indent=2))
    except Exception as e:
        log.warning(f"  mirror health write failed: {e}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                        help="single pass then exit (default behavior)")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse + report, no DB write")
    parser.add_argument("--source", default=None,
                        help=f"only ingest this source key (one of {list(LIVE_SOURCES)})")
    parser.add_argument("--status", action="store_true",
                        help="print last-seen state + exit")
    parser.add_argument("--daemon", action="store_true",
                        help="run continuously, 5-min loop")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(load_state(), indent=2))
        return 0

    svc = get_services()

    if args.daemon:
        log.info("=" * 60)
        log.info(f"GOJ Drive Ingest — daemon mode, 5-min loop (pid={os.getpid()})")
        while True:
            try:
                stats = ingest_pass(svc, args.source, args.dry_run)
                log.info(f"pass complete: {json.dumps({k:v.get('status') for k,v in stats.items()})}")
            except Exception:
                log.exception("ingest pass crashed; will retry next interval")
            time.sleep(300)
    else:
        log.info("=" * 60)
        log.info(f"GOJ Drive Ingest — single pass (dry_run={args.dry_run}, source={args.source or 'all'})")
        stats = ingest_pass(svc, args.source, args.dry_run)
        print(json.dumps(stats, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
