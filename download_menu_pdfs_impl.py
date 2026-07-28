#!/usr/bin/env python3
"""
GOJ Menu PDF Downloader
=======================
Downloads all pending menu PDFs from Gmail (forwarded by Allen Khiger)
and registers them in the dashboard auth_tracker.db.

Emails to process (8 PDFs from April 4, 2026):
  - doc00167620260330143130.pdf  25MB  (March 30 scan)
  - doc00167720260330143248.pdf  20MB  (March 30 scan)
  - doc00167820260330143352.pdf  17MB  (March 30 scan)
  - doc00189720260403100057.pdf   2MB  (April 3 scan)
  - doc00189920260403100157.pdf   2MB  (April 3 scan)
  - doc00190420260403121359.pdf  14MB  (April 3 scan)
  - doc00198320260403154200.pdf  22MB  (April 3 scan)
  - doc00198520260403162451.pdf   1MB  (April 3 scan)

Week delivered: April 6-10, 2026
"""

import os
import sys
import json
import base64
import sqlite3
from pathlib import Path
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
DASHBOARD    = Path.home() / "Documents" / "goj files" / "dashboard"
DB_PATH      = DASHBOARD / "auth_tracker.db"
MENUS_DIR    = DASHBOARD / "documents" / "menus"
CREDS_FILE   = SCRIPT_DIR / "google_credentials.json"

# Week that these menus deliver
WEEK_START = date(2026, 4, 6)   # Monday April 6, 2026
SCAN_DATE  = date(2026, 3, 30)  # Earliest scan date

# Gmail message IDs and their attachments
EMAILS = [
    {
        "message_id": "19d5720c403b2736",
        "filename": "doc00167620260330143130.pdf",
        "size_bytes": 25129408,
        "label": "Menu (March 30 batch 1)",
    },
    {
        "message_id": "19d56572c638493f",
        "filename": "doc00167720260330143248.pdf",
        "size_bytes": 19946269,
        "label": "Menu (March 30 batch 2)",
    },
    {
        "message_id": "19d5610067936f9f",
        "filename": "doc00167820260330143352.pdf",
        "size_bytes": 17343147,
        "label": "Menu (March 30 batch 3)",
    },
    {
        "message_id": "19d5604f33622807",
        "filename": "doc00189720260403100057.pdf",
        "size_bytes": 1715211,
        "label": "Sign-in (April 3 batch 1)",
    },
    {
        "message_id": "19d560489c99e9e9",
        "filename": "doc00189920260403100157.pdf",
        "size_bytes": 2066046,
        "label": "Sign-in (April 3 batch 2)",
    },
    {
        "message_id": "19d56036b11ce00a",
        "filename": "doc00190420260403121359.pdf",
        "size_bytes": 13695387,
        "label": "Menus (April 3 noon)",
    },
    {
        "message_id": "19d5603007ff6a08",
        "filename": "doc00198320260403154200.pdf",
        "size_bytes": 22122760,
        "label": "Menus (April 3 afternoon)",
    },
    {
        "message_id": "19d560244978fd0e",
        "filename": "doc00198520260403162451.pdf",
        "size_bytes": 830643,
        "label": "Misc (April 3 end of day)",
    },
]

# ── OAuth Token Discovery ─────────────────────────────────────────────────────
# CANONICAL TOKEN: ~/.rex_google_token.json — always check this first
TOKEN_SEARCH_PATHS = [
    Path.home() / ".rex_google_token.json",          # canonical — all scripts use this
    Path.home() / "Desktop" / "REX" / "gmail_token.json",
    Path.home() / "Desktop" / "REX" / "token.json",
    SCRIPT_DIR / "gmail_token.json",
    SCRIPT_DIR / "token.json",
    Path.home() / ".config" / "google-gmail-mcp" / "credentials.json",
    Path.home() / ".config" / "gcp-oauth.keys.json",
    Path.home() / "Library" / "Application Support" / "google-gmail-mcp" / "token.json",
    Path.home() / "Library" / "Application Support" / "Claude" / "gmail_token.json",
    Path.home() / ".gmail_token.json",
]


