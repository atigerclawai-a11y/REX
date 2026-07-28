#!/usr/bin/env python3
"""
Download staff medical files from Gmail.
Targets specific message IDs containing staff medical PDFs and tracking doc.
"""
import os
import json
import base64
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
HOME = Path.home()
TOKEN_PATH = HOME / "Desktop/REX/gmail_token.json"
CREDS_PATH = HOME / "Desktop/REX/google_credentials.json"
STAFF_DIR = HOME / "Documents/goj files/documents/staff"
STAFF_DIR.mkdir(parents=True, exist_ok=True)

# Message IDs containing staff medical files
TARGET_MESSAGES = {
    "19d67a0b629b3296": "Fw: medicals — individual staff medical PDFs",
    "19d67a070114bc35": "Fw: employee medical and inservice as of jan 2026 — tracking doc",
}

# ── Auth ─────────────────────────────────────────────────────────────────────
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            print("❌ No valid Gmail token. Run setup_gmail_token.py first.")
            return None
    return build("gmail", "v1", credentials=creds)

# ── Download ─────────────────────────────────────────────────────────────────
def download_attachments(service, msg_id, description):
    print(f"\n📧 Processing: {description}")
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

    parts = msg.get("payload", {}).get("parts", [])
    if not parts:
        # Try nested
        parts = msg.get("payload", {}).get("parts", [msg.get("payload", {})])

    downloaded = 0
    for part in parts:
        filename = part.get("filename", "")
        if not filename or part.get("mimeType", "") in ("text/plain", "text/html", "image/svg+xml"):
            continue

        # Skip Outlook SVG icons
        if filename.startswith("Outlook-"):
            continue

        attachment_id = part.get("body", {}).get("attachmentId")
        if not attachment_id:
            # Data might be inline
            data = part.get("body", {}).get("data", "")
        else:
            attachment = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()
            data = attachment.get("data", "")

        if not data:
            print(f"  ⚠️  No data for: {filename}")
            continue

        file_data = base64.urlsafe_b64decode(data)
        out_path = STAFF_DIR / filename
        with open(out_path, "wb") as f:
            f.write(file_data)
        print(f"  ✓ Saved: {filename} ({len(file_data):,} bytes)")
        downloaded += 1

    return downloaded

def main():
    print("=" * 60)
    print("  GOJ Staff Medical File Downloader")
    print(f"  Output: {STAFF_DIR}")
    print("=" * 60)

    service = get_gmail_service()
    if not service:
        return

    total = 0
    for msg_id, description in TARGET_MESSAGES.items():
        count = download_attachments(service, msg_id, description)
        total += count

    print(f"\n{'='*60}")
    print(f"✅ Done — {total} files saved to {STAFF_DIR}")
    print(f"\nFiles in staff folder:")
    for f in sorted(STAFF_DIR.iterdir()):
        print(f"  {f.name}")

if __name__ == "__main__":
    main()
