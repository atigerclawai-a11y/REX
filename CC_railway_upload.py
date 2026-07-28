#!/usr/bin/env python3
"""
CC_railway_upload.py — Upload GOJ documents to goldhealthsys.com
=================================================================
Uploads generated PDFs from output_docs/ to the Railway-hosted
staff dashboard at goldhealthsys.com.

Usage:
    python3 CC_railway_upload.py --all              # Upload all new PDFs
    python3 CC_railway_upload.py --date 2026-07-01  # Upload specific date
    python3 CC_railway_upload.py --dry-run           # Show what would upload

Railway endpoint: POST https://goldhealthsys.com/api/documents/upload
Auth: RAILWAY_API_KEY in ~/.hermes/profiles/work/.env
"""

from __future__ import annotations

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path.home() / "Documents" / "goj files" / "output_docs"
UPLOAD_LOG = OUTPUT_DIR / ".railway_uploaded.json"
RAILWAY_URL = "https://goldhealthsys.com/api/documents/upload"

def get_api_key() -> str:
    """Read Railway API key from env."""
    env_path = Path.home() / ".hermes" / "profiles" / "work" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("RAILWAY_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    main_env = Path.home() / ".hermes" / ".env"
    if main_env.exists():
        for line in main_env.read_text().splitlines():
            if line.startswith("RAILWAY_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def get_uploaded() -> set:
    """Load set of already-uploaded file hashes."""
    if UPLOAD_LOG.exists():
        return set(json.loads(UPLOAD_LOG.read_text()))
    return set()


def save_uploaded(hashes: set):
    """Save set of uploaded hashes."""
    UPLOAD_LOG.write_text(json.dumps(list(hashes)))


def hash_file(path: Path) -> str:
    """SHA-256 for dedup."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_file(path: Path, api_key: str) -> bool:
    """Upload a single PDF to Railway. Returns True on success."""
    cmd = [
        "curl", "-s", "-X", "POST", RAILWAY_URL,
        "-H", f"Authorization: Bearer {api_key}",
        "-F", f"file=@{path}",
        "-F", f"filename={path.name}",
        "--connect-timeout", "30",
        "--max-time", "120"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
    
    if result.returncode == 0:
        try:
            resp = json.loads(result.stdout)
            if resp.get("status") == "ok":
                return True
            print(f"  ⚠️ Upload rejected: {resp.get('error', result.stdout[:100])}")
        except json.JSONDecodeError:
            # Non-JSON response might still be success (HTML redirect)
            if "200" in result.stdout or "success" in result.stdout.lower():
                return True
            print(f"  ⚠️ Unexpected response: {result.stdout[:100]}")
    else:
        print(f"  ❌ Upload failed: {result.stderr[:200]}")
    return False


def upload_all(dry_run: bool = False, date_filter: str = None):
    """Upload all new PDFs to Railway."""
    api_key = get_api_key()
    if not api_key:
        print("❌ RAILWAY_API_KEY not found in .env")
        return
    
    uploaded = get_uploaded()
    files = sorted(OUTPUT_DIR.glob("*.pdf"))
    
    if date_filter:
        files = [f for f in files if date_filter in f.name]
    
    new_files = []
    for f in files:
        h = hash_file(f)
        if h not in uploaded:
            new_files.append((f, h))
    
    if not new_files:
        print(f"📋 All {len(files)} files already uploaded")
        return
    
    print(f"📤 Uploading {len(new_files)} new files to {RAILWAY_URL}...")
    
    success = 0
    for f, h in new_files:
        if dry_run:
            print(f"  [DRY RUN] {f.name} ({f.stat().st_size} bytes)")
            success += 1
        else:
            print(f"  ⬆️ {f.name}...", end=" ")
            if upload_file(f, api_key):
                uploaded.add(h)
                print("✅")
                success += 1
            else:
                print("❌")
    
    if not dry_run:
        save_uploaded(uploaded)
    
    print(f"\n✅ {success}/{len(new_files)} uploaded")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    date_filter = None
    
    for i, arg in enumerate(sys.argv):
        if arg == "--date" and i + 1 < len(sys.argv):
            date_filter = sys.argv[i + 1]
    
    if "--all" in sys.argv or len(sys.argv) == 1:
        upload_all(dry_run=dry_run, date_filter=date_filter)
    else:
        print(__doc__)
