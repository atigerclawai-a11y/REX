#!/bin/bash
# CC_google_oauth_fix.command
# Forces a proper Google OAuth grant with refresh_token — fixes the "re-auth every 10 min" bug
# Run this ONCE. After this, the token auto-renews forever.

set -e

TOKEN_FILE="$HOME/.rex_google_token.json"
CREDS_FILE="$HOME/Desktop/REX/google_credentials.json"

echo "======================================"
echo "  Google OAuth Permanent Fix"
echo "======================================"
echo ""

# Check credentials
if [ ! -f "$CREDS_FILE" ]; then
    echo "❌ Credentials not found: $CREDS_FILE"
    exit 1
fi

# Delete old broken token
if [ -f "$TOKEN_FILE" ]; then
    echo "🗑  Removing old token (was missing refresh_token)..."
    rm "$TOKEN_FILE"
fi

echo "🔑 Launching OAuth flow (browser will open)..."
echo "   → Sign in as atigerclawai@gmail.com"
echo "   → Click 'Allow' on ALL permission prompts"
echo ""

# Python OAuth with offline access + consent prompt (forces refresh_token)
source "$HOME/debate-chamber/.venv/bin/activate"

python3 - << 'PYEOF'
import json
import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

CREDS_FILE = os.path.expanduser("~/Desktop/REX/google_credentials.json")
TOKEN_FILE = os.path.expanduser("~/.rex_google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

flow = InstalledAppFlow.from_client_secrets_file(
    CREDS_FILE,
    scopes=SCOPES,
)

# Force offline access + consent prompt — this is what generates the refresh_token
creds = flow.run_local_server(
    port=8085,
    access_type="offline",
    prompt="consent",
    open_browser=True,
)

# Save token
token_data = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret,
    "scopes": list(creds.scopes) if creds.scopes else SCOPES,
}

with open(TOKEN_FILE, "w") as f:
    json.dump(token_data, f, indent=2)

print(f"\n✅ Token saved to {TOKEN_FILE}")
if creds.refresh_token:
    print("✅ refresh_token: PRESENT — this token will auto-renew forever")
else:
    print("❌ refresh_token: MISSING — something went wrong, try running again")
    sys.exit(1)

# Quick verify
print("\nVerifying token works...")
from googleapiclient.discovery import build
service = build("gmail", "v1", credentials=creds)
profile = service.users().getProfile(userId="me").execute()
print(f"✅ Gmail connected: {profile['emailAddress']}")
print(f"   Messages: {profile.get('messagesTotal', '?')}")
PYEOF

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ OAuth flow failed. Check the error above."
    exit $EXIT_CODE
fi

echo ""
echo "======================================"
echo "  Done. You will NEVER need to re-auth again."
echo "  The token now lives at: ~/.rex_google_token.json"
echo "======================================"
read -p "Press Enter to close..."
