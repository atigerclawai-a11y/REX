#!/usr/bin/env python3
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
