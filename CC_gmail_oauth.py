#!/usr/bin/env python3
"""Generate a Google OAuth token with Gmail read scope + Drive readonly."""
import json, os

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]
CREDS_PATH = os.path.expanduser('~/Desktop/REX/google_credentials.json')
TOKEN_PATH = os.path.expanduser('~/Desktop/REX/gmail_token.json')

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
flow.redirect_uri = 'http://localhost:8080'
creds = flow.run_local_server(port=8080, open_browser=False, 
    authorization_prompt_message='Please visit this URL to authorize:\n{url}\n',
    success_message='Authorization complete!')

data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': list(creds.scopes),
    'universe_domain': getattr(creds, 'universe_domain', 'googleapis.com'),
    'account': '',
    'expiry': creds.expiry.isoformat() + 'Z'
}

with open(TOKEN_PATH, 'w') as f:
    json.dump(data, f)

print(f"✅ Token saved: {TOKEN_PATH}")
print(f"Scopes: {creds.scopes}")
