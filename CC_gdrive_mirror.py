#!/usr/bin/env python3
"""
CC_gdrive_mirror.py — Mirror all GOJ Google Drive folders to local disk.

Downloads every file from every GOJ Operations Drive folder into:
  ~/Desktop/REX/gdrive_mirror/{folder_name}/{filename}

Also writes a manifest at gdrive_mirror/MANIFEST.json listing every file,
its Drive ID, size, modified date, and local path.

Needs broader Drive scope than drive.file — will re-auth if required.
Run once manually; after that the token covers ongoing uploads too.
"""
import json, os, sys, io
from pathlib import Path
from datetime import datetime

REX_DIR    = Path.home() / 'Desktop' / 'REX'
MIRROR_DIR = REX_DIR / 'gdrive_mirror'
CREDS_PATH = REX_DIR / 'google_credentials.json'
TOKEN_PATH = Path.home() / '.rex_google_token.json'

# All GOJ Drive folders to mirror
GOJ_FOLDERS = {
    'GOJ_Operations_Root':  '1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB',
    'Sign_In_Sheets':       '1znUHkOMfuSQo9iK1Nnz-SSoWVZdnax6H',
    'Distribution_Sheets':  '1m8GAglqzBKEdrDuU5Am08Hl9MHnOqhsG',
    'Kitchen_Counts':       '1o56SCqK7QZVcDorAo1oyOAwiEu4CyVu8',
    'Driver_Sheets':        '1JCh5oQt9yJODyLB5PGdTLCjxku3a17HG',
    'Calendar_Attendance':  '1VcNscnjp-rVfUHDxty1g-Njla34uUTTl',
    'Menus':                '1OBrFP9NR_1lYm_PLHjXXgnISqtxMxuo4',
}

# Broader scope — allows listing + downloading all shared files
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
]
SA_KEY = Path.home() / '.rex_drive_service_account.json'


def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}')


def get_creds():
    """Service-account auth ONLY (user OAuth permanently banned, Kato hard rule 2026-07).

    Reads what is shared with the SA email. If a source 404s, share it from
    atigerclawai@gmail.com: Share -> goj-drive-reader@solid-idiom-489906-g7.iam.gserviceaccount.com -> Viewer.
    """
    try:
        from google.oauth2 import service_account
    except ImportError:
        print('ERROR: Google API packages not installed.')
        print('Run: pip install google-auth google-auth-httplib2 google-api-python-client --break-system-packages')
        sys.exit(1)

    if not SA_KEY.exists():
        print(f'ERROR: service account key not found at {SA_KEY}')
        sys.exit(1)
    return service_account.Credentials.from_service_account_file(str(SA_KEY), scopes=SCOPES)


def list_folder_files(svc, folder_id: str) -> list:
    """List all non-folder files in a Drive folder (non-recursive)."""
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"

    while True:
        params = {
            'q': query,
            'fields': 'nextPageToken, files(id, name, mimeType, size, modifiedTime)',
            'pageSize': 100,
        }
        if page_token:
            params['pageToken'] = page_token

        result = svc.files().list(**params).execute()
        files.extend(result.get('files', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            break

    return files


def download_file(svc, file_id: str, dest_path: Path, mime_type: str):
    """Download a Drive file to dest_path."""
    from googleapiclient.http import MediaIoBaseDownload

    # Google Workspace files (Docs, Sheets) need export
    export_map = {
        'application/vnd.google-apps.document':     ('application/pdf', '.pdf'),
        'application/vnd.google-apps.spreadsheet':  ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
        'application/vnd.google-apps.presentation': ('application/pdf', '.pdf'),
    }

    if mime_type in export_map:
        export_mime, ext = export_map[mime_type]
        if not dest_path.suffix:
            dest_path = dest_path.with_suffix(ext)
        request = svc.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = svc.files().get_media(fileId=file_id)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    dest_path.write_bytes(buf.getvalue())
    return dest_path


def mirror_folder(svc, folder_name: str, folder_id: str, dest_dir: Path) -> list:
    """Download all files from one Drive folder. Returns list of manifest entries."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    log(f'  Folder: {folder_name}')

    try:
        files = list_folder_files(svc, folder_id)
    except Exception as e:
        log(f'  ❌ Could not list {folder_name}: {e}')
        return []

    if not files:
        log(f'  ℹ  (empty folder)')
        return []

    log(f'  {len(files)} file(s) found')
    entries = []

    for f in files:
        fname = f['name']
        fid   = f['id']
        fmime = f.get('mimeType', '')
        fsize = int(f.get('size', 0))
        fmod  = f.get('modifiedTime', '')
        dest  = dest_dir / fname

        try:
            actual_dest = download_file(svc, fid, dest, fmime)
            log(f'    ✅ {fname} ({fsize:,} bytes)')
            entries.append({
                'folder':        folder_name,
                'folder_id':     folder_id,
                'file_id':       fid,
                'name':          fname,
                'mime_type':     fmime,
                'size_bytes':    fsize,
                'modified':      fmod,
                'local_path':    str(actual_dest),
            })
        except Exception as e:
            log(f'    ❌ {fname}: {e}')
            entries.append({
                'folder':    folder_name,
                'file_id':   fid,
                'name':      fname,
                'error':     str(e),
            })

    return entries


def main():
    print('=' * 60)
    print(f'  GOJ Google Drive Mirror — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 60)

    MIRROR_DIR.mkdir(parents=True, exist_ok=True)

    creds = get_creds()

    try:
        from googleapiclient.discovery import build
    except ImportError:
        print('ERROR: google-api-python-client not installed')
        sys.exit(1)

    svc = build('drive', 'v3', credentials=creds)
    log('Drive service authenticated')

    all_entries = []
    total_files = 0
    total_errors = 0

    for folder_name, folder_id in GOJ_FOLDERS.items():
        entries = mirror_folder(svc, folder_name, folder_id, MIRROR_DIR / folder_name)
        all_entries.extend(entries)
        ok  = sum(1 for e in entries if 'error' not in e)
        err = sum(1 for e in entries if 'error' in e)
        total_files  += ok
        total_errors += err

    # Write manifest
    manifest = {
        'mirrored_at':  datetime.now().isoformat(),
        'total_files':  total_files,
        'total_errors': total_errors,
        'folders':      list(GOJ_FOLDERS.keys()),
        'files':        all_entries,
    }
    manifest_path = MIRROR_DIR / 'MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print()
    print('=' * 60)
    print(f'  Done — {total_files} files downloaded, {total_errors} errors')
    print(f'  Mirror: {MIRROR_DIR}')
    print(f'  Manifest: {manifest_path}')
    print('=' * 60)


if __name__ == '__main__':
    main()
