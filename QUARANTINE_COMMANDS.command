#!/bin/bash
# ====================================================================
#  QUARANTINE DUPLICATE COMMANDS
#  Moves superseded/duplicate .command files to a sealed quarantine.
#  Files are NOT deleted — they are sealed with chmod 000 (no access).
#  To restore any file: mv it out of quarantine, chmod +x it.
#
#  Run once from ~/Desktop/REX/
# ====================================================================
set -uo pipefail
REX="$HOME/Desktop/REX"
QDIR="$REX/QUARANTINE_COMMANDS_2026_04_14"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Quarantine Duplicate Commands                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Create quarantine with open permissions first so we can write into it
mkdir -p "$QDIR"
cat > "$QDIR/README.md" << 'DOC'
# Quarantined Command Files — 2026-04-14

These files were moved here because they are:
- Superseded by a newer, more complete version
- One-time scripts that have already been executed
- Duplicates of an active command with a different name

## To restore a file:
1. Move it OUT of this directory: `mv FILENAME.command ~/Desktop/REX/`
2. Re-enable execution: `chmod +x ~/Desktop/REX/FILENAME.command`
3. Log the restoration in ledger.db

## Active replacements:
| Quarantined | Replaced by |
|---|---|
| RUN_OCR.command | RUN_MENU_VISION_INBOX.command |
| RUN_MENU_EXTRACT.command | RUN_MENU_VISION_INBOX.command |
| RUN_FULL_SCAN.command | RUN_MENU_VISION_INBOX.command |
| RUN_INGEST_MISSING.command | DOWNLOAD_ALL_SCANS.command |
| diag_menus.command | TEST_OCR.command |
| RUN_SIGNIN_INTAKE.command | LOG_ATTENDANCE_TODAY.command |
| run_read_sign_in.command | LOG_ATTENDANCE_TODAY.command |
| start_rexxie_only.command | FIX_REXXIE.command (single bot) |
| fix_rexxie_launchd.command | FIX_REXXIE.command |
| fix_telegram_conflict.command | FIX_REXXIE.command |
| restart-backend.command | START_API_SERVER.command |
| check_rexxie.command | REX_HEALTH_CHECK.command |
| INSTALL_PDFPLUMBER.command | install_ocr_deps.command |
| install-all-agents.command | install_ocr_deps.command |
| setup-google-auth.command | SETUP_GMAIL.command |
| teach_rex.command | teach_system_knowledge.command |
| teach_rexxie.command | teach_system_knowledge.command |
| rex-backup-goj.command | rex-backup.command |
| INSTALL_BEGIN.command | (first-run only — already completed) |
| fix-paperless-autostart.command | (one-time — already applied) |
| SEND_MON_HANDOFF_NOW.command | (event script — already sent) |
| SEND_SIGNIN_DRIVER_NOW.command | (event script — already sent) |
| REINSTATE_CLIENT_DATA.command | (one-time restore — already done) |
| RESTORE_ENV.command | (one-time restore — already done) |
| fix_schedule_changes_schema.command | (one-time migration — already done) |
| download_menu_pdfs.command | DOWNLOAD_ALL_SCANS.command |
| paperless_sync.command | (superseded by direct Paperless API) |
| paperless_bulk_upload.command | (superseded by direct Paperless API) |
| get_paperless_token.command | (one-time setup — token already obtained) |
| RUN_REAUTH.command | SETUP_GMAIL.command |
| AGENT.command | (old launcher — replaced by FIX_REXXIE) |
DOC

echo "Moving superseded OCR commands..."
for f in \
  RUN_OCR.command \
  RUN_MENU_EXTRACT.command \
  RUN_FULL_SCAN.command \
  RUN_INGEST_MISSING.command \
  diag_menus.command; do
  [ -f "$REX/$f" ] && mv "$REX/$f" "$QDIR/" && echo "  ✓ $f" || echo "  - $f (not found)"
done

echo "Moving superseded sign-in commands..."
for f in \
  RUN_SIGNIN_INTAKE.command \
  run_read_sign_in.command; do
  [ -f "$REX/$f" ] && mv "$REX/$f" "$QDIR/" && echo "  ✓ $f" || echo "  - $f (not found)"
done

echo "Moving superseded bot/service commands..."
for f in \
  start_rexxie_only.command \
  fix_rexxie_launchd.command \
  fix_telegram_conflict.command \
  restart-backend.command \
  check_rexxie.command; do
  [ -f "$REX/$f" ] && mv "$REX/$f" "$QDIR/" && echo "  ✓ $f" || echo "  - $f (not found)"
done

echo "Moving superseded install/setup commands..."
for f in \
  INSTALL_PDFPLUMBER.command \
  install-all-agents.command \
  setup-google-auth.command \
  fix-paperless-autostart.command \
  INSTALL_BEGIN.command; do
  [ -f "$REX/$f" ] && mv "$REX/$f" "$QDIR/" && echo "  ✓ $f" || echo "  - $f (not found)"
done

echo "Moving superseded teach commands..."
for f in \
  teach_rex.command \
  teach_rexxie.command; do
  [ -f "$REX/$f" ] && mv "$REX/$f" "$QDIR/" && echo "  ✓ $f" || echo "  - $f (not found)"
done

echo "Moving one-time event/backup commands..."
for f in \
  SEND_MON_HANDOFF_NOW.command \
  SEND_SIGNIN_DRIVER_NOW.command \
  REINSTATE_CLIENT_DATA.command \
  RESTORE_ENV.command \
  fix_schedule_changes_schema.command \
  download_menu_pdfs.command \
  paperless_sync.command \
  paperless_bulk_upload.command \
  get_paperless_token.command \
  RUN_REAUTH.command \
  AGENT.command \
  rex-backup-goj.command; do
  [ -f "$REX/$f" ] && mv "$REX/$f" "$QDIR/" && echo "  ✓ $f" || echo "  - $f (not found)"
done

echo ""
echo "Sealing quarantine..."
# chmod 000 on all quarantined .command files — cannot be executed
chmod 000 "$QDIR"/*.command 2>/dev/null && echo "  ✓ Files sealed (chmod 000 — no read/write/execute)"
# chmod 500 on the directory itself — can list contents but cannot write or delete
chmod 500 "$QDIR" && echo "  ✓ Directory sealed (chmod 500)"

echo ""
MOVED=$(ls "$QDIR"/*.command 2>/dev/null | wc -l)
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Done. $MOVED commands quarantined and sealed.             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Quarantine:  $QDIR"
echo "  Permissions: directory=500, files=000"
echo "  To restore:  move file out, chmod +x it, log in ledger.db"
echo ""
echo "  Active commands remaining in ~/Desktop/REX/:"
ls "$REX"/*.command 2>/dev/null | grep -v "QUARANTINE" | while read f; do
  echo "    $(basename $f)"
done

read -n 1 -p "Press any key to close..."
