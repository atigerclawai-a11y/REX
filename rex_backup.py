#!/usr/bin/env python3
"""
REX — Backup & Restore System
================================
Creates timestamped, encrypted snapshots of REX's entire brain:
  • Long-term memory (rex_memory table)
  • Session history (rex_session_log table)
  • All conversation journeys (journeys + messages tables)
  • The encryption key fingerprint (so you know which key made the backup)

Backups are stored at: ~/Desktop/REX/backups/
Each backup is a single .rexbak file (encrypted JSON, AES-256-GCM).

Usage:
    python rex_backup.py                  # Create a backup right now
    python rex_backup.py --list           # List all available backups
    python rex_backup.py --restore        # Restore from most recent backup
    python rex_backup.py --restore N      # Restore from backup number N (from --list)
    python rex_backup.py --restore-file path/to/file.rexbak

The backup runs automatically via run.sh — REX saves a snapshot on every launch
and every shutdown, so you always have a recent version to roll back to.
"""

import os
import sys
import json
import base64
import hashlib
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# ── Auto-switch to venv Python ─────────────────────────────────────────────────
_HERE    = Path(__file__).parent.resolve()
_VENV_PY = _HERE / ".venv" / "bin" / "python"

try:
    import keyring
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
except ImportError:
    if _VENV_PY.exists():
        print("🔄 Re-launching with REX venv Python...")
        os.execv(str(_VENV_PY), [str(_VENV_PY)] + sys.argv)
        sys.exit(0)
    else:
        print("❌  Run ./setup.sh first.")
        sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH      = Path.home() / ".rex" / "rex_journeys.db"
BACKUP_DIR   = _HERE / "backups"
APP_NAME     = "REX-PrivacyProxy"
KEY_NAME     = "rex_master_encryption_key"
MAX_BACKUPS  = 30   # Keep last 30 backups, auto-prune older ones

GREEN  = '\033[92m'
YELLOW = '\033[93m'
RED    = '\033[91m'
BOLD   = '\033[1m'
RESET  = '\033[0m'


# ── Key management ────────────────────────────────────────────────────────────

def get_key() -> bytes:
    stored = keyring.get_password(APP_NAME, KEY_NAME)
    if stored:
        return base64.b64decode(stored)
    raise RuntimeError("No REX encryption key found in Keychain. Start REX first.")


def key_fingerprint(key: bytes) -> str:
    digest = hashlib.sha256(key).hexdigest()
    return f"{digest[:8]}...{digest[-8:]}"


# ── Encryption ────────────────────────────────────────────────────────────────

def encrypt_backup(data: str, key: bytes) -> bytes:
    nonce = os.urandom(12)
    ct    = AESGCM(key).encrypt(nonce, data.encode("utf-8"), None)
    return nonce + ct


def decrypt_backup(payload: bytes, key: bytes) -> str:
    return AESGCM(key).decrypt(payload[:12], payload[12:], None).decode("utf-8")


# ── Database snapshot ─────────────────────────────────────────────────────────

def snapshot_db(db_path: Path) -> dict:
    """Read all REX tables into a plain dict (content stays encrypted as stored)."""
    if not db_path.exists():
        return {"error": "Database not found", "tables": {}}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tables = {}

    for table in ["rex_memory", "rex_session_log", "journeys", "messages", "phi_mappings", "audit_log"]:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            tables[table] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            tables[table] = []   # Table doesn't exist yet — skip silently

    conn.close()
    return tables


# ── Create backup ─────────────────────────────────────────────────────────────

