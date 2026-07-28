#!/bin/bash
# Quick test: Engine 2 (Google Drive OCR) auth check
cd "$HOME/Desktop/REX"
source .venv/bin/activate 2>/dev/null || true

echo "=== Engine 2 (Google Drive) Auth Test ==="
echo ""

python3 - <<'PYEOF'
import os, sys

token_path = os.path.expanduser("~/.rex_google_token.json")
if not os.path.exists(token_path):
    print("❌ Token file not found at ~/.rex_google_token.json")
    sys.exit(1)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/documents']

creds = Credentials.from_authorized_user_file(token_path, SCOPES)
if creds.expired and creds.refresh_token:
    print("  Refreshing token...")
    creds.refresh(Request())

if not creds.valid:
    print("❌ Credentials invalid after refresh attempt")
    sys.exit(1)

print("✅ Token loaded and valid")
print("")
print("  Testing Drive API call...")

service = build('drive', 'v3', credentials=creds)
results = service.files().list(pageSize=3, fields="files(id, name)").execute()
files = results.get('files', [])
print(f"✅ Drive API working — found {len(files)} files (listing first 3)")
for f in files:
    print(f"   - {f['name']}")

print("")
print("✅ Engine 2 fully operational!")
PYEOF

echo ""
read -n 1 -p "Press any key to close..."
