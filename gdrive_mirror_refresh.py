#!/usr/bin/env python3
"""
gdrive_mirror_refresh.py — Complete + incremental refresh of local Drive mirror.
PHI stays local (no cloud, no re-upload). Read-only on Drive.

Sources from CC_goj_drive_ingest.py LIVE_SOURCES plus employee files folder.
Writes only under ~/Desktop/REX/gdrive_mirror/

Run:  python3 gdrive_mirror_refresh.py
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Config ────────────────────────────────────────────────────────────────────

HOME        = Path.home()
MIRROR_DIR  = HOME / "Desktop" / "REX" / "gdrive_mirror"
TOKEN_PATH  = HOME / ".rex_google_token.json"
VENV_PYTHON = HOME / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"

MIRROR_DIR.mkdir(parents=True, exist_ok=True)

# Sources — sheets export every tab as CSV, folders download files
SOURCES = {
    "sign_in": {
        "file_id": "1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8",
        "name": "SIGN IN (27 tabs)",
        "kind": "google_sheet",
        "local_dir": "Sign_In",
    },
    "attendance_tracking": {
        "file_id": "1XQMusZ0-rPx50QDrpf92l1mgEZdHRvmnGwpB9-moSwQ",
        "name": "Attendance Tracking",
        "kind": "google_sheet",
        "local_dir": "Attendance_Tracking",
    },
    "calendar_2026": {
        "file_id": "1giUlw82mlFFfMZOvcZWqBtyB5vNntKliAamQRWzV0IE",
        "name": "Calendar 2026",
        "kind": "google_sheet",
        "local_dir": "Calendar_2026",
    },
    "menu_second_shift": {
        "file_id": "18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0",
        "name": "2026 Second Shift Menu",
        "kind": "google_sheet",
        "local_dir": "Menus/second_shift",
    },
    "menu_first_shift": {
        "file_id": "1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw",
        "name": "2026 First Shift Menu (xlsx)",
        "kind": "xlsx",
        "local_dir": "Menus/first_shift",
    },
    "carecenta_auth": {
        "file_id": "14AVRfWJH9aAuvHec0dRoZ3DgP6MWNJJt",
        "name": "CARECENTA authorizations folder",
        "kind": "folder",
        "local_dir": "CARECENTA_Auth",
    },
    "new_auth": {
        "file_id": "1SZzHuL1PYI2M39gCxoEZrcDj6s8Be8A9",
        "name": "New auth folder",
        "kind": "folder",
        "local_dir": "New_Auth",
    },
    "employee_files": {
        "file_id": "1BZTYJjoJH0tY8_BlGaRQXsVcjKNb4qGM",
        "name": "Employee files folder",
        "kind": "folder",
        "local_dir": "Employee_Files",
    },
}

LOCAL_TEMPLATES_SRC = HOME / "Documents" / "goj files" / "documents"
TEMPLATES_DIR = MIRROR_DIR / "Templates"


# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize_filename(name: str, max_len: int = 200) -> str:
    """Make filename safe for filesystem."""
    name = re.sub(r'[/\\:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:max_len]


def load_manifest() -> Dict[str, Any]:
    manifest_path = MIRROR_DIR / "MANIFEST.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text())
        except Exception:
            pass
    return {"sources": {}}


def save_manifest(manifest: Dict[str, Any]) -> None:
    manifest["generated"] = datetime.now(timezone.utc).isoformat()
    (MIRROR_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


def get_services():
    """Service account ONLY (OAuth permanently banned per Kato's hard rule).

    Key: ~/.rex_drive_service_account.json — share target files/folders with
    the service account email. Same pattern as CC_goj_drive_ingest.get_services().
    """
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    sa_key = Path.home() / ".rex_drive_service_account.json"
    if not sa_key.exists():
        raise RuntimeError(
            "Service account key missing: ~/.rex_drive_service_account.json "
            "(OAuth is banned — restore the SA key, do not fall back to tokens)")
    creds = service_account.Credentials.from_service_account_file(
        str(sa_key),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"])
    drive  = build("drive",  "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    return drive, sheets


# ── Sheet export ──────────────────────────────────────────────────────────────

def export_sheet_tabs(sheets, file_id: str, local_dir: Path, source_key: str,
                      manifest_entry: Dict, old_modified: Optional[str],
                      drive_modified: str) -> Tuple[int, int, List[str]]:
    """Export every tab of a Google Sheet to CSV. Returns (tabs_done, tabs_skipped, local_paths)."""
    # Get list of tabs
    meta = sheets.spreadsheets().get(
        spreadsheetId=file_id,
        fields="sheets(properties(title,sheetId))",
    ).execute()
    tabs = [(s["properties"]["title"], s["properties"]["sheetId"])
            for s in meta.get("sheets", [])]

    local_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    skipped = 0
    paths = []

    for tab_title, sheet_id in tabs:
        safe_name = sanitize_filename(tab_title)
        csv_path = local_dir / f"{safe_name}.csv"
        paths.append(str(csv_path))

        # Incremental: skip if file exists and drive hasn't changed
        if csv_path.exists() and old_modified == drive_modified:
            skipped += 1
            continue

        try:
            resp = sheets.spreadsheets().values().get(
                spreadsheetId=file_id,
                range=tab_title,
            ).execute()
            rows = resp.get("values", [])
            # Write CSV
            import csv
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(row)
            done += 1
        except Exception as e:
            print(f"    WARN: tab '{tab_title}' failed: {e}")

    return done, skipped, paths


def export_xlsx(drive, file_id: str, local_dir: Path, name: str,
                old_modified: Optional[str], drive_modified: str) -> Tuple[int, List[str]]:
    """Download xlsx file directly. Returns (1 if downloaded else 0, paths)."""
    local_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(name) + ".xlsx"
    xlsx_path = local_dir / safe_name

    if xlsx_path.exists() and old_modified == drive_modified:
        return 0, [str(xlsx_path)]

    try:
        req = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        from googleapiclient.http import MediaIoBaseDownload
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done_dl = False
        while not done_dl:
            _, done_dl = dl.next_chunk()
        xlsx_path.write_bytes(buf.getvalue())
        return 1, [str(xlsx_path)]
    except Exception as e:
        print(f"    WARN: xlsx download failed: {e}")
        return 0, [str(xlsx_path)] if xlsx_path.exists() else []


# ── Folder download ───────────────────────────────────────────────────────────

def list_folder_files(drive, folder_id: str) -> List[Dict]:
    """Paginate all files in a folder (non-trashed)."""
    files = []
    page_token = None
    while True:
        res = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name,mimeType,modifiedTime,size)",
            pageSize=500,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return files


def download_folder(drive, folder_id: str, local_dir: Path,
                    manifest_files: Dict[str, str],
                    is_recursive: bool = True) -> Tuple[int, int, int, List[str], List[str]]:
    """
    Download all files in a folder recursively.
    manifest_files: {file_id: drive_modifiedTime} from previous run.
    Returns (downloaded, skipped, errors, local_paths, pending_ids).
    """
    from googleapiclient.http import MediaIoBaseDownload

    local_dir.mkdir(parents=True, exist_ok=True)
    files = list_folder_files(drive, folder_id)
    downloaded = 0
    skipped = 0
    errors = 0
    paths = []
    pending = []

    for f in files:
        fid  = f["id"]
        name = f["name"]
        mime = f["mimeType"]
        mod  = f.get("modifiedTime", "")

        # Recurse into subfolders
        if mime == "application/vnd.google-apps.folder" and is_recursive:
            sub_dir = local_dir / sanitize_filename(name)
            d, s, e, sub_paths, sub_pending = download_folder(
                drive, fid, sub_dir, manifest_files, is_recursive=True
            )
            downloaded += d; skipped += s; errors += e
            paths.extend(sub_paths); pending.extend(sub_pending)
            continue

        # Skip Google native types that can't be downloaded directly
        # (except we could export them — for now skip non-PDFs/docs in folder)
        if mime.startswith("application/vnd.google-apps"):
            # Try to export as PDF for docs/sheets
            if mime in ("application/vnd.google-apps.document",
                         "application/vnd.google-apps.spreadsheet",
                         "application/vnd.google-apps.presentation"):
                safe = sanitize_filename(name) + ".pdf"
                local_path = local_dir / safe
                paths.append(str(local_path))
                old_mod = manifest_files.get(fid)
                if local_path.exists() and old_mod == mod:
                    skipped += 1
                    continue
                try:
                    req = drive.files().export_media(fileId=fid, mimeType="application/pdf")
                    buf = io.BytesIO()
                    dl = MediaIoBaseDownload(buf, req)
                    done_dl = False
                    while not done_dl:
                        _, done_dl = dl.next_chunk()
                    local_path.write_bytes(buf.getvalue())
                    downloaded += 1
                    manifest_files[fid] = mod
                except Exception as e:
                    print(f"    WARN: export {name}: {e}")
                    errors += 1
            continue

        # Regular downloadable file
        safe = sanitize_filename(name)
        # Preserve extension
        if "." not in safe[-8:]:
            # Guess extension from mime
            ext_map = {
                "application/pdf": ".pdf",
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "application/msword": ".doc",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.ms-excel": ".xls",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            }
            ext = ext_map.get(mime, "")
            safe = safe + ext

        local_path = local_dir / safe
        paths.append(str(local_path))

        old_mod = manifest_files.get(fid)
        if local_path.exists() and old_mod == mod:
            skipped += 1
            continue

        try:
            req = drive.files().get_media(fileId=fid, supportsAllDrives=True)
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, req)
            done_dl = False
            while not done_dl:
                _, done_dl = dl.next_chunk()
            local_path.write_bytes(buf.getvalue())
            downloaded += 1
            manifest_files[fid] = mod
            time.sleep(0.05)  # light rate-limit courtesy
        except Exception as e:
            print(f"    WARN: download {name}: {e}")
            errors += 1

    return downloaded, skipped, errors, paths, pending


# ── Templates ─────────────────────────────────────────────────────────────────

def mirror_local_templates() -> Tuple[int, List[str]]:
    """Copy TEMPLATE_*.* and GOJ_Templates_Registry.json to gdrive_mirror/Templates/."""
    import shutil
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    paths = []

    if LOCAL_TEMPLATES_SRC.exists():
        for item in LOCAL_TEMPLATES_SRC.iterdir():
            if item.is_file() and (
                item.name.startswith("TEMPLATE_") or
                item.name == "GOJ_Templates_Registry.json"
            ):
                dest = TEMPLATES_DIR / item.name
                paths.append(str(dest))
                if not dest.exists() or item.stat().st_mtime > dest.stat().st_mtime:
                    shutil.copy2(item, dest)
                    copied += 1

    # Also check ~/Documents/goj files/ root
    goj_root = HOME / "Documents" / "goj files"
    if goj_root.exists():
        for item in goj_root.iterdir():
            if item.is_file() and (
                item.name.startswith("TEMPLATE_") or
                item.name == "GOJ_Templates_Registry.json"
            ):
                dest = TEMPLATES_DIR / item.name
                paths.append(str(dest))
                if not dest.exists() or item.stat().st_mtime > dest.stat().st_mtime:
                    import shutil
                    shutil.copy2(item, dest)
                    copied += 1

    return copied, paths


# ── Drive-side template search ────────────────────────────────────────────────

def fetch_drive_templates(drive, sheets) -> Tuple[int, List[str]]:
    """Search Drive for files named TEMPLATE* and download them."""
    from googleapiclient.http import MediaIoBaseDownload
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    paths = []

    try:
        res = drive.files().list(
            q="name contains 'TEMPLATE' and trashed=false",
            fields="files(id,name,mimeType,modifiedTime)",
            pageSize=50,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])
        for f in files:
            safe = sanitize_filename(f["name"])
            mime = f["mimeType"]
            if mime.startswith("application/vnd.google-apps"):
                safe += ".pdf"
                local_path = TEMPLATES_DIR / safe
                paths.append(str(local_path))
                if local_path.exists():
                    continue
                try:
                    req = drive.files().export_media(fileId=f["id"], mimeType="application/pdf")
                    buf = io.BytesIO()
                    dl = MediaIoBaseDownload(buf, req)
                    done_dl = False
                    while not done_dl:
                        _, done_dl = dl.next_chunk()
                    local_path.write_bytes(buf.getvalue())
                    downloaded += 1
                except Exception as e:
                    print(f"    WARN: template export {f['name']}: {e}")
            else:
                if "." not in safe[-8:]:
                    ext_map = {"application/pdf": ".pdf"}
                    safe += ext_map.get(mime, "")
                local_path = TEMPLATES_DIR / safe
                paths.append(str(local_path))
                if local_path.exists():
                    continue
                try:
                    req = drive.files().get_media(fileId=f["id"], supportsAllDrives=True)
                    buf = io.BytesIO()
                    dl = MediaIoBaseDownload(buf, req)
                    done_dl = False
                    while not done_dl:
                        _, done_dl = dl.next_chunk()
                    local_path.write_bytes(buf.getvalue())
                    downloaded += 1
                except Exception as e:
                    print(f"    WARN: template download {f['name']}: {e}")
    except Exception as e:
        print(f"  WARN: Drive template search failed: {e}")

    return downloaded, paths


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(f"GOJ Drive Mirror Refresh — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mirror dir: {MIRROR_DIR}")
    print("=" * 70)

    # Count before
    before_count = sum(1 for _ in MIRROR_DIR.rglob("*") if _.is_file())
    print(f"\nBEFORE: {before_count} files in mirror\n")

    manifest = load_manifest()
    # Track per-file modifiedTimes for incremental folder downloads
    file_mod_cache: Dict[str, str] = manifest.get("_file_mod_cache", {})

    drive, sheets = get_services()

    new_manifest: Dict[str, Any] = {
        "sources": {},
        "_file_mod_cache": file_mod_cache,
    }
    totals = {"sheets_tabs_exported": 0, "sheets_tabs_skipped": 0,
               "folder_files_downloaded": 0, "folder_files_skipped": 0,
               "folder_errors": 0, "templates_copied": 0}

    # ── 1. Sheets ─────────────────────────────────────────────────────────────
    for key, src in SOURCES.items():
        kind = src["kind"]
        local_dir = MIRROR_DIR / src["local_dir"]
        fid = src["file_id"]

        print(f"\n[{key}] {src['name']} ({kind})")

        # Get drive modified time for this source
        try:
            meta = drive.files().get(
                fileId=fid,
                fields="id,name,mimeType,modifiedTime",
                supportsAllDrives=True,
            ).execute()
            drive_modified = meta.get("modifiedTime", "")
        except Exception as e:
            print(f"  ERROR: cannot get metadata: {e}")
            continue

        old_entry = manifest.get("sources", {}).get(key, {})
        old_modified = old_entry.get("drive_modified")

        if kind == "google_sheet":
            done, skipped, paths = export_sheet_tabs(
                sheets, fid, local_dir, key,
                old_entry, old_modified, drive_modified,
            )
            print(f"  tabs exported: {done}  skipped (unchanged): {skipped}  total tabs: {done+skipped}")
            totals["sheets_tabs_exported"] += done
            totals["sheets_tabs_skipped"] += skipped
            new_manifest["sources"][key] = {
                "file_id": fid,
                "name": src["name"],
                "type": "google_sheet",
                "tab_count": done + skipped,
                "tabs_exported": done,
                "tabs_skipped": skipped,
                "local_paths": paths,
                "drive_modified": drive_modified,
                "status": "complete",
            }

        elif kind == "xlsx":
            dl, paths = export_xlsx(drive, fid, local_dir, src["name"],
                                     old_modified, drive_modified)
            status = "downloaded" if dl else "skipped (unchanged)"
            print(f"  xlsx: {status}")
            totals["sheets_tabs_exported"] += dl
            new_manifest["sources"][key] = {
                "file_id": fid,
                "name": src["name"],
                "type": "xlsx",
                "file_count": 1,
                "local_paths": paths,
                "drive_modified": drive_modified,
                "status": "complete",
            }

        elif kind == "folder":
            print(f"  Listing folder contents...")
            dl, sk, err, paths, pending = download_folder(
                drive, fid, local_dir, file_mod_cache, is_recursive=True
            )
            print(f"  downloaded: {dl}  skipped (unchanged): {sk}  errors: {err}  total: {dl+sk}")
            totals["folder_files_downloaded"] += dl
            totals["folder_files_skipped"]    += sk
            totals["folder_errors"]            += err
            new_manifest["sources"][key] = {
                "file_id": fid,
                "name": src["name"],
                "type": "folder",
                "file_count": dl + sk,
                "files_downloaded": dl,
                "files_skipped": sk,
                "files_errors": err,
                "local_paths": [str(local_dir)],
                "drive_modified": drive_modified,
                "status": "complete" if not pending else "partial",
            }

    # ── 2. Templates ──────────────────────────────────────────────────────────
    print(f"\n[templates] Local TEMPLATE_* files")
    copied, local_tpl_paths = mirror_local_templates()
    print(f"  local templates copied: {copied}")

    print(f"[templates] Drive-side TEMPLATE* search")
    drive_tpl_dl, drive_tpl_paths = fetch_drive_templates(drive, sheets)
    print(f"  drive templates downloaded: {drive_tpl_dl}")

    totals["templates_copied"] = copied + drive_tpl_dl
    all_tpl_paths = list(set(local_tpl_paths + drive_tpl_paths))
    new_manifest["sources"]["templates"] = {
        "type": "templates",
        "name": "GOJ Templates (local + Drive)",
        "file_count": len(all_tpl_paths),
        "local_copied": copied,
        "drive_downloaded": drive_tpl_dl,
        "local_paths": all_tpl_paths,
        "status": "complete",
    }

    # ── 3. Update manifest ────────────────────────────────────────────────────
    new_manifest["_file_mod_cache"] = file_mod_cache
    new_manifest["totals"] = totals
    save_manifest(new_manifest)

    # Count after
    after_count = sum(1 for _ in MIRROR_DIR.rglob("*") if _.is_file())
    mirror_size_mb = sum(f.stat().st_size for f in MIRROR_DIR.rglob("*") if f.is_file()) / 1024 / 1024

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Before: {before_count} files | After: {after_count} files  (+{after_count - before_count})")
    print(f"  Mirror size: {mirror_size_mb:.1f} MB")
    print()
    print("  SHEETS:")
    for key, src in SOURCES.items():
        if src["kind"] in ("google_sheet", "xlsx"):
            entry = new_manifest["sources"].get(key, {})
            tabs = entry.get("tab_count") or entry.get("file_count", 0)
            dl   = entry.get("tabs_exported") or entry.get("files_downloaded", 0)
            sk   = entry.get("tabs_skipped", 0)
            status = entry.get("status", "?")
            print(f"    {key}: {tabs} tabs/files | exported {dl} | skipped {sk} | {status}")
    print()
    print("  FOLDERS:")
    for key, src in SOURCES.items():
        if src["kind"] == "folder":
            entry = new_manifest["sources"].get(key, {})
            total = entry.get("file_count", 0)
            dl    = entry.get("files_downloaded", 0)
            sk    = entry.get("files_skipped", 0)
            err   = entry.get("files_errors", 0)
            status = entry.get("status", "?")
            print(f"    {key}: {total} files | downloaded {dl} | skipped {sk} | errors {err} | {status}")
    print()
    entry = new_manifest["sources"].get("templates", {})
    print(f"  TEMPLATES: {entry.get('file_count',0)} total | local {entry.get('local_copied',0)} | drive {entry.get('drive_downloaded',0)}")
    print()
    print(f"  Manifest: {MIRROR_DIR / 'MANIFEST.json'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
