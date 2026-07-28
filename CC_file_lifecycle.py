#!/usr/bin/env python3
"""
CC_file_lifecycle.py — GOJ File Lifecycle Watcher
=================================================
Watches output_docs/ for new PDFs. When a newer version of a file appears
(same type + date + shift), auto-archives the old one to CC_archive/.

Usage:
    python3 CC_file_lifecycle.py --watch       # Watch continuously
    python3 CC_file_lifecycle.py --once         # Single sweep
    python3 CC_file_lifecycle.py --dry-run      # Show what would be archived

File patterns detected:
    Kitchen_Day_{Day}_{Date}_S{Shift}.pdf
    Distribution_Day_{Day}_{Date}_S{Shift}.pdf
    distribution_shift{Shift}_{Date}.pdf
    GOJ_{Code}_S{Shift}_{Day}_signin.pdf
    GOJ_{Code}_S{Shift}_{Day}_drivers.pdf
    Menus_{Week}_*.pdf
"""
from __future__ import annotations

import os
import re
import sys
import time
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

# ── Hardcoded Paths ────────────────────────────────────────────────────────
OUTPUT_DIR  = Path.home() / "Documents" / "goj files" / "output_docs"
ARCHIVE_DIR = Path.home() / "Desktop" / "REX" / "CC_archive" / "file_lifecycle"
DONE_LOG    = OUTPUT_DIR / ".lifecycle_archived.json"
DRY_RUN      = "--dry-run" in sys.argv

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# ── File Pattern Matching ──────────────────────────────────────────────────

FILE_PATTERNS = [
    # Kitchen sheets: Kitchen_Day_Mon_2026-06-30_S1.pdf
    (r"Kitchen_Day_(\w+)_(\d{4}-\d{2}-\d{2})_S(\d)\.pdf", "kitchen"),
    # Distribution sheets (goj_distribution style): Distribution_Day_Mon_2026-06-30_S1.pdf
    (r"Distribution_Day_(\w+)_(\d{4}-\d{2}-\d{2})_S(\d)\.pdf", "distribution"),
    # Distribution sheets (standalone style): distribution_shift1_2026-06-30.pdf
    (r"distribution_shift(\d)_(\d{4}-\d{2}-\d{2})\.pdf", "distribution"),
    # Sign-in sheets: GOJ_M_S1_Monday_signin.pdf
    (r"GOJ_(\w+)_S(\d)_(\w+)_signin\.pdf", "signin"),
    # Driver routes: GOJ_M_S1_Monday_drivers.pdf
    (r"GOJ_(\w+)_S(\d)_(\w+)_drivers\.pdf", "drivers"),
    # Weekly menus: Menus_Week_2026-06-15.pdf
    (r"Menus_Week_(\d{4}-\d{2}-\d{2})\.pdf", "menus_weekly"),
    # Personalized menus: Menus_Mon_S1_2026-06-16.pdf
    (r"Menus_(\w+)_S(\d)_(\d{4}-\d{2}-\d{2})\.pdf", "menus_daily"),
]


def classify_file(filename: str) -> "dict | None":
    """Classify a filename into type + key for dedup matching."""
    for pattern, ftype in FILE_PATTERNS:
        m = re.match(pattern, filename)
        if m:
            groups = m.groups()
            if ftype == "kitchen":
                return {"type": ftype, "key": f"kitchen_{groups[1]}_S{groups[2]}"}
            elif ftype == "distribution":
                return {"type": ftype, "key": f"distribution_{groups[-1]}_S{groups[-2] if len(groups) == 3 else groups[0]}"}
            elif ftype in ("signin", "drivers"):
                return {"type": ftype, "key": f"{ftype}_{groups[2]}_S{groups[1]}"}
            elif ftype == "menus_weekly":
                return {"type": ftype, "key": f"menus_weekly_{groups[0]}"}
            elif ftype == "menus_daily":
                return {"type": ftype, "key": f"menus_{groups[0]}_S{groups[1]}_{groups[2]}"}
    return None


def sweep() -> dict:
    """Single sweep: find files, auto-archive old versions, return report."""
    files = sorted(OUTPUT_DIR.glob("*.pdf"))
    
    # Group files by their canonical key
    groups = defaultdict(list)
    for f in files:
        info = classify_file(f.name)
        if info:
            info["path"] = f
            info["mtime"] = f.stat().st_mtime
            info["size"] = f.stat().st_size
            groups[info["key"]].append(info)
    
    archived = []
    kept = []
    
    for key, entries in groups.items():
        if len(entries) <= 1:
            kept.extend(entries)
            continue
        
        # Sort by modification time — newest first
        entries.sort(key=lambda e: e["mtime"], reverse=True)
        
        # Keep the newest, archive the rest
        newest = entries[0]
        kept.append(newest)
        
        for old in entries[1:]:
            # Skip if it's the same file (by hash)
            if _hash_file(old["path"]) == _hash_file(newest["path"]):
                continue
            
            archive_path = ARCHIVE_DIR / old["path"].name
            # Add timestamp to avoid name collisions
            if archive_path.exists():
                ts = datetime.fromtimestamp(old["mtime"]).strftime("%Y%m%d_%H%M%S")
                archive_path = ARCHIVE_DIR / f"{old['path'].stem}_{ts}.pdf"
            
            if not DRY_RUN:
                shutil.move(str(old["path"]), str(archive_path))
            
            archived.append({
                "file": old["path"].name,
                "key": key,
                "type": old["type"],
                "mtime": datetime.fromtimestamp(old["mtime"]).isoformat(),
                "archived_to": str(archive_path),
                "reason": f"Superseded by {newest['path'].name}"
            })
    
    return {
        "sweep_time": datetime.now().isoformat(),
        "total_files": len(files),
        "unique_groups": len(groups),
        "kept": len(kept),
        "archived": len(archived),
        "archived_files": archived,
        "dry_run": DRY_RUN
    }


def _hash_file(path: Path) -> str:
    """Quick hash for dedup."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read(4096))  # First 4KB is enough for PDF dedup
    return h.hexdigest()


def watch():
    """Watch output_docs/ continuously, sweep every 60s."""
    print(f"👁 Watching {OUTPUT_DIR} for new files...")
    print(f"   Archive: {ARCHIVE_DIR}")
    print(f"   Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
    
    seen = set()
    try:
        while True:
            result = sweep()
            new_archived = [a for a in result["archived_files"] if a["file"] not in seen]
            
            if new_archived:
                print(f"\n📦 {datetime.now().strftime('%H:%M:%S')} — {len(new_archived)} files archived:")
                for a in new_archived:
                    print(f"   🗑️ {a['file']} → {a['reason']}")
                seen.update(a["file"] for a in new_archived)
            
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Watcher stopped.")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        result = sweep()
        print(f"📋 Sweep complete: {result['total_files']} files, {result['unique_groups']} groups")
        print(f"   Kept: {result['kept']}  Archived: {result['archived']}")
        if result["archived_files"]:
            print(f"\nArchived files:")
            for a in result["archived_files"]:
                print(f"   🗑️ {a['file']} → {a['archived_to']}")
