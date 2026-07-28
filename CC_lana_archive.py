#!/usr/bin/env python3
"""CC_lana_archive.py — Archive Lana transcripts via IMAP email + optional Drive (service account, no OAuth).

Usage: python3 CC_lana_archive.py <file_path> [--drive-folder-id FOLDER_ID]

Always emails via Gmail SMTP (IMAP app password from ~/.rex_gmail_imap.json).
If ~/.rex_drive_service_account.json exists, also uploads to Google Drive via service account.
OAuth is never used — permanently banned.
"""
import json, smtplib, sys, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

CREDS_PATH = os.path.expanduser("~/.rex_gmail_imap.json")
SA_KEY_PATH = os.path.expanduser("~/.rex_drive_service_account.json")


def email_file(file_path: str, subject_prefix: str) -> str:
    """Email a file via Gmail SMTP. Returns status string."""
    with open(CREDS_PATH) as f:
        creds = json.load(f)
    email_addr = creds["email"]
    app_password = creds["app_password"]

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    msg = MIMEMultipart()
    msg["From"] = email_addr
    msg["To"] = email_addr
    msg["Subject"] = f"{subject_prefix} — {filename}"

    body = (
        f"Lana Study transcript archive attached.\n"
        f"File: {filename}\n"
        f"Size: {file_size:,} bytes\n"
    )
    msg.attach(MIMEText(body, "plain"))

    with open(file_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(email_addr, app_password)
    server.send_message(msg)
    server.quit()

    return f"✅ Emailed to {email_addr} ({file_size:,} bytes)"


def upload_to_drive(file_path: str, folder_id: str = None) -> str:
    """Upload file to Google Drive via service account. Returns status string."""
    if not Path(SA_KEY_PATH).exists():
        return ""

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = service_account.Credentials.from_service_account_file(
        str(SA_KEY_PATH), scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    filename = os.path.basename(file_path)
    file_metadata = {"name": filename}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    # Search for existing file by name in folder
    query = f"name = '{filename}' and trashed = false"
    if folder_id:
        query += f" and '{folder_id}' in parents"

    results = drive.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
    existing = results.get("files", [])

    media = MediaFileUpload(file_path, mimetype="text/markdown", resumable=True)

    if existing:
        file_id = existing[0]["id"]
        drive.files().update(fileId=file_id, media_body=media).execute()
        link = f"https://drive.google.com/file/d/{file_id}/view"
        return f"📁 Drive updated: {link}"
    else:
        f = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
        link = f"https://drive.google.com/file/d/{f['id']}/view"
        return f"📁 Drive uploaded: {link}"


def main():
    if len(sys.argv) < 2:
        print("Usage: CC_lana_archive.py <file_path> [--drive-folder-id FOLDER_ID] [--imap-only]", file=sys.stderr)
        sys.exit(1)

    file_path = None
    folder_id = None
    imap_only = False
    for i, arg in enumerate(sys.argv[1:], start=1):
        if arg == "--drive-folder-id" and i + 1 < len(sys.argv):
            folder_id = sys.argv[i + 1]
        elif arg == "--imap-only":
            imap_only = True
        elif not arg.startswith("--") and file_path is None:
            file_path = arg

    if file_path is None:
        print("Usage: CC_lana_archive.py <file_path> [--drive-folder-id FOLDER_ID] [--imap-only]", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    subject_prefix = "Lana Study Transcript Archive"
    results = []

    # 1. Email via IMAP wire (always)
    results.append(email_file(file_path, subject_prefix))

    # 2. Drive via service account (unless --imap-only)
    if imap_only:
        results.append("ℹ️ Drive: skipped (--imap-only)")
    elif Path(SA_KEY_PATH).exists():
        try:
            results.append(upload_to_drive(file_path, folder_id))
        except Exception as e:
            results.append(f"⚠️ Drive upload failed: {e}")
    else:
        results.append("ℹ️ Drive: service account key not found — email only")

    for r in results:
        print(r)


if __name__ == "__main__":
    main()
