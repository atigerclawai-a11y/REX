#!/usr/bin/env python3
"""
CC_google_reauth_headless.py — Phone-based Google OAuth re-authorization.
No browser needed on the Mac. User taps link on phone, pastes redirect URL.

Usage: python3 CC_google_reauth_headless.py
"""
import json
import sys
import shutil
import urllib.parse
import tempfile
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
HOME = str(Path.home())
CREDS_PATH = Path(HOME, "Desktop", "REX", "google_credentials.json")
TOKEN_PATH = Path(HOME, ".rex_google_token.json")
STATE_PATH = Path(tempfile.gettempdir(), "hermes_oauth_verifier.json")

# ── Scopes ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive",
]

# ── Step 1: Generate auth URL with PKCE ─────────────────────────────────
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
flow.redirect_uri = "http://localhost:9999"

auth_url, state = flow.authorization_url(
    access_type="offline",
    prompt="consent",
    include_granted_scopes="true",
)

# Save PKCE verifier so we can complete the exchange later
STATE_PATH.write_text(json.dumps({
    "code_verifier": flow.code_verifier,
    "state": state,
}))

print("=" * 60)
print("OPEN THIS LINK ON YOUR PHONE:")
print()
print(auth_url)
print()
print("=" * 60)
print()
print("After you approve, your browser will try to open 'localhost:9999'")
print("and show an error page. That's fine — just COPY THE ENTIRE URL")
print("from your address bar and paste it here.")
print()
print("The URL will look like:")
print("  http://localhost:9999/?code=4/0A...&state=...&scope=...")
print()

redirect_url = input("Paste the redirect URL: ").strip()

# ── Step 2: Extract code from redirect URL ─────────────────────────────
parsed = urllib.parse.urlparse(redirect_url)
params = urllib.parse.parse_qs(parsed.query)
code = params.get("code", [None])[0]

if not code:
    print("ERROR: No authorization code found in URL. Try again.")
    sys.exit(1)

print("Code extracted successfully.")

# ── Step 3: Exchange code for token ────────────────────────────────────
state_data = json.loads(STATE_PATH.read_text())
flow.code_verifier = state_data["code_verifier"]
flow.redirect_uri = "http://localhost:9999"

try:
    flow.fetch_token(code=code)
except Exception as e:
    print("ERROR: Token exchange failed:", e)
    sys.exit(1)

creds = flow.credentials

if not creds.refresh_token:
    print("ERROR: No refresh token returned.")
    print("  Go to https://myaccount.google.com/permissions")
    print("  Remove the app, then re-run this script.")
    sys.exit(1)

# ── Step 4: Save token ─────────────────────────────────────────────────
if TOKEN_PATH.exists():
    shutil.copy2(TOKEN_PATH, TOKEN_PATH.with_suffix(".json.bak"))

tok_data = json.loads(creds.to_json())
if not tok_data.get("scopes"):
    tok_data["scopes"] = SCOPES
TOKEN_PATH.write_text(json.dumps(tok_data, indent=2))

# Clean up
STATE_PATH.unlink(missing_ok=True)

print()
print("SUCCESS! Token saved.")
print("  Scopes:", tok_data.get("scopes", SCOPES))
print("  Expiry:", creds.expiry)
print("  Refresh token: present")
print()
print("Drive WRITE is now enabled. The hourly cron keeps it alive.")