def find_token():
    print("🔍 Looking for Gmail OAuth token...")
    for p in TOKEN_SEARCH_PATHS:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if "access_token" in data or "refresh_token" in data:
                    print(f"   ✓ Found token at: {p}")
                    return data, p
            except Exception:
                pass
    return None, None


def refresh_access_token(token_data, creds):
    """Use refresh_token to get a new access_token."""
    import urllib.request
    import urllib.parse

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None

    print("   🔄 Refreshing access token...")
    body = urllib.parse.urlencode({
        "client_id":     creds["installed"]["client_id"],
        "client_secret": creds["installed"]["client_secret"],
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("access_token")
    except Exception as e:
        print(f"   ❌ Token refresh failed: {e}")
        return None


def gmail_get_attachment(access_token, message_id, attachment_id):
    """Download attachment bytes from Gmail API."""
    import urllib.request
    url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/"
        f"{message_id}/attachments/{attachment_id}"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            # Gmail returns URL-safe base64
            raw = data.get("data", "").replace("-", "+").replace("_", "/")
            return base64.b64decode(raw + "==")
    except Exception as e:
        print(f"     ❌ Attachment download failed: {e}")
        return None


def gmail_get_message(access_token, message_id):
    """Get message metadata to find attachment IDs."""
    import urllib.request
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"     ❌ Message fetch failed: {e}")
        return None


def find_attachment_id(message, filename):
    """Recursively find attachment part ID by filename."""
    def _search(parts):
        for part in parts:
            if part.get("filename") == filename:
                return part.get("body", {}).get("attachmentId")
            if "parts" in part:
                result = _search(part["parts"])
                if result:
                    return result
        return None
    return _search(message.get("payload", {}).get("parts", []))


def register_in_db(filename, stored_path_rel, file_size):
    """Register a menu PDF in the auth_tracker.db menus table."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Check if already registered
    cur.execute("SELECT menu_id FROM menus WHERE original_filename=?", (filename,))
    if cur.fetchone():
        conn.close()
        return False  # already exists

    cur.execute("""
        INSERT INTO menus (
            original_filename, file_path,
            menu_date, week_start, file_type,
            uploaded_by, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        filename,
        stored_path_rel,
        SCAN_DATE.isoformat(),
        WEEK_START.isoformat(),
        "pdf",
        "auto_downloader",
        "Downloaded from Gmail (Allen Khiger forward, April 4 2026)",
    ))
    conn.commit()
    conn.close()
    return True


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Load credentials
    if not CREDS_FILE.exists():
        print(f"❌ credentials file not found: {CREDS_FILE}")
        return 1

    creds = json.loads(CREDS_FILE.read_text())

    # Find token
    token_data, token_path = find_token()
    if not token_data:
        print()
        print("❌ No Gmail OAuth token found.")
        print()
        print("The token file isn't in the expected places.")
        print("To fix this, run the following ONE-TIME setup:")
        print()
        print("  1. Open Terminal")
        print("  2. Run:")
        print("       cd ~/Desktop/REX")
        print("       .venv/bin/python3 setup_gmail_token.py")
        print("  3. A browser will open — log in with atigerclawai@gmail.com")
        print("  4. Once done, double-click this downloader again")
        print()
        # Write setup script
        _write_setup_script()
        print("   (setup_gmail_token.py has been written to ~/Desktop/REX/)")
        return 1

    # Get/refresh access token
    access_token = token_data.get("access_token")
    if not access_token or _token_likely_expired(token_data):
        access_token = refresh_access_token(token_data, creds)
        if not access_token:
            print("❌ Could not get a valid access token. Try deleting the token file and re-running.")
            return 1
        # Save refreshed token
        token_data["access_token"] = access_token
        token_path.write_text(json.dumps(token_data, indent=2))
        print("   ✓ Token refreshed and saved.")

    # Ensure menus directory exists
    MENUS_DIR.mkdir(parents=True, exist_ok=True)

    print()
    print(f"📂 Saving PDFs to: {MENUS_DIR}")
    print(f"📅 Registering for week: {WEEK_START} (April 6-10, 2026)")
    print()

    downloaded = 0
    skipped = 0
    failed = 0

    for email_info in EMAILS:
        msg_id = email_info["message_id"]
        filename = email_info["filename"]
        label = email_info["label"]
        dest = MENUS_DIR / filename

        print(f"  📄 {filename}  ({label})")

        if dest.exists():
            size_ok = abs(dest.stat().st_size - email_info["size_bytes"]) < 100_000
            if size_ok:
                print(f"     ✓ Already on disk — skipping download")
                # Still register in DB if not there
                rel = str(dest.relative_to(MENUS_DIR))
                register_in_db(filename, rel, dest.stat().st_size)
                skipped += 1
                continue

        # Get message to find attachment ID
        print(f"     Fetching message metadata...")
        msg = gmail_get_message(access_token, msg_id)
        if not msg:
            failed += 1
            continue

        att_id = find_attachment_id(msg, filename)
        if not att_id:
            print(f"     ❌ Attachment ID not found in message")
            failed += 1
            continue

        # Download attachment
        print(f"     Downloading ({email_info['size_bytes']//1_000_000}MB)...")
        data = gmail_get_attachment(access_token, msg_id, att_id)
        if not data:
            failed += 1
            continue

        # Save file
        dest.write_bytes(data)
        actual_size = dest.stat().st_size
        print(f"     ✓ Saved ({actual_size:,} bytes)")

        # Register in DB
        rel = filename
        added = register_in_db(filename, rel, actual_size)
        if added:
            print(f"     ✓ Registered in database")
        else:
            print(f"     ℹ️  Already in database")

        downloaded += 1

    print()
    print("=" * 50)
    print(f"  Downloaded:  {downloaded}")
    print(f"  Skipped:     {skipped} (already on disk)")
    print(f"  Failed:      {failed}")
    print("=" * 50)

    return 0 if failed == 0 else 1


