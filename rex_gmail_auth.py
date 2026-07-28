#!/usr/bin/env python3
"""
rex_gmail_auth.py — One-time Gmail OAuth setup for REX
=======================================================
Run this ONCE on your Mac to generate the Gmail token.
It will open a browser window — just click Allow.

After it completes, ~/.rex_google_token.json will exist and
all other REX Gmail scripts will work automatically.

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages

Run:
    cd ~/Desktop/REX
    python rex_gmail_auth.py
"""

import sys
from pathlib import Path

CREDS_PATH = Path.home() / "Desktop" / "REX" / "google_credentials.json"
TOKEN_PATH = Path.home() / ".rex_google_token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ── Check credentials file ────────────────────────────────────────────────────
if not CREDS_PATH.exists():
    print("❌  google_credentials.json not found at:")
    print(f"    {CREDS_PATH}")
    print()
    print("  To fix:")
    print("  1. Go to https://console.cloud.google.com/apis/credentials")
    print("  2. Find your OAuth 2.0 Client ID (type: Desktop app)")
    print("  3. Click the download icon → save as google_credentials.json")
    print("  4. Move it to ~/Desktop/REX/google_credentials.json")
    print("  5. Re-run this script")
    sys.exit(1)

# ── Import libraries ──────────────────────────────────────────────────────────
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("❌  Missing Google API libraries.")
    print()
    print("  Run this first:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
    sys.exit(1)

# ── Check for existing valid token ────────────────────────────────────────────
creds = None
if TOKEN_PATH.exists():
    print(f"📂  Found existing token at {TOKEN_PATH}")
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.valid:
            print("✅  Token is valid — no re-auth needed.")
        elif creds and creds.expired and creds.refresh_token:
            print("🔄  Token expired — refreshing...")
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            print("✅  Token refreshed and saved.")
        else:
            print("⚠️   Token invalid — will re-authenticate.")
            creds = None
    except Exception as e:
        print(f"⚠️   Could not load token ({e}) — will re-authenticate.")
        creds = None

# ── Run OAuth flow if needed ──────────────────────────────────────────────────
if not creds or not creds.valid:
    print()
    print("🌐  Opening browser for Google sign-in...")
    print("    → Sign in with the GOJ Gmail account")
    print("    → Click 'Allow' to grant read access")
    print()
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"✅  Token saved → {TOKEN_PATH}")

# ── Verify by listing inbox ───────────────────────────────────────────────────
print()
print("🔍  Verifying access — checking Gmail inbox...")
svc = build("gmail", "v1", credentials=creds)
profile = svc.users().getProfile(userId="me").execute()
email   = profile.get("emailAddress", "unknown")
total   = profile.get("messagesTotal", 0)
print(f"   ✅  Connected as: {email}")
print(f"   📬  Total messages: {total:,}")
print()
print("✅  Gmail auth complete. You can now run:")
print("   python goj_ingest_all.py")
