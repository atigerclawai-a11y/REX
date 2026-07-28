#!/usr/bin/env python3
"""
CC_transition_drive_watcher.py — Google Drive Monitoring Hook
Watches GOJ Drive folders for new files, triggers TransitionAgent pipeline.

Captures bookkeeper workflow: QuickBooks exports, receipts, spreadsheets.
Deadline: June 7 2026 — bookkeeper departing.

Runs as daemon every 5 min via launchd.
State tracked in ~/Desktop/REX/.drive_watcher_state.json
"""
import subprocess, sys, json, os, time
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
REX_DIR = HOME / 'Desktop' / 'REX'
STATE_FILE = REX_DIR / '.drive_watcher_state.json'
WATCH_DIR = REX_DIR / 'drive_incoming'
LOG_FILE = REX_DIR / 'scheduled_task_logs' / 'drive_watcher.log'

# Google Drive folder IDs to watch
WATCH_FOLDERS = {
    'goj_ops':      '1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB',  # GOJ Operations root
    'quickbooks':   '1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB',  # ← UPDATE with actual QB folder ID
    'receipts':     '1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB',  # ← UPDATE with actual receipts folder ID
}
CHECK_INTERVAL_MINUTES = 5
FILE_AGE_MINUTES = 60  # Only process files newer than this
EXTENSIONS = ('.xlsx', '.xls', '.csv', '.pdf', '.qbo', '.qbb', '.iif')

WATCH_DIR.mkdir(exist_ok=True)
LOG_FILE.parent.mkdir(exist_ok=True)

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {'seen_files': {}, 'last_check': None}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def _get_google_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    
    TOKEN = HOME / '.rex_google_token.json'
    CREDS = REX_DIR / 'google_credentials.json'
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    
    if not TOKEN.exists():
        log('⚠ No Google token file')
        return None
    
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json())
        except Exception as e:
            log(f'⚠ Token refresh failed: {e}')
            return None
    return creds

def scan_folder(svc, folder_id, folder_name, state):
    """Scan a Drive folder for new files. Returns list of new file metadata."""
    cutoff = (datetime.utcnow() - timedelta(minutes=FILE_AGE_MINUTES)).isoformat() + 'Z'
    new_files = []
    
    try:
        results = svc.files().list(
            q=f"'{folder_id}' in parents and modifiedTime > '{cutoff}' and trashed = false",
            fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
            orderBy="modifiedTime desc",
            pageSize=50
        ).execute()
        
        for f in results.get('files', []):
            fid = f['id']
            fname = f['name']
            
            # Skip non-business files
            if not any(fname.lower().endswith(ext) for ext in EXTENSIONS):
                continue
            
            # Check if already processed
            last_seen = state['seen_files'].get(fid, {})
            last_modified = last_seen.get('modifiedTime', '')
            
            if last_modified == f.get('modifiedTime', ''):
                continue  # Already processed this version
            
            new_files.append(f)
            state['seen_files'][fid] = {
                'name': fname,
                'modifiedTime': f.get('modifiedTime', ''),
                'first_seen': datetime.now().isoformat(),
                'folder': folder_name
            }
        
        if new_files:
            log(f'  {folder_name}: {len(new_files)} new file(s)')
    
    except Exception as e:
        log(f'  ❌ Scan error ({folder_name}): {e}')
    
    return new_files

def download_file(svc, file_id, file_name):
    """Download a file from Drive to the incoming watch directory."""
    dest = WATCH_DIR / file_name
    
    # Avoid overwrites — append timestamp if exists
    if dest.exists():
        stem = Path(file_name).stem
        ext = Path(file_name).suffix
        ts = datetime.now().strftime('%H%M%S')
        dest = WATCH_DIR / f'{stem}_{ts}{ext}'
    
    try:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        
        request = svc.files().get_media(fileId=file_id)
        fh = io.FileIO(str(dest), 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.close()
        log(f'  📥 Downloaded: {file_name} → {dest.name}')
        return str(dest)
    
    except Exception as e:
        log(f'  ❌ Download failed ({file_name}): {e}')
        return None

def trigger_pipeline(downloaded_files):
    """Trigger TransitionAgent for downloaded QuickBooks/receipt files."""
    if not downloaded_files:
        return
    
    log(f'▶ Triggering pipeline for {len(downloaded_files)} file(s)')
    
    # QuickBooks mode: process the incoming files
    # For now, just log them. Full QB processing comes after workflow capture.
    for fpath in downloaded_files:
        fname = Path(fpath).name
        if fname.lower().endswith(('.qbo', '.qbb', '.iif')):
            log(f'  📊 QuickBooks file detected: {fname} — QB processing hook')
        elif fname.lower().endswith(('.xlsx', '.xls', '.csv')):
            log(f'  📊 Spreadsheet detected: {fname}')
        elif fname.lower().endswith('.pdf'):
            log(f'  📄 PDF detected: {fname}')
    
    # Trigger transition supervisor in full mode to process daily docs
    # (includes Drive upload + Gmail summary)
    try:
        result = subprocess.run(
            ['python3', str(REX_DIR / 'transition_supervisor.py'), 'full'],
            capture_output=True, text=True, timeout=300,
            cwd=str(REX_DIR)
        )
        if result.returncode == 0:
            log('  ✅ Pipeline triggered successfully')
        else:
            log(f'  ⚠ Pipeline exit {result.returncode}: {result.stderr[-200:]}')
    except Exception as e:
        log(f'  ❌ Pipeline trigger error: {e}')

def main():
    log('=' * 50)
    log('Drive Watcher — starting scan')
    
    creds = _get_google_creds()
    if not creds:
        log('❌ No Google credentials — aborting')
        return 1
    
    try:
        from googleapiclient.discovery import build
    except ImportError:
        log('❌ google-api-python-client not installed')
        return 1
    
    svc = build('drive', 'v3', credentials=creds)
    state = load_state()
    state['last_check'] = datetime.now().isoformat()
    
    all_new = []
    for folder_name, folder_id in WATCH_FOLDERS.items():
        new_files = scan_folder(svc, folder_id, folder_name, state)
        all_new.extend(new_files)
    
    if all_new:
        log(f'📦 {len(all_new)} new file(s) detected across {len(WATCH_FOLDERS)} folders')
        downloaded = []
        for f in all_new:
            path = download_file(svc, f['id'], f['name'])
            if path:
                downloaded.append(path)
        
        if downloaded:
            trigger_pipeline(downloaded)
    else:
        log('No new files — all clear')
    
    save_state(state)
    log(f'Scan complete — next check in {CHECK_INTERVAL_MINUTES} min')
    return 0

if __name__ == '__main__':
    sys.exit(main())
