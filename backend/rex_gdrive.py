"""
rex_gdrive.py — Google Drive Integration for REX

Provides:
  • Upload files to a designated REX folder in Google Drive
  • List uploaded files
  • Download / get shareable links
  • Syncs REX's local uploads/ directory to Drive

Uses the same google_credentials.json as Gmail.
Token stored in ~/.rex_google_token.json (shared with Gmail module).
"""

import os
import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("rex.gdrive")

REX_DIR     = Path(__file__).resolve().parent.parent
CREDS_PATH  = REX_DIR / "google_credentials.json"
TOKEN_PATH  = Path.home() / ".rex_google_token.json"
UPLOADS_DIR = REX_DIR / "uploads"

# The Drive folder name where REX keeps its files
DRIVE_FOLDER_NAME = "REX Documents"


def _get_service():
    """Return authenticated Drive API service."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. Run: "
            "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages"
        )

    # Full 4-scope set (same as rex_gmail.py / CC_google_reauth.py). This module
    # writes the refreshed token back; mismatched SCOPES strip the others.
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDS_PATH}. "
                    "Run: python backend/rex_gmail.py --setup"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def is_configured() -> bool:
    return TOKEN_PATH.exists() and CREDS_PATH.exists()


def _get_or_create_rex_folder(svc) -> str:
    """Get or create the 'REX Documents' folder in Drive root. Returns folder ID."""
    # Search for existing folder
    query = f"name='{DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = svc.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Create new folder
    folder_meta = {
        "name":     DRIVE_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = svc.files().create(body=folder_meta, fields="id").execute()
    logger.info(f"Created Drive folder '{DRIVE_FOLDER_NAME}' with id={folder['id']}")
    return folder["id"]


def upload_file(local_path: str, description: str = "") -> Dict[str, Any]:
    """
    Upload a local file to the REX Documents folder in Google Drive.
    Returns: { ok, file_id, name, web_link, error }
    """
    try:
        from googleapiclient.http import MediaFileUpload
        svc = _get_service()
        folder_id = _get_or_create_rex_folder(svc)

        path = Path(local_path)
        if not path.exists():
            return {"ok": False, "error": f"File not found: {local_path}"}

        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"

        file_meta = {
            "name":        path.name,
            "parents":     [folder_id],
            "description": description or f"Uploaded by REX on {__import__('datetime').datetime.now().isoformat()}",
        }
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
        uploaded = svc.files().create(
            body=file_meta, media_body=media, fields="id, name, webViewLink"
        ).execute()

        logger.info(f"Uploaded {path.name} to Drive folder '{DRIVE_FOLDER_NAME}'")
        return {
            "ok":       True,
            "file_id":  uploaded["id"],
            "name":     uploaded["name"],
            "web_link": uploaded.get("webViewLink", ""),
        }
    except Exception as e:
        logger.error(f"Drive upload failed: {e}")
        return {"ok": False, "error": str(e)}


def list_drive_files(max_results: int = 50) -> Dict[str, Any]:
    """List files in the REX Documents Drive folder."""
    try:
        svc = _get_service()
        folder_id = _get_or_create_rex_folder(svc)
        query = f"'{folder_id}' in parents and trashed=false"
        results = svc.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, mimeType, size, modifiedTime, webViewLink)"
        ).execute()
        files = results.get("files", [])
        return {"ok": True, "files": files, "count": len(files)}
    except Exception as e:
        return {"ok": False, "error": str(e), "files": []}


def sync_uploads_to_drive() -> Dict[str, Any]:
    """
    Scan ~/Desktop/REX/uploads/ and upload any files not yet in Drive.
    Returns summary of what was synced.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    synced   = []
    skipped  = []
    errors   = []
    sync_log = UPLOADS_DIR / ".drive_sync.json"

    already_synced: set = set()
    if sync_log.exists():
        try:
            already_synced = set(json.loads(sync_log.read_text()).get("synced", []))
        except Exception:
            pass

    for f in UPLOADS_DIR.iterdir():
        if f.name.startswith(".") or not f.is_file():
            continue
        if f.name in already_synced:
            skipped.append(f.name)
            continue

        result = upload_file(str(f), description=f"Auto-synced from REX local uploads")
        if result["ok"]:
            synced.append(f.name)
            already_synced.add(f.name)
        else:
            errors.append({"file": f.name, "error": result.get("error", "unknown")})

    # Save updated sync log
    try:
        sync_log.write_text(json.dumps({"synced": list(already_synced)}, indent=2))
    except Exception:
        pass

    summary = (
        f"☁️ Drive sync: **{len(synced)} uploaded**, "
        f"{len(skipped)} already synced, "
        f"{len(errors)} error(s)."
    )
    return {"ok": True, "synced": synced, "skipped": skipped, "errors": errors, "summary": summary}


if __name__ == "__main__":
    import sys
    if "--list" in sys.argv:
        result = list_drive_files()
        if result["ok"]:
            print(f"Files in '{DRIVE_FOLDER_NAME}':")
            for f in result["files"]:
                print(f"  {f['name']} — {f.get('webViewLink','')}")
        else:
            print(f"Error: {result['error']}")
    elif "--sync" in sys.argv:
        result = sync_uploads_to_drive()
        print(result["summary"])
    else:
        print("Usage: python backend/rex_gdrive.py --list | --sync")
