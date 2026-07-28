#!/bin/bash
# CC_ocr_backfill.command — GOJ Menu OCR Backfill
# Double-click to re-process all unprocessed PDFs through the full pipeline.
# Logs to ~/Desktop/REX/logs/ocr_backfill_YYYYMMDD_HHMMSS.log
#
# Pipeline order:
#   1. Clear stale worker lock (if PID is dead)
#   2. Find PDFs in menus dir not yet in queue → enqueue
#   3. Run OCR worker (hybrid mode, all pending)
#   4. Run oversight agent --fix-all (Claude Vision QC)
#   5. Print summary

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────────────
REX_DIR="$HOME/Desktop/REX"
VENV="$HOME/debate-chamber/.venv/bin/python3"
LOGS_DIR="$REX_DIR/logs"
MENUS_DIR="$HOME/Documents/goj files/dashboard/documents/menus"
LOCK_FILE="$REX_DIR/locks/ocr_worker.lock"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOGS_DIR/ocr_backfill_${TIMESTAMP}.log"

mkdir -p "$LOGS_DIR"

# Tee all output to log file
exec > >(tee "$LOG_FILE") 2>&1

echo "========================================================"
echo " GOJ OCR Backfill — $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log: $LOG_FILE"
echo "========================================================"

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [ ! -f "$VENV" ]; then
    echo "❌ venv not found at $VENV"
    echo "   Try: source ~/debate-chamber/.venv/bin/activate"
    exit 1
fi

if [ ! -d "$MENUS_DIR" ]; then
    echo "⚠️  Menus directory not found: $MENUS_DIR"
    echo "   No PDFs to process. Gmail may not have deposited any yet."
    echo "   Re-run after Gmail token is re-authed and menus arrive."
    exit 0
fi

# ── Step 0: Clear stale worker lock ───────────────────────────────────────────
echo ""
echo "── Step 0: Check worker lock ──────────────────────────"
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "✋ Worker lock held by live PID $LOCK_PID — another worker is running."
        echo "   If this is wrong, manually delete: $LOCK_FILE"
        exit 1
    else
        echo "🗑  Clearing stale lock (PID $LOCK_PID is not running)"
        rm -f "$LOCK_FILE"
    fi
else
    echo "✅ No lock file — clear to proceed"
fi

# ── Step 1: Count PDFs in menus dir ───────────────────────────────────────────
echo ""
echo "── Step 1: Scan menus directory ───────────────────────"
PDF_COUNT=$(find "$MENUS_DIR" -name "*.pdf" -type f 2>/dev/null | wc -l | tr -d ' ')
echo "   Found $PDF_COUNT PDF(s) in: $MENUS_DIR"

if [ "$PDF_COUNT" -eq 0 ]; then
    echo "   Nothing to enqueue. Gmail token may still need re-auth."
    echo "   Run: source ~/debate-chamber/.venv/bin/activate && python backend/rex_gmail.py --setup"
    # Still run oversight agent in case there are low-confidence rows from before the break
    echo ""
    echo "   (Continuing to oversight agent to fix any pre-existing low-confidence rows...)"
fi

# ── Step 2: Enqueue all unprocessed PDFs ──────────────────────────────────────
echo ""
echo "── Step 2: Enqueue unprocessed PDFs ───────────────────"
cd "$REX_DIR"

ENQUEUE_SCRIPT=$(cat <<'PYEOF'
import sys
from pathlib import Path

# Add REX dir to path
sys.path.insert(0, str(Path.cwd()))
from CC_ocr_queue import enqueue_scan, get_queue_status

MENUS_DIR = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "menus"

pdfs = sorted(MENUS_DIR.glob("*.pdf"))
enqueued = 0
already_done = 0

for pdf in pdfs:
    job_id = enqueue_scan(str(pdf), mode="hybrid")
    if job_id:
        print(f"  + Enqueued: {pdf.name} (job {job_id})")
        enqueued += 1
    else:
        print(f"  - Already queued/done: {pdf.name}")
        already_done += 1

print(f"\nEnqueue summary: {enqueued} new | {already_done} already done/queued")
print("\nQueue status after enqueue:")
status = get_queue_status()
for state, count in sorted(status.items()):
    print(f"  {state:10s}: {count}")
if not status:
    print("  (empty)")
PYEOF
)

"$VENV" -c "$ENQUEUE_SCRIPT"

# ── Step 3: Run OCR Worker ─────────────────────────────────────────────────────
echo ""
echo "── Step 3: Run OCR Worker (hybrid mode) ───────────────"
"$VENV" "$REX_DIR/CC_ocr_worker.py"
WORKER_EXIT=$?
if [ $WORKER_EXIT -ne 0 ]; then
    echo "⚠️  Worker exited with code $WORKER_EXIT — check log above"
else
    echo "✅ Worker completed"
fi

# ── Step 4: Run Oversight Agent --fix-all ─────────────────────────────────────
echo ""
echo "── Step 4: Oversight Agent (--fix-all) ────────────────"
"$VENV" "$REX_DIR/CC_ocr_oversight_agent.py" --fix-all
OVERSIGHT_EXIT=$?
if [ $OVERSIGHT_EXIT -ne 0 ]; then
    echo "⚠️  Oversight agent exited with code $OVERSIGHT_EXIT — check log above"
else
    echo "✅ Oversight agent completed"
fi

# ── Step 5: Final queue status ─────────────────────────────────────────────────
echo ""
echo "── Step 5: Final Queue Status ─────────────────────────"
"$VENV" "$REX_DIR/CC_ocr_worker.py" --status

echo ""
echo "── Step 6: Confidence Audit ────────────────────────────"
"$VENV" "$REX_DIR/CC_ocr_oversight_agent.py" --audit

echo ""
echo "========================================================"
echo " Backfill complete — $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log saved to: $LOG_FILE"
echo "========================================================"

# Keep Terminal window open (double-click behavior)
echo ""
echo "Press Enter to close..."
read -r