def _token_likely_expired(token_data):
    """Check if token expiry is in the past."""
    expiry = token_data.get("expiry") or token_data.get("token_expiry") or token_data.get("expires_at")
    if not expiry:
        return False  # can't tell, try it
    from datetime import datetime, timezone
    try:
        if isinstance(expiry, (int, float)):
            exp_dt = datetime.fromtimestamp(expiry, tz=timezone.utc)
        else:
            exp_dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        return exp_dt < datetime.now(tz=timezone.utc)
    except Exception:
        return False


def _write_setup_script():
    """Write a one-time OAuth setup script."""
    setup = SCRIPT_DIR / "setup_gmail_token.py"
    setup.write_text('''#!/usr/bin/env python3
"""Run this ONCE to authorize Gmail access. A browser will open."""
from pathlib import Path
import json

SCRIPT_DIR = Path(__file__).parent
CREDS = SCRIPT_DIR / "google_credentials.json"
TOKEN = SCRIPT_DIR / "gmail_token.json"

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "google-auth-oauthlib", "google-auth-httplib2",
                           "google-api-python-client", "--break-system-packages"])
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
creds = flow.run_local_server(port=0)

token_data = {
    "access_token":  creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri":     creds.token_uri,
    "client_id":     creds.client_id,
    "client_secret": creds.client_secret,
    "scopes":        list(creds.scopes),
}
TOKEN.write_text(json.dumps(token_data, indent=2))
print(f"✅ Token saved to {TOKEN}")
print("Now double-click download_menu_pdfs.command to download the PDFs.")
''')
    print(f"   Wrote: {setup}")


if __name__ == "__main__":
    sys.exit(main())
