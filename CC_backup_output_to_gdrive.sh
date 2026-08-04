#!/bin/bash
# CC_backup_output_to_gdrive.sh — Daily output backup to Google Drive
# Cron: b6c93f4f223e — GDrive Output Backup (23:00 daily)
# Created by Blue Team #194 — 2026-08-04
# Uploads REX outputs to GDrive for off-machine safety.

set -euo pipefail

LOG="$HOME/Desktop/REX/logs/gdrive_backup.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== GDrive Output Backup — $(date) ==="

# ── Python upload script ──────────────────────────────────────────────
python3 << 'PYEOF'
import os, sys, json, time, io
from pathlib import Path
from datetime import datetime, timezone

HOME = Path.home()
TOKEN_PATH = HOME / ".rex_google_token.json"
OUTPUT_DIR = HOME / "Desktop" / "REX" / "output"
BACKUP_DIR = HOME / "Desktop" / "REX" / "Platform_Backups"

if not TOKEN_PATH.exists():
    print("❌ No Google token at", TOKEN_PATH, "— skipping backup", file=sys.stderr)
    sys.exit(0)

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request
except ImportError as e:
    print(f"❌ Import error: {e} — skipping backup", file=sys.stderr)
    sys.exit(0)

# Auth
with open(TOKEN_PATH) as f:
    creds_data = json.load(f)
creds = Credentials(
    token=creds_data.get("token"),
    refresh_token=creds_data.get("refresh_token"),
    token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
    client_id=creds_data.get("client_id"),
    client_secret=creds_data.get("client_secret"),
    scopes=creds_data.get("scopes", ["https://www.googleapis.com/auth/drive"]),
)
if creds.expired:
    creds.refresh(Request())
    with open(TOKEN_PATH, 'w') as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        }, f)

service = build("drive", "v3", credentials=creds)

# Find or create backup folder
FOLDER_NAME = "REX_Daily_Backups"
folder_id = None
resp = service.files().list(
    q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
    spaces="drive", fields="files(id,name)"
).execute()
for f in resp.get("files", []):
    folder_id = f["id"]
    break

if not folder_id:
    folder_meta = {
        "name": FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=folder_meta, fields="id").execute()
    folder_id = folder["id"]
    print(f"📁 Created folder: {FOLDER_NAME} ({folder_id})")

# Upload files from output directories
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
uploaded = 0

for src_dir in [OUTPUT_DIR, BACKUP_DIR]:
    if not src_dir.exists():
        continue
    for filepath in src_dir.rglob("*"):
        if not filepath.is_file():
            continue
        if filepath.stat().st_size == 0:
            continue
        # Skip hidden and system files
        if filepath.name.startswith("."):
            continue
        # Only upload files modified in the last 7 days
        mtime = filepath.stat().st_mtime
        if time.time() - mtime > 7 * 86400:
            continue

        try:
            file_meta = {"name": filepath.name, "parents": [folder_id]}
            media = MediaFileUpload(str(filepath), resumable=True)
            service.files().create(body=file_meta, media_body=media, fields="id").execute()
            uploaded += 1
        except Exception as e:
            print(f"⚠️  Failed to upload {filepath.name}: {e}", file=sys.stderr)

print(f"✅ Uploaded {uploaded} files to GDrive folder '{FOLDER_NAME}'")
PYEOF

echo "=== Done: $(date) ==="
