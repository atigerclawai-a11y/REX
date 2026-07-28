#!/usr/bin/env python3
"""
GOJ/GHS Session Backup Utility
Exports SQLite conversation state to timestamped JSON backup files.
Called by agent_launcher.py before switching agents.
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

BACKUP_DIR = Path.home() / "Desktop" / "REX" / "session_backups"


def ensure_backup_dir():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _rows_to_dicts(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cursor.fetchall()]
    cursor.execute(f"SELECT * FROM {table}")
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def backup_sqlite_db(db_path: str, agent_id: str, label: str = "") -> str | None:
    """
    Export all tables from a SQLite DB to a JSON backup file.
    Returns the path of the backup file, or None if DB not found.
    """
    db = Path(db_path).expanduser()
    if not db.exists():
        return None

    ensure_backup_dir()

    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{agent_id}_{ts}.json"
    if label:
        fname = f"{agent_id}_{label}_{ts}.json"
    out_path = BACKUP_DIR / fname

    backup = {
        "agent_id":   agent_id,
        "db_path":    str(db),
        "timestamp":  datetime.now().isoformat(),
        "label":      label,
        "tables":     {}
    }

    try:
        conn = sqlite3.connect(db)
        cur  = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]

        for table in tables:
            try:
                backup["tables"][table] = _rows_to_dicts(cur, table)
            except Exception as e:
                backup["tables"][table] = {"_error": str(e)}

        conn.close()

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=2, default=str)

        size_kb = out_path.stat().st_size // 1024
        print(f"  ✓ Backup saved: {fname} ({size_kb} KB)")
        return str(out_path)

    except Exception as e:
        print(f"  ✗ Backup failed for {db}: {e}")
        return None


def backup_agent(agent_config: dict) -> list[str]:
    """
    Back up all databases for a given agent registry entry.
    Returns list of backup file paths created.
    """
    paths = []
    db = agent_config.get("db")
    if db:
        result = backup_sqlite_db(db, agent_config["id"], agent_config["name"])
        if result:
            paths.append(result)
    return paths


def list_backups(agent_id: str | None = None) -> list[dict]:
    """List all backup files, optionally filtered by agent_id."""
    ensure_backup_dir()
    backups = []
    for f in sorted(BACKUP_DIR.glob("*.json"), reverse=True):
        if agent_id and not f.name.startswith(agent_id):
            continue
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "path":     str(f),
            "size_kb":  stat.st_size // 1024,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return backups


def restore_backup(backup_path: str, target_db: str) -> bool:
    """
    Restore a JSON backup into a SQLite DB.
    WARNING: This replaces existing data in matched tables.
    """
    backup_file = Path(backup_path)
    db_file     = Path(target_db).expanduser()

    if not backup_file.exists():
        print(f"  ✗ Backup file not found: {backup_path}")
        return False

    with open(backup_file, encoding="utf-8") as f:
        backup = json.load(f)

    conn = sqlite3.connect(db_file)
    cur  = conn.cursor()

    restored = 0
    for table, rows in backup.get("tables", {}).items():
        if isinstance(rows, list) and rows:
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?" for _ in cols])
            col_str = ", ".join(cols)
            try:
                cur.execute(f"DELETE FROM {table}")
                for row in rows:
                    cur.execute(
                        f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})",
                        [row.get(c) for c in cols]
                    )
                restored += 1
            except Exception as e:
                print(f"  ⚠  Table {table}: {e}")

    conn.commit()
    conn.close()
    print(f"  ✓ Restored {restored} tables from {backup_file.name}")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "restore":
        restore_backup(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    else:
        print("Usage: python3 session_backup.py restore <backup.json> <target.db>")
        print("\nAvailable backups:")
        for b in list_backups()[:10]:
            print(f"  {b['modified']}  {b['filename']}  ({b['size_kb']} KB)")
