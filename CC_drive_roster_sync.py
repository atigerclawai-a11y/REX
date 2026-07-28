#!/usr/bin/env python3
"""
CC_drive_roster_sync.py — GOJ Attendance Spreadsheet → auth_tracker.db Sync
Gold Health Systems · Garden of Joy

Reads the Google Drive attendance spreadsheet (source of truth for client rosters),
clones it to a working copy (never touches the original), parses each day/shift tab,
and syncs the roster into the clients table in auth_tracker.db.

Changes are non-destructive: soft deactivation only, never hard deletes.
Logs what was added, changed, or removed.

Usage:
    python3 CC_drive_roster_sync.py [--dry-run] [--tab TH2] [--file-id FILE_ID]

    --dry-run        Parse and report without writing to DB
    --tab TH2        Only sync a specific tab (e.g. TH2, M1, F2)
    --file-id ID     Override the spreadsheet file ID (if not found automatically)

Venv: ~/.rex-venv/
OAuth token: ~/.rex_google_token.json
Credentials: ~/Desktop/REX/google_credentials.json
"""

import sys
import os
import re
import json
import sqlite3
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

# ── Paths ─────────────────────────────────────────────────────────────────────

REX_DIR    = Path(__file__).resolve().parent
CREDS_PATH = REX_DIR / 'google_credentials.json'
TOKEN_PATH = Path.home() / '.rex_google_token.json'
DB_PATH    = Path.home() / 'Documents' / 'goj files' / 'dashboard' / 'auth_tracker.db'
LOG_DIR    = REX_DIR / 'scheduled_task_logs'
LOG_DIR.mkdir(exist_ok=True)

# ── Google Drive / Sheets constants ───────────────────────────────────────────

# Calendar/Attendance Drive folder (akhiger@gmail.com, shared with atigerclawai)
ATTENDANCE_FOLDER_ID = '1VcNscnjp-rVfUHDxty1g-Njla34uUTTl'

# OAuth scopes — spreadsheets.readonly for Sheets API; drive.file for copy creation;
# drive.readonly to locate/read shared spreadsheets not created by this app
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
]

# Keyword in spreadsheet name to identify the attendance file
ATTENDANCE_FILE_KEYWORDS = ['attendance', 'sign', 'roster', 'schedule']

# ── Tab naming normalization ──────────────────────────────────────────────────

# Canonical day keys used in auth_tracker.db clients table
# Maps normalized tab key → DB day column prefix
DAY_KEY_MAP = {
    'M':  'M',
    'T':  'T',
    'W':  'W',
    'TH': 'TH',
    'F':  'F',
    'SA': 'SA',
    'SU': 'Su',  # DB uses day_Su_actual
}

# Expected tab names: M1, M2, T1, T2, W1, W2, TH1, TH2, F1, F2, SA1, SA2
# Also handle spaces: "M 1", "TH 2", "Th 1", "Monday 1", etc.
_TAB_PATTERN = re.compile(
    r'^(?P<day>M(?:on(?:day)?)?|T(?:ue(?:sday)?)?|W(?:ed(?:nesday)?)?'
    r'|TH(?:u(?:rs(?:day)?)?)?|F(?:ri(?:day)?)?|SA(?:t(?:urday)?)?'
    r'|SU(?:n(?:day)?)?)\s*(?P<shift>[12])$',
    re.IGNORECASE,
)

_DAY_ALIASES = {
    'MON': 'M', 'MONDAY': 'M',
    'TUE': 'T', 'TUESDAY': 'T',
    'WED': 'W', 'WEDNESDAY': 'W',
    'THU': 'TH', 'THURSDAY': 'TH',
    'FRI': 'F', 'FRIDAY': 'F',
    'SAT': 'SA', 'SATURDAY': 'SA',
    'SUN': 'SU', 'SUNDAY': 'SU',
}


