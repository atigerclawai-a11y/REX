#!/usr/bin/env python3
"""
download_menu_scan.py — Download the menu scan Allen forwarded today.
Run on the Mac: python3 ~/Desktop/REX/download_menu_scan.py
"""
import json, base64, sys
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
        'google-api-python-client', 'google-auth-httplib2',
        'google-auth-oauthlib', '--break-system-packages', '-q'])
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

TOKEN_PATHS = [
    Path.home() / '.rex_google_token.json',
    Path.home() / 'Desktop' / 'REX' / '.rex_google_token.json',
    Path.home() / 'Desktop' / 'REX' / 'GOJ_Backups' / 'GOJ_2026-04-19_06-11' / 'gmail' / 'gmail_token.json',
]

creds = None
for tp in TOKEN_PATHS:
    if tp.exists():
        print(f"Using token: {tp}")
        creds = Credentials.from_authorized_user_info(json.loads(tp.read_text()))
        break

if not creds:
    print("ERROR: No Google token found.")
    sys.exit(1)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    print("Token refreshed OK")

service = build('gmail', 'v1', credentials=creds)

MSG_ID = '19db0aa25350c803'  # Allen's forwarded scan — April 20 4:03 PM

OUT_DIR = Path.home() / 'Documents' / 'goj files' / 'menu_scans_incoming'
OUT_DIR.mkdir(parents=True, exist_ok=True)
print(f"Saving to: {OUT_DIR}")

msg = service.users().messages().get(userId='me', id=MSG_ID, format='full').execute()
payload = msg.get('payload', {})

def find_attachments(parts, msg_id):
    saved = []
    for part in parts:
        fname = part.get('filename', '')
        if fname:
            att_id = part.get('body', {}).get('attachmentId')
            data   = part.get('body', {}).get('data')
            if att_id:
                att  = service.users().messages().attachments().get(
                    userId='me', messageId=msg_id, id=att_id).execute()
                data = att['data']
            if data:
                fb  = base64.urlsafe_b64decode(data)
                out = OUT_DIR / fname
                out.write_bytes(fb)
                print(f"  ✓ {fname}  ({len(fb):,} bytes)  →  {out}")
                saved.append(out)
        for sub in part.get('parts', []):
            saved += find_attachments([sub], msg_id)
    return saved

parts = payload.get('parts', [payload])
files = find_attachments(parts, MSG_ID)

if not files:
    print("  No attachments found in this message.")
else:
    print(f"\nDownloaded {len(files)} file(s).")
    print("Next step: upload the file(s) into the Cowork chat so the menu OCR can process them.")
