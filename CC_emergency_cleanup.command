#!/usr/bin/env bash
# CC_emergency_cleanup.command
# Stops the signin improve loop and purges contaminated attendance records.
# Double-click to run.

set -euo pipefail
LOG="$HOME/Desktop/REX/logs/CC_emergency_cleanup_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$LOG") 2>&1

DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
PLIST="$HOME/Library/LaunchAgents/com.ghs.signin.improve.loop.plist"

echo "=== CC_emergency_cleanup ==="
echo "$(date)"
echo ""

# ── Step 1: Stop the improve loop ─────────────────────────────────────────────
echo "Step 1 — Stopping signin improve loop..."
if launchctl list | grep -q "ghs.signin.improve.loop"; then
    launchctl unload "$PLIST" 2>/dev/null && echo "  ✅ plist unloaded" || echo "  ⚠️  unload failed (already stopped?)"
else
    echo "  ℹ️  plist not currently loaded"
fi
pkill -f "CC_signin_improve_loop" 2>/dev/null && echo "  ✅ process killed" || echo "  ℹ️  no process running"
echo ""

# ── Step 2: Purge contaminated records from today ─────────────────────────────
echo "Step 2 — Purging contaminated client_signatures for 2026-06-25..."
DELETED=$(sqlite3 "$DB" "
BEGIN;
DELETE FROM client_signatures
WHERE date = '2026-06-25'
  AND source_pdf IN (
    '800_doc00474320260601105724.pdf',
    '808_doc00502620260608110603.pdf',
    '809_doc00502820260608110647.pdf',
    '810_doc00503020260608110731.pdf',
    '811_doc00503020260608110731.pdf'
  );
SELECT changes();
COMMIT;
")
echo "  ✅ Rows deleted: $DELETED"
echo ""

# Also purge contaminated attendance_log entries from the improve loop
echo "Step 2b — Purging contaminated attendance_log entries..."
DELETED_ATT=$(sqlite3 "$DB" "
BEGIN;
DELETE FROM attendance_log
WHERE log_date = '2026-06-25'
  AND source = 'ocr_signin_match'
  AND note LIKE '%source=ocr_signin_match%';
SELECT changes();
COMMIT;
" 2>/dev/null || echo "0")
echo "  ✅ attendance_log rows deleted: $DELETED_ATT"
echo ""

# ── Step 3: Verify what remains ───────────────────────────────────────────────
echo "Step 3 — Verifying today's clean data..."
REMAINING=$(sqlite3 "$DB" "SELECT count(*) FROM client_signatures WHERE date='2026-06-25';")
echo "  client_signatures for 2026-06-25: $REMAINING rows"

DRIVE_COUNT=$(sqlite3 "$DB" "SELECT count(*) FROM client_signatures WHERE date='2026-06-25' AND source_pdf IS NULL OR (date='2026-06-25' AND source_type='drive_sync');" 2>/dev/null || echo "N/A")
echo "  Drive sync rows: $DRIVE_COUNT"

echo ""
echo "=== Done ==="
echo "Log saved to: $LOG"
echo ""
echo "Press any key to close..."
read -n 1 -s
