#!/usr/bin/env python3
"""
CC_sync_to_pipeline.py
Syncs client_menus (auth_tracker.db) → menu_orders (pipeline.db) after each OCR job.
Best-of-both from Claude + DeepSeek via /claudeseek.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

AUTH_DB     = str(Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db")
PIPELINE_DB = str(Path.home() / ".hermes-cloud" / "home" / "goj-pipeline" / "data" / "pipeline.db")

DAY_OFFSETS = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'SA': 5}


def ensure_unique_index():
    """Ensure menu_orders table + unique index exist in pipeline.db (idempotent)."""
    with sqlite3.connect(PIPELINE_DB) as dst:
        # Create table first so the index creation never fails on a fresh DB
        dst.execute("""
            CREATE TABLE IF NOT EXISTS menu_orders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id  INTEGER NOT NULL,
                date       TEXT    NOT NULL,
                menu_json  TEXT,
                created_at TEXT    DEFAULT (datetime('now')),
                updated_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        dst.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_menu_orders_client_date
            ON menu_orders(client_id, date)
        """)


def sync_menus_to_pipeline(client_id: int | None = None, week_start: str | None = None) -> tuple[int, int]:
    """
    Sync OCR results from auth_tracker.db → pipeline.db.
    If client_id + week_start given: sync just that job's rows.
    If neither given: sync all rows (full backfill).
    Returns (synced, skipped).
    """
    ensure_unique_index()

    src = sqlite3.connect(AUTH_DB)
    src.row_factory = sqlite3.Row

    query = "SELECT client_id, client_name, week_start, day, salad, soup, main, side FROM client_menus WHERE main IS NOT NULL"
    params: list = []
    if client_id is not None and week_start is not None:
        query += " AND client_id = ? AND week_start = ?"
        params = [client_id, week_start]

    rows = src.execute(query, params).fetchall()
    src.close()

    synced = skipped = 0

    with sqlite3.connect(PIPELINE_DB) as dst:
        for row in rows:
            offset = DAY_OFFSETS.get(str(row["day"]).upper())
            if offset is None:
                skipped += 1
                continue

            try:
                week_dt  = datetime.strptime(row["week_start"], "%Y-%m-%d")
                date_str = (week_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                skipped += 1
                continue

            menu_json = json.dumps({
                "salad":       row["salad"],
                "soup":        row["soup"],
                "main":        row["main"],
                "side":        row["side"],
                "client_name": row["client_name"],
                "source":      "ocr",
                "synced_at":   datetime.utcnow().isoformat(),
            })

            dst.execute(
                """
                INSERT INTO menu_orders (client_id, date, menu_json)
                VALUES (?, ?, ?)
                ON CONFLICT(client_id, date) DO UPDATE SET menu_json = excluded.menu_json
                """,
                (row["client_id"], date_str, menu_json),
            )
            synced += 1

    return synced, skipped


if __name__ == "__main__":
    import sys
    cid   = int(sys.argv[1]) if len(sys.argv) > 1 else None
    wk    = sys.argv[2]      if len(sys.argv) > 2 else None
    s, sk = sync_menus_to_pipeline(cid, wk)
    print(f"Sync complete: {s} upserted, {sk} skipped")
