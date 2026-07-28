#!/usr/bin/env bash
# CC_state_db_pruner.sh — Hermes state.db message history pruner
# ---------------------------------------------------------------
# Deletes messages older than RETENTION_DAYS from CLOSED sessions.
# FTS index tables (messages_fts, messages_fts_trigram) are cleaned
# automatically via database triggers on DELETE — no manual rebuild needed.
# Runs VACUUM after pruning to reclaim disk space.
#
# Scheduled: Sunday 03:00 via com.hermes.state-db-pruner.plist
# Logs to:   ~/Desktop/REX/logs/state_db_pruner.log
# ---------------------------------------------------------------

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
RETENTION_DAYS=14          # Delete messages older than this many days
                           # (from closed sessions only — open sessions untouched)
                           # NOTE: bump to 30 once the DB has 30+ days of history

LOG_DIR="$HOME/Desktop/REX/logs"
LOG_FILE="$LOG_DIR/state_db_pruner.log"

# Databases to prune — add/remove paths as needed
# DO NOT add rexxie.db here
DATABASES=(
  "$HOME/.hermes/profiles/cloud/state.db"
  "$HOME/.hermes/profiles/work/state.db"
)
# ── End Configuration ──────────────────────────────────────────

mkdir -p "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

hr() {
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

hr
log "Hermes state.db pruner started (retention=${RETENTION_DAYS}d)"
hr

TOTAL_SAVED_MB=0
TOTAL_ROWS_DELETED=0

for DB in "${DATABASES[@]}"; do
  if [[ ! -f "$DB" ]]; then
    log "SKIP: $DB not found"
    continue
  fi

  log ""
  log "Processing: $DB"

  # ── Before metrics ───────────────────────────────────────────
  SIZE_BEFORE_HUMAN=$(du -sh "$DB" | cut -f1)
  BYTES_BEFORE=$(du -sk "$DB" | awk '{print $1}')   # kilobytes
  MB_BEFORE=$(( BYTES_BEFORE / 1024 ))

  TOTAL_MSGS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM messages;")
  TOTAL_SESSIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sessions;")
  OPEN_SESSIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL;")

  log "  Size before  : $SIZE_BEFORE_HUMAN"
  log "  Messages     : $TOTAL_MSGS total"
  log "  Sessions     : $TOTAL_SESSIONS total ($OPEN_SESSIONS open — will NOT be touched)"

  # ── Compute cutoff (Unix epoch seconds) ──────────────────────
  CUTOFF=$(( $(date +%s) - RETENTION_DAYS * 86400 ))
  CUTOFF_DATE=$(date -r "$CUTOFF" '+%Y-%m-%d %H:%M:%S' 2>/dev/null \
    || date -d "@$CUTOFF" '+%Y-%m-%d %H:%M:%S' 2>/dev/null \
    || echo "timestamp < $CUTOFF")

  # ── Count rows to be deleted (dry-run count) ─────────────────
  ROWS_TO_DELETE=$(sqlite3 "$DB" "
    SELECT COUNT(*) FROM messages
    WHERE timestamp < $CUTOFF
    AND session_id IN (
      SELECT id FROM sessions WHERE ended_at IS NOT NULL
    );
  ")

  log "  Cutoff date  : $CUTOFF_DATE"
  log "  Rows to prune: $ROWS_TO_DELETE messages from closed sessions"

  # ── Delete ───────────────────────────────────────────────────
  if [[ "$ROWS_TO_DELETE" -eq 0 ]]; then
    log "  Nothing to prune — skipping DELETE step"
  else
    log "  Deleting $ROWS_TO_DELETE messages (FTS cleaned by triggers)..."
    sqlite3 "$DB" "
      PRAGMA journal_mode=WAL; -- quiet
      DELETE FROM messages
      WHERE timestamp < $CUTOFF
      AND session_id IN (
        SELECT id FROM sessions WHERE ended_at IS NOT NULL
      );
    "
    log "  Delete complete"
    TOTAL_ROWS_DELETED=$(( TOTAL_ROWS_DELETED + ROWS_TO_DELETE ))
  fi

  # ── VACUUM ───────────────────────────────────────────────────
  log "  Running VACUUM (reclaiming freed pages)..."
  sqlite3 "$DB" "VACUUM;"
  log "  VACUUM complete"

  # ── After metrics ────────────────────────────────────────────
  SIZE_AFTER_HUMAN=$(du -sh "$DB" | cut -f1)
  BYTES_AFTER=$(du -sk "$DB" | awk '{print $1}')
  MB_AFTER=$(( BYTES_AFTER / 1024 ))
  SAVED_MB=$(( MB_BEFORE - MB_AFTER ))

  log "  Size after   : $SIZE_AFTER_HUMAN"
  log "  Space saved  : ~${SAVED_MB} MB"
  TOTAL_SAVED_MB=$(( TOTAL_SAVED_MB + SAVED_MB ))
done

log ""
hr
log "Summary: rows deleted=$TOTAL_ROWS_DELETED | space reclaimed=~${TOTAL_SAVED_MB} MB"
log "Pruner finished"
hr
