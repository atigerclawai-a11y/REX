#!/bin/bash
# CC_ocr_test.command
# Pulls 3-5 completed job paths from ocr_jobs, re-runs process_pdf_local() on them,
# and prints full diagnostics (client names, week, days, inserted/skipped).
# Safe to run multiple times — DB writes are deduped by (client_id, week_start, day).
set -euo pipefail

LOG="$HOME/Desktop/REX/logs/ocr_test_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== CC_ocr_test ==="
echo "Date: $(date)"
echo "Log:  $LOG"
echo ""

source "$HOME/debate-chamber/.venv/bin/activate"
cd "$HOME/Desktop/REX"

python3 - << 'PYEOF'
import sys, os, sqlite3, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / "Desktop" / "REX"))

DB_PATH  = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
GDRIVE   = Path.home() / "Desktop" / "REX" / "gdrive_mirror" / "Menus"
FIXTURES = Path.home() / "Desktop" / "REX" / "tests" / "ocr_fixtures"

# ── Import ────────────────────────────────────────────────────────────────────
try:
    from goj_menu_consensus_ocr import process_pdf_local
    print("✓ goj_menu_consensus_ocr imported OK")
except Exception as e:
    print(f"✗ IMPORT ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# ── Pick test files: prefer done jobs from ocr_jobs, fall back to disk PDFs ──
def pick_test_files(n=5):
    """Return up to n file paths to test, pulling from completed ocr_jobs first."""
    candidates = []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT file_path FROM ocr_jobs WHERE status='completed' "
            "ORDER BY completed_at DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        for (fp,) in rows:
            p = Path(fp)
            if p.exists():
                candidates.append(p)
    except Exception as e:
        print(f"  (ocr_jobs lookup failed: {e})")

    if len(candidates) < n:
        # Fill from fixtures dir first, then gdrive batch PDFs
        for d in [FIXTURES, GDRIVE]:
            if d.exists():
                for p in sorted(d.glob("*.pdf")):
                    if p not in candidates:
                        candidates.append(p)
                    if len(candidates) >= n:
                        break
            if len(candidates) >= n:
                break

    return candidates[:n]

test_files = pick_test_files()
if not test_files:
    print("ERROR: No test PDFs found anywhere. Check gdrive_mirror/Menus/ or ocr_jobs table.")
    sys.exit(1)

print(f"Test files ({len(test_files)}):")
for p in test_files:
    mb = p.stat().st_size / 1_048_576
    print(f"  {p.name}  ({mb:.1f} MB)")
print()

# ── Pre-run DB snapshot ───────────────────────────────────────────────────────
def db_count():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        n = conn.execute("SELECT COUNT(*) FROM client_menus").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return -1

before_total = db_count()
print(f"DB before: {before_total} rows in client_menus")
print()

# ── Run each test file ────────────────────────────────────────────────────────
grand_inserted = 0
grand_skipped  = 0
grand_errors   = 0

for pdf_path in test_files:
    print("─" * 60)
    print(f"FILE: {pdf_path.name}")

    t0 = datetime.now()
    try:
        result = process_pdf_local(str(pdf_path))
    except Exception as e:
        print(f"  ✗ EXCEPTION: {e}")
        traceback.print_exc()
        grand_errors += 1
        print()
        continue
    elapsed = (datetime.now() - t0).total_seconds()

    if result is None:
        print(f"  ✗ returned None  ({elapsed:.1f}s)")
        grand_errors += 1
        print()
        continue

    ins     = result.get('inserted', 0)
    skp     = result.get('skipped',  0)
    results = result.get('_results', [])

    grand_inserted += ins
    grand_skipped  += skp

    print(f"  Elapsed:  {elapsed:.1f}s")
    print(f"  Inserted: {ins}  |  Skipped (dedup): {skp}")
    print(f"  Clients:  {len(results)}")
    print()

    for i, r in enumerate(results[:8]):
        name  = r.get('client_name', '(unknown)')
        cid   = r.get('client_id', '?')
        week  = r.get('week_start', '?')
        conf  = r.get('confidence', None)
        days  = r.get('days', {})
        cf_s  = f"{conf:.2f}" if isinstance(conf, float) else str(conf)
        filled = [d for d, items in days.items() if items and any(items.values())]
        print(f"  [{i+1:02d}] {name[:30]:<30}  wk={week}  conf={cf_s}  days={filled}")

    if len(results) > 8:
        print(f"  … +{len(results)-8} more clients")
    print()

# ── Summary ───────────────────────────────────────────────────────────────────
after_total = db_count()
print("─" * 60)
print("SUMMARY")
print(f"  Files:    {len(test_files)}")
print(f"  Errors:   {grand_errors}")
print(f"  Inserted: {grand_inserted}")
print(f"  Skipped:  {grand_skipped}")
print(f"  DB rows:  {before_total} → {after_total}  (net +{after_total - before_total})")
print()

# ── Latest DB rows ────────────────────────────────────────────────────────────
try:
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT cm.client_id, c.name, cm.week_start, cm.day, cm.main
          FROM client_menus cm
          LEFT JOIN clients c ON c.client_id = cm.client_id
         ORDER BY cm.id DESC LIMIT 15
    """).fetchall()
    conn.close()
    print("Most recent 15 client_menus rows:")
    print(f"  {'id':<6} {'name':<28} {'week_start':<12} {'day':<4} main")
    print(f"  {'─'*5} {'─'*27} {'─'*11} {'─'*3} {'─'*35}")
    for cid, name, ws, day, main in rows:
        print(f"  {str(cid):<6} {(name or '?')[:27]:<28} {str(ws):<12} {str(day):<4} {(main or '')[:35]}")
except Exception as e:
    print(f"DB query error: {e}")

print()
print("Done.")
PYEOF

echo ""
echo "=== CC_ocr_test complete ==="
echo "Log: $LOG"