def create_backup(label: str = "") -> Path:
    """Create an encrypted snapshot. Returns path to the .rexbak file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    key       = get_key()
    fingerprint = key_fingerprint(key)

    tables    = snapshot_db(DB_PATH)
    total_rows = sum(len(v) for v in tables.values() if isinstance(v, list))

    # Count active memories specifically
    mem_count = len([r for r in tables.get("rex_memory", []) if r.get("active", 0)])
    ses_count = len([r for r in tables.get("rex_session_log", []) if r.get("active", 0)])

    backup_payload = {
        "version":      "3.0",
        "created_at":   datetime.utcnow().isoformat(),
        "label":        label or f"auto-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
        "key_fingerprint": fingerprint,
        "stats": {
            "active_memories":   mem_count,
            "active_sessions":   ses_count,
            "total_rows":        total_rows,
        },
        "tables": tables,
    }

    raw_json = json.dumps(backup_payload, ensure_ascii=False, default=str)
    encrypted = encrypt_backup(raw_json, key)

    # Filename: rex_YYYYMMDD_HHMMSS_label.rexbak
    ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = (label or "auto").replace(" ", "_")[:24]
    fname = BACKUP_DIR / f"rex_{ts}_{slug}.rexbak"

    fname.write_bytes(encrypted)

    # Prune old backups (keep most recent MAX_BACKUPS)
    all_backups = sorted(BACKUP_DIR.glob("*.rexbak"), key=lambda p: p.stat().st_mtime)
    while len(all_backups) > MAX_BACKUPS:
        oldest = all_backups.pop(0)
        oldest.unlink()

    print(f"{GREEN}✅  Backup created: {fname.name}{RESET}")
    print(f"    Memories: {mem_count} | Sessions: {ses_count} | Total rows: {total_rows}")
    return fname


# ── List backups ──────────────────────────────────────────────────────────────

def list_backups() -> list:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(BACKUP_DIR.glob("*.rexbak"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        print("ℹ️  No backups found. Run: python rex_backup.py")
        return []

    print(f"\n{BOLD}REX Backups — {len(files)} available{RESET}")
    print("=" * 60)
    key = get_key()

    for i, f in enumerate(files):
        try:
            data = json.loads(decrypt_backup(f.read_bytes(), key))
            stats   = data.get("stats", {})
            created = data.get("created_at", "")[:16].replace("T", " ")
            label   = data.get("label", "")
            mems    = stats.get("active_memories", "?")
            sess    = stats.get("active_sessions", "?")
            size_kb = f.stat().st_size // 1024
            print(f"  [{i+1}]  {f.name}")
            print(f"       Created: {created} UTC  |  Memories: {mems}  |  Sessions: {sess}  |  Size: {size_kb}KB")
            if label and not label.startswith("auto-"):
                print(f"       Label: {label}")
            print()
        except Exception as e:
            print(f"  [{i+1}]  {f.name}  ⚠️  Could not read: {e}")

    return files


# ── Restore ───────────────────────────────────────────────────────────────────

def restore_backup(source: Path):
    """Restore REX's database from a .rexbak file."""
    print(f"\n{YELLOW}⚠️  Restoring from: {source.name}{RESET}")
    print("This will REPLACE all current REX memory and session data.")
    ans = input("Type 'restore' to confirm: ").strip().lower()
    if ans != "restore":
        print("Cancelled.")
        return

    key  = get_key()
    data = json.loads(decrypt_backup(source.read_bytes(), key))

    stored_fingerprint = data.get("key_fingerprint", "")
    current_fingerprint = key_fingerprint(key)
    if stored_fingerprint != current_fingerprint:
        print(f"{RED}⚠️  Key mismatch!{RESET}")
        print(f"   Backup key:  {stored_fingerprint}")
        print(f"   Current key: {current_fingerprint}")
        print("   This backup was made with a different encryption key.")
        ans2 = input("   Proceed anyway? (yes/no): ").strip().lower()
        if ans2 not in ("yes", "y"):
            print("Cancelled.")
            return

    tables = data.get("tables", {})

    # Backup current state before overwriting (safety net)
    pre_restore = create_backup(label="pre-restore-auto")
    print(f"  📸  Safety snapshot created before restore: {pre_restore.name}")

    conn = sqlite3.connect(str(DB_PATH))

    for table, rows in tables.items():
        if not rows:
            continue
        try:
            # Clear table
            conn.execute(f"DELETE FROM {table}")
            if rows:
                # Re-insert from backup
                cols    = list(rows[0].keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_str = ", ".join(cols)
                conn.executemany(
                    f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})",
                    [tuple(r[c] for c in cols) for r in rows]
                )
            print(f"  ✅  {table}: {len(rows)} rows restored")
        except Exception as e:
            print(f"  ⚠️  {table}: {e}")

    conn.commit()
    conn.close()

    stats = data.get("stats", {})
    print(f"\n{GREEN}✅  Restore complete!{RESET}")
    print(f"    Memories restored:  {stats.get('active_memories', '?')}")
    print(f"    Sessions restored:  {stats.get('active_sessions', '?')}")
    print(f"    Backup was from:    {data.get('created_at','')[:16].replace('T',' ')} UTC")
    print()
    print("Restart REX to apply: cd ~/Desktop/REX && ./run.sh")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="REX Backup & Restore")
    parser.add_argument("--list",         action="store_true",      help="List all backups")
    parser.add_argument("--restore",      nargs="?", const="latest", help="Restore (latest or backup number)")
    parser.add_argument("--restore-file", metavar="PATH",            help="Restore from specific .rexbak file")
    parser.add_argument("--label",        default="",                help="Label for this backup")
    args = parser.parse_args()

    if args.list:
        list_backups()

    elif args.restore_file:
        src = Path(args.restore_file)
        if not src.exists():
            print(f"❌  File not found: {src}")
            sys.exit(1)
        restore_backup(src)

    elif args.restore is not None:
        files = list_backups()
        if not files:
            sys.exit(1)
        if args.restore == "latest":
            restore_backup(files[0])
        else:
            try:
                idx = int(args.restore) - 1
                restore_backup(files[idx])
            except (ValueError, IndexError):
                print(f"❌  Invalid backup number: {args.restore}")
                sys.exit(1)

    else:
        # Default: create a backup
        label = args.label or input("Backup label (press Enter to skip): ").strip()
        create_backup(label=label)


if __name__ == "__main__":
    main()
