#!/usr/bin/env python3
"""
CC_DB_CLEANUP_AND_SYNTAXCHECK.py
Cleans false-match and wrong-week rows from auth_tracker.db,
then verifies goj_menu_ocr.py imports without errors.
Run once: ~/Desktop/REX/.venv/bin/python3 ~/Desktop/REX/CC_DB_CLEANUP_AND_SYNTAXCHECK.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

print(f"DB: {DB_PATH}")
if not DB_PATH.exists():
    print("ERROR: DB not found!")
    exit(1)

conn = sqlite3.connect(str(DB_PATH))
cur  = conn.cursor()

# ── Show schema so we know what columns exist ──────────────────────────────────
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='client_menus'")
row = cur.fetchone()
print("\nclient_menus schema:")
print(row[0] if row else "(table not found)")

# ── Helper: preview rows before deleting ──────────────────────────────────────
def preview_and_delete(label, where_clause, params):
    cur.execute(f"SELECT id, client_id, client_name, week_start, day FROM client_menus WHERE {where_clause}", params)
    rows = cur.fetchall()
    print(f"\n--- {label} ---")
    if rows:
        for r in rows:
            print(f"  id={r[0]}  client_id={r[1]}  name={r[2]}  week={r[3]}  day={r[4]}")
        cur.execute(f"DELETE FROM client_menus WHERE {where_clause}", params)
        conn.commit()
        print(f"  → Deleted {len(rows)} row(s)")
    else:
        print("  (no matching rows found)")

# ── Bug 2: Delete false-match rows ────────────────────────────────────────────
# Rukhlevich Svetlana (client_id 734) — week 2026-05-04
preview_and_delete(
    "Bug2: Rukhlevich Svetlana (id=734) week=2026-05-04",
    "client_id=? AND week_start=?",
    (734, "2026-05-04")
)

# Kiselyova Raisa (client_id 582) — week 2026-05-04
preview_and_delete(
    "Bug2: Kiselyova Raisa (id=582) week=2026-05-04",
    "client_id=? AND week_start=?",
    (582, "2026-05-04")
)

# Mikler Galina (client_id 665) — weeks 2026-05-04 AND 2026-04-27
preview_and_delete(
    "Bug2: Mikler Galina (id=665) week=2026-05-04",
    "client_id=? AND week_start=?",
    (665, "2026-05-04")
)
preview_and_delete(
    "Bug2: Mikler Galina (id=665) week=2026-04-27",
    "client_id=? AND week_start=?",
    (665, "2026-04-27")
)

# ── Bug 4: Delete wrong-week rows (week_start=2026-04-20) ─────────────────────
# Posadova Liubov — any day, week 2026-04-20
preview_and_delete(
    "Bug4: Posadova Liubov week=2026-04-20",
    "client_name LIKE ? AND week_start=?",
    ("%Posadova%", "2026-04-20")
)

# Grabovskaya Larisa — any day, week 2026-04-20
preview_and_delete(
    "Bug4: Grabovskaya Larisa week=2026-04-20",
    "client_name LIKE ? AND week_start=?",
    ("%Grabovskaya%", "2026-04-20")
)

conn.close()
print("\n✅ DB cleanup complete.")

# ── Syntax check ──────────────────────────────────────────────────────────────
print("\n--- Syntax check: goj_menu_ocr.py ---")
import importlib.util, sys
ocr_path = Path(__file__).parent / "goj_menu_ocr.py"
spec = importlib.util.spec_from_file_location("goj_menu_ocr", ocr_path)
mod  = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("import OK — no syntax errors")
except Exception as e:
    print(f"ERROR: {e}")