def parse_tab_name(title: str) -> Optional[Tuple[str, int]]:
    """
    Parse a tab title into (day_key, shift).
    Returns None if the tab is not a recognizable day/shift tab.

    Examples:
        'M1' → ('M', 1)
        'TH 2' → ('TH', 2)
        'Thursday1' → ('TH', 1)
        'Overview' → None
    """
    t = title.strip()
    m = _TAB_PATTERN.match(t)
    if not m:
        return None
    day_raw = m.group('day').upper()
    shift   = int(m.group('shift'))
    day_key = _DAY_ALIASES.get(day_raw, day_raw)
    if day_key not in DAY_KEY_MAP:
        return None
    return (day_key, shift)


# ── Column detection ──────────────────────────────────────────────────────────

# The spreadsheet has: Name, Plan, CH, TR, IN, OUT, Signature
# We locate headers case-insensitively and handle column order variation

_COL_ALIASES = {
    'name':      ['name', 'client', 'client name', 'last name', 'first name', 'full name'],
    'plan':      ['plan', 'insurance', 'payer', 'plan type'],
    'ch':        ['ch', 'chairs', 'chrs'],
    'tr':        ['tr', 'transport', 'trans'],
    'in':        ['in', 'time in', 'time-in', 'checkin'],
    'out':       ['out', 'time out', 'time-out', 'checkout'],
    'signature': ['signature', 'sig', 'sign'],
}


def detect_columns(header_row: List[str]) -> Dict[str, Optional[int]]:
    """
    Given a header row, return a dict mapping logical field → column index (or None).
    Tolerates missing columns gracefully.
    """
    cols: Dict[str, Optional[int]] = {k: None for k in _COL_ALIASES}
    for i, cell in enumerate(header_row):
        cell_norm = str(cell).strip().lower()
        for field, aliases in _COL_ALIASES.items():
            if cols[field] is None and cell_norm in aliases:
                cols[field] = i
                break
    return cols


# ── Google API helpers ────────────────────────────────────────────────────────

