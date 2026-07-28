#!/usr/bin/env python3
"""
Run this ONCE on Mac to re-authorize Google token with full Drive + Gmail scopes.
Saves to ~/.rex_google_token.json (shared by all experiment teams).

Run: cd ~/Desktop/REX && .venv/bin/python3 reauth_google_full.py
"""
import json, os
from pathlib import Path

CREDS_FILE = Path("~/Desktop/REX/google_credentials.json").expanduser()
TOKEN_FILE = Path("~/.rex_google_token.json").expanduser()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

print("Opening browser for Google authorization...")
print("Scopes being requested:")
for s in SCOPES:
    print(f"  {s}")
print()

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
creds = flow.run_local_server(port=0)

token_data = {
    "access_token":  creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri":     creds.token_uri,
    "client_id":     creds.client_id,
    "client_secret": creds.client_secret,
    "scopes":        list(creds.scopes),
}
TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
print(f"\n✅ Token saved to {TOKEN_FILE}")
print(f"   Scopes: {list(creds.scopes)}")
