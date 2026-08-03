#!/bin/bash
# CC_daily_backup.sh — Daily ecosystem backup (rolling 14-day)
# Triggered by Hermes cron job
set -e

BACKUP_ROOT="$HOME/Desktop/REX_Backups"
TIMESTAMP=$(date +%Y%m%d_%H%M)
BACKUP_DIR="$BACKUP_ROOT/CC_daily_$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup → $BACKUP_DIR"

# ── 1. Hermes configs ──
mkdir -p "$BACKUP_DIR/hermes_config" "$BACKUP_DIR/hermes_cloud_profile"
rsync -a "$HOME/.hermes/config.yaml" "$HOME/.hermes/.env" "$BACKUP_DIR/hermes_config/" 2>/dev/null || true
rsync -a "$HOME/.hermes/profiles/cloud/" --exclude='logs/' --exclude='*.log' --exclude='state.db*' "$BACKUP_DIR/hermes_cloud_profile/" 2>/dev/null || true

# ── 2. Hub server ──
mkdir -p "$BACKUP_DIR/hub"
rsync -a "$HOME/hermes-hub/server.py" "$HOME/hermes-hub/pin.json" "$HOME/hermes-hub/auth.json" "$BACKUP_DIR/hub/" 2>/dev/null || true

# ── 3. Vault ──
mkdir -p "$BACKUP_DIR/rexxie_vault"
rsync -a "$HOME/.hermes/rexxie_vault/" "$BACKUP_DIR/rexxie_vault/" 2>/dev/null || true

# ── 4. REX scripts ──
mkdir -p "$BACKUP_DIR/REX_toplevel"
rsync -a --max-size=50M \
  --include='*.py' --include='*.command' --include='*.md' --include='*.json' \
  --exclude='*' \
  "$HOME/Desktop/REX/" "$BACKUP_DIR/REX_toplevel/" 2>/dev/null || true

# ── 4b. REX scripts/ subdir — CRITICAL (was excluded → unrecoverable wipe 2026-08-03).
# Kato 2026-08-03: scripts/ must ALWAYS be in the daily snapshot.
mkdir -p "$BACKUP_DIR/REX_scripts"
rsync -a --max-size=50M \
  --include='*.py' --include='*.json' --exclude='__pycache__' --exclude='*' \
  "$HOME/Desktop/REX/scripts/" "$BACKUP_DIR/REX_scripts/" 2>/dev/null || true

# ── 4c. GOJ Databases — CRITICAL (Kato 2026-08-03: DBs were never backed up. Last DB backup Jun 8.)
mkdir -p "$BACKUP_DIR/GOJ_databases"
for DB in \
  "$HOME/Documents/goj files/dashboard/auth_tracker.db" \
  "$HOME/Documents/goj files/proprietary/goj_proprietary.db" \
  "$HOME/Documents/goj files/dashboard/ghs_schedule.db"; do
  if [ -f "$DB" ]; then
    cp "$DB" "$BACKUP_DIR/GOJ_databases/$(basename "$DB")" 2>/dev/null || true
  fi
done

# ── 5. Notebook ──
mkdir -p "$BACKUP_DIR/notebook"
rsync -a "$HOME/.hermes/notebook/" "$BACKUP_DIR/notebook/" 2>/dev/null || true

# ── 6. Cron jobs ──
mkdir -p "$BACKUP_DIR/cron"
rsync -a "$HOME/.hermes/cron/jobs.json" "$BACKUP_DIR/cron/" 2>/dev/null || true

# ── 7. Master reference ──
cp "$HOME/Desktop/REX/CC_HUB_MASTER_REFERENCE.md" "$BACKUP_DIR/" 2>/dev/null || true

# ── Size ──
SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "[$(date)] Done — $SIZE → $BACKUP_DIR"

# ── Prune: keep last 14 daily backups ──
cd "$BACKUP_ROOT"
ls -dt CC_daily_* 2>/dev/null | tail -n +15 | while read old; do
    echo "[$(date)] Pruning old backup: $old"
    rm -rf "$BACKUP_ROOT/$old"
done

echo "[$(date)] Pruning complete. Active backups: $(ls -d CC_daily_* 2>/dev/null | wc -l)"
