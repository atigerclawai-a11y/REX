#!/usr/bin/env python3
"""Refresh Google OAuth token — cron-safe script."""
import json, requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
TOKEN_PATH = HOME / '.rex_google_token.json'
SHARED = HOME / '.hermes' / 'shared' / 'google_token.json'

# Read current token
if not TOKEN_PATH.exists():
    print('ERROR: token file missing')
    exit(1)

token = json.loads(TOKEN_PATH.read_text())

# Check if refresh needed (within 30 minutes of expiry)
expiry_str = token.get('expiry', '')
if expiry_str:
    try:
        expiry = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        if expiry > now + timedelta(minutes=30):
            print(f'Token valid until {expiry_str} — skipping refresh')
            exit(0)
    except:
        pass

# Refresh
resp = requests.post('https://oauth2.googleapis.com/token', data={
    'client_id': token['client_id'],
    'client_secret': token['client_secret'],
    'refresh_token': token['refresh_token'],
    'grant_type': 'refresh_token',
})

if resp.status_code != 200:
    print(f'Refresh FAILED: {resp.status_code} {resp.text[:200]}')
    exit(1)

data = resp.json()
token['token'] = data['access_token']
expiry = (datetime.now(timezone.utc) + timedelta(seconds=data['expires_in'])).isoformat() + 'Z'
token['expiry'] = expiry

# Write to both locations (real files, not symlinks)
TOKEN_PATH.write_text(json.dumps(token, indent=2))
SHARED.write_text(json.dumps(token, indent=2))

print(f'Token refreshed — expires {expiry}')
