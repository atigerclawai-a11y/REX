#!/usr/bin/env python3
"""
Direct Google OAuth token refresh using refresh_token from ~/.rex_google_token.json.
Does NOT import CC_drive_oauth_runner (which binds port 8085 at import time).
Updates both ~/.rex_google_token.json and ~/.hermes/profiles/cloud/google_token.json.

Usage:
    cd ~/Desktop/REX && ~/.rex-venv/bin/python3 direct_token_refresh.py
"""
import json, os, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

TOKEN_PATH = os.path.expanduser("~/.rex_google_token.json")
CLOUD_TOKEN = os.path.expanduser("~/.hermes/profiles/cloud/google_token.json")

if not os.path.exists(TOKEN_PATH):
    print(f"ERROR: Token file not found at {TOKEN_PATH}")
    sys.exit(1)

with open(TOKEN_PATH) as f:
    token_data = json.load(f)

refresh_token = token_data.get("refresh_token")
client_id = token_data.get("client_id")
client_secret = token_data.get("client_secret")

if not refresh_token or not client_id or not client_secret:
    print("ERROR: Token file missing refresh_token, client_id, or client_secret")
    sys.exit(1)

print(f"Refreshing token (client_id: {client_id[:30]}...)")

data = urllib.parse.urlencode({
    'client_id': client_id,
    'client_secret': client_secret,
    'refresh_token': refresh_token,
    'grant_type': 'refresh_token'
}).encode()

req = urllib.request.Request(
    'https://oauth2.googleapis.com/token',
    data=data,
    headers={'Content-Type': 'application/x-www-form-urlencoded'}
)

try:
    resp = urllib.request.urlopen(req)
    new_data = json.loads(resp.read())

    new_access_token = new_data.get('access_token')
    expires_in = new_data.get('expires_in', 0)

    if not new_access_token:
        print("ERROR: Refresh response has no access_token")
        print(json.dumps(new_data, indent=2))
        sys.exit(1)

    # Update token files
    token_data['token'] = new_access_token
    token_data['access_token'] = new_access_token
    token_data['expiry'] = datetime.now(timezone.utc).isoformat()

    with open(TOKEN_PATH, 'w') as f:
        json.dump(token_data, f, indent=2)
    print(f"Token refreshed ({expires_in}s). Updated {TOKEN_PATH}")

    # Also copy to cloud profile
    cloud_dir = os.path.dirname(CLOUD_TOKEN)
    if os.path.exists(cloud_dir):
        with open(CLOUD_TOKEN, 'w') as f:
            json.dump(token_data, f, indent=2)
        print(f"Also copied to {CLOUD_TOKEN}")

except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"Refresh FAILED: HTTP {e.code} — {body}")
    sys.exit(1)
except Exception as e:
    print(f"Refresh FAILED: {e}")
    sys.exit(1)
