#!/usr/bin/env python3
"""Sync goj_proprietary.db from REX path → Documents path.
Fixes the DB path mismatch: CC_drive_preflight.py writes to ~/Desktop/REX/,
but generators (goj_kitchen_paired.py, generate_distribution_sheet.py) read
from ~/Documents/goj files/proprietary/.

Runs as no_agent cron. Copies menu + client rows from source → target.
"""

import sqlite3, sys
from pathlib import Path

SRC_DB = Path.home() / "Desktop" / "REX" / "goj_proprietary.db"
DST_DB = Path.home() / "Documents" / "goj files" / "proprietary" / "goj_proprietary.db"

if not SRC_DB.exists():
    print(f"Source DB not found: {SRC_DB}", file=sys.stderr)
    sys.exit(1)

src = sqlite3.connect(str(SRC_DB))
dst = sqlite3.connect(str(DST_DB))

# Get latest menu dates from source
latest_dates = src.execute(
    "SELECT DISTINCT menu_date FROM client_menus ORDER BY menu_date DESC LIMIT 7"
).fetchall()

synced = 0
for (menu_date,) in latest_dates:
    # Count rows at source
    src_count = src.execute(
        "SELECT COUNT(*) FROM client_menus WHERE menu_date=?", (menu_date,)
    ).fetchone()[0]
    
    # Count rows at destination
    dst_count = dst.execute(
        "SELECT COUNT(*) FROM client_menus WHERE menu_date=?", (menu_date,)
    ).fetchone()[0]
    
    # Compare per (source_sheet, count) — total-only comparison hides category
    # drift (Kato loop 2026-08-03: Aug 6 house_standard 6 vs 8 while totals matched)
    src_sheets = {r[0]: r[1] for r in src.execute(
        "SELECT source_sheet, COUNT(*) FROM client_menus WHERE menu_date=? GROUP BY 1", (menu_date,))}
    dst_sheets = {r[0]: r[1] for r in dst.execute(
        "SELECT source_sheet, COUNT(*) FROM client_menus WHERE menu_date=? GROUP BY 1", (menu_date,))}
    if src_count == dst_count and dst_count > 0 and src_sheets == dst_sheets:
        continue  # Already synced (counts AND source_sheet split match)
    
    # Delete old rows for this date at destination
    dst.execute("DELETE FROM client_menus WHERE menu_date=?", (menu_date,))
    
    # Copy from source
    rows = src.execute(
        "SELECT client_name, menu_date, day_code, shift, salad, soup, main, side, "
        "source_sheet, synced_at FROM client_menus WHERE menu_date=?",
        (menu_date,)
    ).fetchall()
    
    # Day code map from Python weekday() (Mon=0..Sun=6)
    _DAY_MAP = ['M', 'T', 'W', 'TH', 'F', 'Sa', 'S']
    
    for row in rows:
        (client_name, menu_date, day_code, shift, salad, soup, main, side,
         source_sheet, synced_at) = row
        
        # Fill NULL day_code from menu_date
        if not day_code:
            from datetime import date
            try:
                dt = date.fromisoformat(menu_date)
                day_code = _DAY_MAP[dt.weekday()]
            except (ValueError, TypeError):
                day_code = 'M'  # fallback
        
        dst.execute(
            "INSERT OR REPLACE INTO client_menus "
            "(client_name, menu_date, day_code, shift, salad, soup, main, side, "
            "source_sheet, synced_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (client_name, menu_date, day_code, shift, salad, soup, main, side,
             source_sheet, synced_at)
        )
    
    new_count = dst.execute(
        "SELECT COUNT(*) FROM client_menus WHERE menu_date=?", (menu_date,)
    ).fetchone()[0]
    
    dst.commit()
    print(f"  {menu_date}: {src_count}→{new_count} rows (was {dst_count})")
    synced += 1

# Also sync clients table
src_clients = src.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
dst_clients = dst.execute("SELECT COUNT(*) FROM clients").fetchone()[0]

if src_clients > dst_clients:
    dst.execute("DELETE FROM clients")
    rows = src.execute("SELECT * FROM clients").fetchall()
    # Get column names
    cols = [d[0] for d in src.execute("PRAGMA table_info(clients)").fetchall()]
    placeholders = ",".join(["?"] * len(cols))
    dst.executemany(
        f"INSERT INTO clients ({','.join(cols)}) VALUES ({placeholders})",
        rows
    )
    dst.commit()
    print(f"  clients: {src_clients} rows synced (was {dst_clients})")

src.close()
dst.close()

if synced > 0:
    print(f"[SYNC] Synced {synced} menu dates to Documents DB")
else:
    print("[SYNC] Already in sync — nothing to do")
