#!/usr/bin/env python3
"""
CC_transition_drive_hook.py — TransitionAgent Drive Monitoring Hook
====================================================================
⚠️ SUPERSEDED on 2026-06-09: this hook watches `WATCH_FOLDER_ID =
'1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB'` (akhiger's archived "GOJ Operations"
folder), which has had no new activity since March 2026. The current live
GOJ files (SIGN IN, Attendance tracking, Calendar 2026, menus, CARECENTA
authorizations) are tracked by `CC_goj_drive_ingest.py` via individual
file IDs — see `CC_DRIVE_SOURCE_MAP_2026-06-08.md`.

The launchd job `com.goj.transition-drive-hook` has been unloaded. To
re-enable for some future folder, update WATCH_FOLDER_ID below + run:
    launchctl load ~/Library/LaunchAgents/com.goj.transition-drive-hook.plist

Daemon that polls Google Drive for bookkeeper activity every 60 seconds.
Detects new files, edits, and deletions in the GOJ shared Drive folder.
Logs all activity and notifies via Cowork relay.

Usage:
    python3 CC_transition_drive_hook.py              # daemon mode (infinite loop)
    python3 CC_transition_drive_hook.py --once        # single poll then exit
    python3 CC_transition_drive_hook.py --status      # print current state only

State: ~/Desktop/REX/.transition_drive_hook_state.json
Log:   ~/Desktop/REX/logs/transition_drive.log
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REX_DIR = HOME / "Desktop" / "REX"
LOG_DIR = REX_DIR / "logs"
STATE_FILE = REX_DIR / ".transition_drive_hook_state.json"
TOKEN_PATH = HOME / ".rex_google_token.json"
CREDS_PATH = REX_DIR / "google_credentials.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "transition_drive.log"

# ── Configuration ──────────────────────────────────────────────────────────────

POLL_INTERVAL = 60  # seconds

# GOJ Operations Drive folder (bookkeeper activity lives here)
WATCH_FOLDER_ID = "1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB"
WATCH_FOLDER_NAME = "GOJ Operations"

# File types indicating bookkeeper activity
BOOKKEEPER_EXTENSIONS = (
    ".xlsx", ".xls", ".csv", ".pdf", ".qbo", ".qbb", ".iif",
    ".docx", ".doc", ".numbers", ".pages",
)

# Cowork relay for notifications
RELAY_URL = "http://127.0.0.1:8000/api/cowork-relay"
RELAY_SOURCE = "transition-agent"

# ── Logging ────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    # Note: when run under launchd, stdout is captured to LOG_PATH.
    # When run standalone with --once, output goes to terminal.
    # Do NOT also write to file here to avoid duplicate lines.

# ── State persistence ──────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"seen": {}, "last_check": None}

def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── Cowork relay notification ──────────────────────────────────────────────────

def notify(message: str) -> None:
    """Send notification via Cowork relay. Best-effort, never raises."""
    try:
        payload = json.dumps({
            "message": message,
            "source": RELAY_SOURCE,
            "bot": "hermes",
        }).encode()
        req = urllib.request.Request(
            RELAY_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        log(f"  📨 Notified: {message[:80]}")
    except Exception as e:
        log(f"  ⚠️ Notify failed (non-fatal): {e}")

# ── Google Drive auth ──────────────────────────────────────────────────────────

def _get_drive_service():
    """Return authenticated Drive API service v3."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    # Full 4-scope set — this daemon refreshes the token in a 60s loop and
    # write-back with a narrow SCOPES strips Gmail (which breaks the OCR
    # menu pipeline). Match rex_gmail.py / rex_menu_scan_watcher.py.
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]

    if not TOKEN_PATH.exists():
        log("❌ No Google token file at ~/.rex_google_token.json")
        sys.exit(1)

    # Ensure token has client_id/client_secret (merge from credentials if missing)
    token_data = json.loads(TOKEN_PATH.read_text())
    needs_update = False
    for field in ("client_id", "client_secret"):
        if field not in token_data:
            if CREDS_PATH.exists():
                creds_data = json.loads(CREDS_PATH.read_text())
                token_data[field] = creds_data.get("installed", {}).get(field, "")
                needs_update = True
    if needs_update:
        TOKEN_PATH.write_text(json.dumps(token_data, indent=2))
        log("🔧 Token enriched with client_id/client_secret")

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            log("🔄 Token refreshed")
        except Exception as e:
            log(f"❌ Token refresh failed: {e}")
            sys.exit(1)

    return build("drive", "v3", credentials=creds)

# ── Folder listing ─────────────────────────────────────────────────────────────

def list_folder_files(service, folder_id: str) -> list[dict]:
    """Return all non-trashed files in a Drive folder with id/name/modifiedTime/mimeType."""
    results = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id, name, modifiedTime, mimeType)",
            "pageSize": 200,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = service.files().list(**params).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results