def _get_creds():
    """
    Return valid Google credentials using the shared OAuth token.
    Refreshes if expired. Returns None if unavailable.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        logging.error('google-auth not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client')
        return None

    if not TOKEN_PATH.exists():
        logging.error(f'OAuth token missing: {TOKEN_PATH}. Run: python backend/rex_gmail.py --setup')
        return None
    if not CREDS_PATH.exists():
        logging.error(f'OAuth credentials missing: {CREDS_PATH}')
        return None

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            logging.info('OAuth token refreshed')
        except Exception as e:
            logging.error(f'Token refresh failed: {e}')
            return None
    return creds


def _build_drive(creds):
    from googleapiclient.discovery import build
    return build('drive', 'v3', credentials=creds)


def _build_sheets(creds):
    from googleapiclient.discovery import build
    return build('sheets', 'v4', credentials=creds)


# ── Find the attendance spreadsheet ──────────────────────────────────────────

def find_attendance_spreadsheet(drive_svc, folder_id: str) -> Optional[Dict]:
    """
    Search for the GOJ attendance spreadsheet in the given Drive folder.
    Returns the first Google Sheets file found there, or None.
    """
    mime = 'application/vnd.google-apps.spreadsheet'
    query = f"'{folder_id}' in parents and mimeType='{mime}' and trashed=false"
    try:
        resp = drive_svc.files().list(
            q=query,
            fields='files(id, name, modifiedTime)',
            orderBy='modifiedTime desc',
        ).execute()
        files = resp.get('files', [])
        if not files:
            logging.warning(f'No spreadsheets found in folder {folder_id}')
            return None
        # Prefer files whose name suggests attendance/roster
        for f in files:
            name_lower = f['name'].lower()
            if any(kw in name_lower for kw in ATTENDANCE_FILE_KEYWORDS):
                logging.info(f"Found attendance spreadsheet: {f['name']} ({f['id']})")
                return f
        # Fall back to first spreadsheet
        logging.info(f"Using first spreadsheet found: {files[0]['name']} ({files[0]['id']})")
        return files[0]
    except Exception as e:
        logging.error(f'Drive folder search failed: {e}')
        return None


# ── Clone the spreadsheet ─────────────────────────────────────────────────────

def clone_spreadsheet(drive_svc, file_id: str, original_name: str) -> Optional[str]:
    """
    Create a copy of the spreadsheet so we never modify the original.
    Returns the new file's ID, or None on failure.
    """
    ts = datetime.now().strftime('%Y-%m-%d_%H%M')
    copy_name = f'[SYNC_COPY] {original_name} — {ts}'
    try:
        copy = drive_svc.files().copy(
            fileId=file_id,
            body={'name': copy_name},
            fields='id, name',
        ).execute()
        logging.info(f"Cloned to: {copy['name']} ({copy['id']})")
        return copy['id']
    except Exception as e:
        logging.error(f'Clone failed: {e}')
        return None


def delete_drive_file(drive_svc, file_id: str):
    """Delete a Drive file (used to clean up sync copies after processing)."""
    try:
        drive_svc.files().delete(fileId=file_id).execute()
        logging.info(f'Deleted clone {file_id}')
    except Exception as e:
        logging.warning(f'Could not delete clone {file_id}: {e}')


# ── Read all tabs from a spreadsheet ─────────────────────────────────────────

def read_all_sheets(sheets_svc, spreadsheet_id: str) -> Dict[str, List[List]]:
    """
    Read every sheet in the spreadsheet.
    Returns {sheet_title: [[row0_col0, ...], [row1_col0, ...], ...]}
    """
    try:
        meta = sheets_svc.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields='sheets(properties(sheetId,title))',
        ).execute()
    except Exception as e:
        logging.error(f'Failed to read spreadsheet metadata: {e}')
        return {}

    sheets_data: Dict[str, List[List]] = {}
    for sheet in meta.get('sheets', []):
        title = sheet['properties']['title']
        try:
            resp = sheets_svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=title,
            ).execute()
            rows = resp.get('values', [])
            sheets_data[title] = rows
            logging.info(f"  Sheet '{title}': {len(rows)} rows")
        except Exception as e:
            logging.warning(f"  Failed to read sheet '{title}': {e}")
    return sheets_data


# ── Parse a day/shift tab into roster rows ────────────────────────────────────

def parse_sheet_rows(
    rows: List[List],
    tab_title: str,
    day_key: str,
    shift: int,
) -> List[Dict[str, Any]]:
    """
    Parse raw sheet rows into a list of roster entries.
    Returns list of dicts with keys: name, plan, ch, tr, day_key, shift, tab.

    Skips blank rows, header rows, and entries without a name.
    Does NOT filter Larry — he may still attend; exclusion is at the output/transport level.
    """
    if not rows:
        return []

    # Find header row — first row containing 'name' (case-insensitive)
    header_idx = None
    for i, row in enumerate(rows):
        row_text = ' '.join(str(c).lower() for c in row)
        if 'name' in row_text:
            header_idx = i
            break

    if header_idx is None:
        logging.warning(f"Tab '{tab_title}': no header row found")
        return []

    header = [str(c) for c in rows[header_idx]]
    col_map = detect_columns(header)
    name_col = col_map['name']

    if name_col is None:
        logging.warning(f"Tab '{tab_title}': 'Name' column not found in {header}")
        return []

    entries = []
    for row in rows[header_idx + 1:]:
        if not row or len(row) <= name_col:
            continue
        raw_name = str(row[name_col]).strip()
        if not raw_name or raw_name.lower() in ('name', '', 'total', 'count'):
            continue

        plan = ''
        if col_map['plan'] is not None and len(row) > col_map['plan']:
            plan = str(row[col_map['plan']]).strip()

        ch = ''
        if col_map['ch'] is not None and len(row) > col_map['ch']:
            ch = str(row[col_map['ch']]).strip()

        tr = ''
        if col_map['tr'] is not None and len(row) > col_map['tr']:
            tr = str(row[col_map['tr']]).strip()

        entries.append({
            'name':    raw_name,
            'plan':    plan,
            'ch':      ch,
            'tr':      tr,
            'day_key': day_key,
            'shift':   shift,
            'tab':     tab_title,
        })

    return entries


# ── Name matching ─────────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r'\s+', ' ', name.strip().lower())


def fuzzy_match_client(name: str, db_names: Dict[str, int]) -> Optional[int]:
    """
    Try to match a Drive roster name to a client_id in auth_tracker.db.
    First tries exact normalized match, then partial match.
    Returns client_id or None.
    """
    norm = _normalize_name(name)
    if norm in db_names:
        return db_names[norm]

    # Partial: check if Drive name is contained in a DB name or vice versa
    for db_norm, cid in db_names.items():
        if norm in db_norm or db_norm in norm:
            return cid

    return None


# ── DB sync ───────────────────────────────────────────────────────────────────

# Day key → clients table column for schedule flags
# GOJ is CLOSED on Saturday — no SA column exists or is needed.
_DAY_COL = {
    'M':  'day_M_actual',
    'T':  'day_T_actual',
    'W':  'day_W_actual',
    'TH': 'day_TH_actual',
    'F':  'day_F_actual',
    'SA': None,   # GOJ closed Saturday — skip silently
    'SU': 'day_Su_actual',
}

# Map Drive day_key back to DB base column
_DAY_BASE_COL = {
    'M':  'day_M_base',
    'T':  'day_T_base',
    'W':  'day_W_base',
    'TH': 'day_TH_base',
    'F':  'day_F_base',
    'SA': None,
    'SU': 'day_Su_base',
}


def sync_to_db(
    all_entries: List[Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Sync parsed roster entries into auth_tracker.db clients table.

    Strategy:
    - Match each Drive entry to a DB client by name (normalized)
    - If found: update day schedule flag and shift; log changes
    - If not found: insert new client row (active=1); log as added
    - Clients in DB but not seen in Drive for any day: flag but do NOT deactivate
      (that requires Kato approval — we just log the discrepancy)

    Returns a summary dict.
    """
    if not DB_PATH.exists():
        return {'ok': False, 'error': f'DB not found: {DB_PATH}'}

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Load all existing clients
    cur.execute('SELECT client_id, name, shift, plan_raw, plan_canonical, active FROM clients')
    db_rows = cur.fetchall()
    db_by_id: Dict[int, sqlite3.Row] = {r['client_id']: r for r in db_rows}
    db_names: Dict[str, int] = {_normalize_name(r['name']): r['client_id'] for r in db_rows}

    now_ts = datetime.now(timezone.utc).isoformat()

    added   = []
    updated = []
    not_matched = []
    seen_ids: set = set()

    for entry in all_entries:
        name    = entry['name']
        day_key = entry['day_key']
        shift   = entry['shift']
        plan    = entry['plan']

        day_col  = _DAY_COL.get(day_key)
        base_col = _DAY_BASE_COL.get(day_key)
        if day_col is None:
            # GOJ is closed Saturday — skip silently
            logging.debug(f'  Skipping {name} for day {day_key} — GOJ closed this day')
            continue

        cid = fuzzy_match_client(name, db_names)

        if cid is not None:
            seen_ids.add(cid)
            row = db_by_id[cid]
            changes: Dict[str, Any] = {}

            # Check if day flag needs updating (set to shift value, e.g. 1 or 2)
            cur.execute(f'SELECT {day_col} FROM clients WHERE client_id=?', (cid,))
            current_day_val = (cur.fetchone() or (0,))[0]
            if current_day_val != shift:
                changes[day_col] = shift
                if base_col:
                    changes[base_col] = shift

            # Check shift column
            if row['shift'] != shift:
                # Only update if this is the ONLY shift for this client
                # (clients may attend on multiple days across two shifts — keep higher)
                if row['shift'] is None:
                    changes['shift'] = shift

            # Update plan_raw if we have a value and the current one is blank
            if plan and not row['plan_raw']:
                changes['plan_raw'] = plan

            if changes:
                if not dry_run:
                    set_clause = ', '.join(f'{k}=?' for k in changes)
                    vals = list(changes.values()) + [now_ts, cid]
                    cur.execute(
                        f'UPDATE clients SET {set_clause}, updated_at=? WHERE client_id=?',
                        vals,
                    )
                updated.append({'client_id': cid, 'name': row['name'], 'changes': changes})

        else:
            # New client — not in DB
            not_matched.append({'name': name, 'day_key': day_key, 'shift': shift, 'plan': plan})
            if not dry_run:
                # Insert minimal row — active, with day flag set
                day_defaults = {c: 0 for c in _DAY_COL.values()}
                if day_col in day_defaults:
                    day_defaults[day_col] = shift
                    if base_col:
                        day_defaults[base_col] = shift

                cols = ['name', 'shift', 'active', 'plan_raw', 'created_at', 'updated_at'] + list(day_defaults.keys())
                placeholders = ','.join(['?'] * len(cols))
                vals = [name, shift, 1, plan or None, now_ts, now_ts] + list(day_defaults.values())
                cur.execute(
                    f'INSERT INTO clients ({", ".join(cols)}) VALUES ({placeholders})',
                    vals,
                )
                new_id = cur.lastrowid
                added.append({'client_id': new_id, 'name': name, 'day_key': day_key, 'shift': shift})
                # Add to db_names so duplicate entries within the same sync don't double-insert
                db_names[_normalize_name(name)] = new_id

    # Identify DB clients not seen in any Drive tab (potential deactivations)
    # Do NOT deactivate — just report. Kato must approve deactivations.
    active_db_ids = {r['client_id'] for r in db_rows if r['active']}
    missing_from_drive = active_db_ids - seen_ids
    missing_names = [db_by_id[cid]['name'] for cid in missing_from_drive if cid in db_by_id]

    if not dry_run:
        con.commit()
    con.close()

    return {
        'ok':                True,
        'dry_run':           dry_run,
        'added':             added,
        'updated':           updated,
        'not_matched':       not_matched,
        'missing_from_drive': missing_names,
        'counts': {
            'added':             len(added),
            'updated':           len(updated),
            'not_matched':       len(not_matched),
            'missing_from_drive': len(missing_names),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run_roster_sync(
    file_id: Optional[str] = None,
    tab_filter: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Full roster sync pipeline.

    1. Authenticate with Google
    2. Find (or accept provided) attendance spreadsheet in Drive
    3. Clone it to a working copy
    4. Read all tabs via Sheets API
    5. Parse day/shift tabs
    6. Sync to auth_tracker.db
    7. Delete the clone
    8. Return summary

    Args:
        file_id:    Optional spreadsheet file ID override
        tab_filter: Optional tab name to process only one tab (e.g. 'TH2')
        dry_run:    If True, parse and report without writing to DB

    Returns:
        Summary dict with ok, counts, added, updated, not_matched, missing_from_drive
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    creds = _get_creds()
    if creds is None:
        return {'ok': False, 'error': 'OAuth credentials unavailable'}

    try:
        from googleapiclient.discovery import build
    except ImportError:
        return {'ok': False, 'error': 'google-api-python-client not installed'}

    drive_svc  = _build_drive(creds)
    sheets_svc = _build_sheets(creds)

    # Step 1: Locate the spreadsheet
    if file_id:
        try:
            meta = drive_svc.files().get(
                fileId=file_id, fields='id,name,modifiedTime'
            ).execute()
            spreadsheet_meta = meta
        except Exception as e:
            return {'ok': False, 'error': f'File ID {file_id} not accessible: {e}'}
    else:
        spreadsheet_meta = find_attendance_spreadsheet(drive_svc, ATTENDANCE_FOLDER_ID)
        if not spreadsheet_meta:
            return {
                'ok':    False,
                'error': (
                    f'No attendance spreadsheet found in Drive folder {ATTENDANCE_FOLDER_ID}. '
                    'Re-run with --file-id if you know the file ID.'
                ),
            }
        file_id = spreadsheet_meta['id']

    logging.info(f"Attendance file: {spreadsheet_meta['name']} ({file_id})")
    logging.info(f"Last modified: {spreadsheet_meta.get('modifiedTime', 'unknown')}")

    # Step 2: Clone so we never touch the original
    clone_id = clone_spreadsheet(drive_svc, file_id, spreadsheet_meta['name'])
    if clone_id is None:
        # Fallback: read the original directly (read-only, safe if we only use Sheets API)
        logging.warning('Clone failed — reading original directly (read-only via Sheets API)')
        working_id = file_id
        is_clone   = False
    else:
        working_id = clone_id
        is_clone   = True

    # Step 3: Read all sheets
    logging.info('Reading spreadsheet tabs...')
    sheets_data = read_all_sheets(sheets_svc, working_id)

    if is_clone:
        delete_drive_file(drive_svc, clone_id)

    if not sheets_data:
        return {'ok': False, 'error': 'No data read from spreadsheet'}

    # Step 4: Parse day/shift tabs
    all_entries: List[Dict[str, Any]] = []
    tab_summary: List[Dict] = []

    for title, rows in sheets_data.items():
        parsed = parse_tab_name(title)
        if parsed is None:
            logging.info(f"  Skipping tab '{title}' (not a day/shift tab)")
            continue

        day_key, shift = parsed

        # Apply tab filter if specified
        if tab_filter:
            tab_norm = re.sub(r'\s+', '', tab_filter.upper())
            title_norm = re.sub(r'\s+', '', title.upper())
            if tab_norm != title_norm:
                continue

        entries = parse_sheet_rows(rows, title, day_key, shift)
        logging.info(f"  Tab '{title}' ({day_key}{shift}): {len(entries)} clients parsed")
        tab_summary.append({'tab': title, 'day_key': day_key, 'shift': shift, 'count': len(entries)})
        all_entries.extend(entries)

    if not all_entries:
        return {
            'ok':          True,
            'warning':     'No entries parsed from any day/shift tab',
            'tabs_found':  list(sheets_data.keys()),
            'tab_summary': tab_summary,
        }

    logging.info(f'Total entries across all tabs: {len(all_entries)}')

    # Step 5: Sync to DB
    if dry_run:
        logging.info('[DRY RUN] No DB writes will occur')
    result = sync_to_db(all_entries, dry_run=dry_run)

    result['source_file']       = spreadsheet_meta['name']
    result['source_file_id']    = file_id
    result['tabs_processed']    = tab_summary
    result['total_entries']     = len(all_entries)
    result['synced_at']         = datetime.now(timezone.utc).isoformat()

    # Write run log
    log_path = LOG_DIR / f'roster_sync_{datetime.now().strftime("%Y-%m-%d_%H%M")}.json'
    try:
        with open(log_path, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        logging.info(f'Log written: {log_path}')
    except Exception as e:
        logging.warning(f'Could not write log: {e}')

    # Print summary
    c = result['counts']
    logging.info(
        f'Sync complete: {c["added"]} added, {c["updated"]} updated, '
        f'{c["not_matched"]} not matched in DB, '
        f'{c["missing_from_drive"]} active DB clients not in Drive'
    )
    if result.get('not_matched'):
        logging.warning(f'  Not matched (will be inserted if not dry-run): '
                        f'{[e["name"] for e in result["not_matched"][:10]]}...')
    if result.get('missing_from_drive'):
        logging.warning(f'  Active in DB but missing from Drive (NOT deactivated — needs Kato approval): '
                        f'{result["missing_from_drive"][:10]}...')

    return result


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Sync GOJ attendance spreadsheet from Google Drive to auth_tracker.db'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and report without writing to DB')
    parser.add_argument('--tab', metavar='TAB',
                        help='Only sync a specific tab, e.g. TH2 or "TH 2"')
    parser.add_argument('--file-id', metavar='FILE_ID',
                        help='Google Drive file ID of the attendance spreadsheet')
    args = parser.parse_args()

    result = run_roster_sync(
        file_id=args.file_id,
        tab_filter=args.tab,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get('ok') else 1)