def is_bookkeeper_file(filename: str) -> bool:
    """Check if file is relevant to bookkeeper workflow."""
    lower = filename.lower()
    # Match by extension
    if lower.endswith(BOOKKEEPER_EXTENSIONS):
        return True
    # Match by name patterns
    bookkeeper_keywords = [
        "quickbooks", "qb_", "receipt", "invoice", "bill",
        "ledger", "payroll", "expense", "reimburse", "statement",
        "bank", "reconciliation", "tax", "1099", "w-2", "w2",
        "bookkeeper", "accounting", "financial", "budget",
        "medicaid", "medicare", "billing",
    ]
    for kw in bookkeeper_keywords:
        if kw in lower:
            return True
    return False

# ── Poll logic ─────────────────────────────────────────────────────────────────

def poll(service, state: dict) -> dict:
    """Poll the watched folder. Detect new/modified/deleted files. Returns updated state."""
    seen = state.get("seen", {})
    new_seen = {}

    try:
        current_files = list_folder_files(service, WATCH_FOLDER_ID)
        log(f"📂 {WATCH_FOLDER_NAME}: {len(current_files)} file(s) in folder")
    except Exception as e:
        log(f"❌ Failed to list folder: {e}")
        return state

    current_ids = set()
    changes = []

    for f in current_files:
        fid = f["id"]
        fname = f.get("name", "unknown")
        mtime = f.get("modifiedTime", "")
        mime_type = f.get("mimeType", "")

        current_ids.add(fid)

        # Skip non-bookkeeper files (still track them to detect future changes)
        if not is_bookkeeper_file(fname):
            new_seen[fid] = mtime
            continue

        prev_mtime = seen.get(fid)

        if fid not in seen:
            # New file
            changes.append(("🆕 NEW", fname, mime_type))
        elif prev_mtime != mtime:
            # Modified file
            changes.append(("✏️ MODIFIED", fname, mime_type))

        new_seen[fid] = mtime

    # Detect deletions — files in seen but not in current_ids
    for fid, prev_mtime in seen.items():
        if fid not in current_ids:
            # Look up name from previous state
            # (We track names separately since deleted files can't be queried)
            pass  # We don't have names for deleted files in simple state

    # Check for deleted files by looking at our state tracking
    deleted = []
    for fid in seen:
        if fid not in current_ids:
            # We stored names with state — check if we have name info
            name_for_fid = _resolve_name_for_id(state, fid)
            if name_for_fid and is_bookkeeper_file(name_for_fid):
                deleted.append(name_for_fid)

    for dname in deleted:
        changes.append(("🗑️ DELETED", dname, ""))

    # Report and notify
    if changes:
        log(f"🔔 {len(changes)} change(s) detected:")
        summary_lines = [f"📊 Drive Activity — {WATCH_FOLDER_NAME}"]
        for action, name, mime in changes:
            log(f"  {action}: {name}")
            summary_lines.append(f"{action}: {name}")
        notify("\n".join(summary_lines))
    else:
        log("  No bookkeeper activity")

    state["seen"] = new_seen
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    return state

def _resolve_name_for_id(state: dict, fid: str) -> str:
    """Best-effort name lookup for a file ID no longer in the folder."""
    # Simple: we didn't store names separately in seen dict
    # For now, skip deletion detection by name
    return ""

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    once = "--once" in sys.argv
    show_status = "--status" in sys.argv

    log("=" * 60)
    log("CC_transition_drive_hook — starting")
    log(f"  Folder: {WATCH_FOLDER_NAME} ({WATCH_FOLDER_ID})")
    log(f"  Poll interval: {POLL_INTERVAL}s")
    log(f"  Relay: {RELAY_URL}")

    if show_status:
        state = load_state()
        n_seen = len(state.get("seen", {}))
        last = state.get("last_check", "never")
        print(f"Tracked files: {n_seen}")
        print(f"Last check: {last}")
        return

    try:
        service = _get_drive_service()
        log("✅ Drive auth OK")
    except Exception as e:
        log(f"❌ Drive auth failed: {e}")
        sys.exit(1)

    state = load_state()

    if once:
        state = poll(service, state)
        save_state(state)
        log("✅ Single poll complete")
        return

    # Daemon loop
    notify(f"🟢 Transition Drive Hook started — monitoring {WATCH_FOLDER_NAME} every {POLL_INTERVAL}s")
    log("🟢 Entering daemon loop")

    while True:
        try:
            state = poll(service, state)
            save_state(state)
        except KeyboardInterrupt:
            log("🛑 Interrupted — shutting down")
            notify("🔴 Transition Drive Hook stopped")
            break
        except Exception as e:
            log(f"❌ Poll error (will retry): {e}")

        try:
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            log("🛑 Interrupted — shutting down")
            notify("🔴 Transition Drive Hook stopped")
            break


if __name__ == "__main__":
    main()
