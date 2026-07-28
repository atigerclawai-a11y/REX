#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  REX — Daily Backup (Cartoons external drive edition)
#  Backs up ~/Desktop/REX to /Volumes/Cartoons/REX_Backups/REX_YYYY-MM-DD_HH-MM/
#  Keeps the 14 most recent snapshots. Safe to run manually or via cron.
#  FIRST TIME: Right-click → Open (to allow macOS to run it)
#
#  Design rules (per operator directive):
#   • Backups live OFF the build tree, on the external Cartoons drive only.
#   • Nothing in REX is ever expected to read from here — every snapshot
#     is stamped with a DO_NOT_USE_AS_SOURCE.txt marker so scanners,
#     indexers, and future-you can't mistake an archive for a source.
#   • If Cartoons isn't mounted, the script hard-fails — NO silent
#     fallback to Desktop. Missed runs are better than quietly
#     re-polluting the Desktop.
# ─────────────────────────────────────────────────────────────────────

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

REX_SRC="$HOME/Desktop/REX"

# ── Locate the Cartoons drive (case variants: Cartoons, cartoons) ─────
CARTOONS_MOUNT=""
for candidate in "/Volumes/Cartoons" "/Volumes/cartoons"; do
  if [ -d "$candidate" ]; then
    CARTOONS_MOUNT="$candidate"
    break
  fi
done

STAMP=$(date '+%Y-%m-%d_%H-%M')
KEEP=14   # snapshots to keep

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   🦖  REX Daily Backup — Cartoons edition${NC}"
echo -e "${BLUE}   $(date '+%A, %B %d %Y  %H:%M')${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Sanity check: REX source must exist ──────────────────────────────
if [ ! -d "$REX_SRC" ]; then
  echo -e "${RED}✗ REX source not found at $REX_SRC${NC}"
  echo "Press Enter to close..."; read; exit 1
fi

# ── Sanity check: Cartoons drive must be mounted ─────────────────────
if [ -z "$CARTOONS_MOUNT" ]; then
  echo -e "${RED}✗ Cartoons external drive is NOT mounted.${NC}"
  echo -e "${RED}   Looked for: /Volumes/Cartoons and /Volumes/cartoons${NC}"
  echo -e "${YELLOW}   Plug in the drive and re-run. No fallback to Desktop — by design.${NC}"
  echo "Press Enter to close..."; read; exit 2
fi

BACKUP_ROOT="$CARTOONS_MOUNT/REX_Backups"
DEST="$BACKUP_ROOT/REX_$STAMP"
mkdir -p "$BACKUP_ROOT"

# Quick write-test on the drive
TEST_FILE="$BACKUP_ROOT/.write_test_$$"
if ! touch "$TEST_FILE" 2>/dev/null; then
  echo -e "${RED}✗ Cartoons drive is mounted at $CARTOONS_MOUNT but not writable.${NC}"
  echo -e "${YELLOW}   Check read/write status or permissions and try again.${NC}"
  echo "Press Enter to close..."; read; exit 3
fi
rm -f "$TEST_FILE"

echo -e "${GREEN}✓ Cartoons mounted at: $CARTOONS_MOUNT${NC}"
echo -e "${GREEN}✓ Snapshot target:     $DEST${NC}\n"

# ── Run rsync backup ──────────────────────────────────────────────────
echo -e "${YELLOW}[1/4]${NC} Backing up REX → $DEST"
echo -e "      (Excluding: node_modules, .venv, __pycache__, *.pyc, dist/, .git/, logs)\n"

rsync -a --progress \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.git/' \
  --exclude='logs/*.log' \
  --exclude='REX_Backups/' \
  "$REX_SRC/" "$DEST/"

RSYNC_EXIT=$?

# ── Also back up REX memory DB (~/.rex/) ──────────────────────────────
if [ -d "$HOME/.rex" ]; then
  echo -e "\n${YELLOW}  [+]${NC} Backing up REX memory (~/.rex → $DEST/.rex_memory/)"
  rsync -a "$HOME/.rex/" "$DEST/.rex_memory/"
  MEM_EXIT=$?
  if [ $MEM_EXIT -eq 0 ]; then
    echo -e "  ${GREEN}✓ REX memory backed up${NC}"
  else
    echo -e "  ${RED}✗ REX memory rsync failed (exit $MEM_EXIT) — continuing${NC}"
  fi
fi

if [ $RSYNC_EXIT -ne 0 ]; then
  echo -e "\n${RED}✗ Backup failed (rsync exit $RSYNC_EXIT)${NC}"
  echo "Press Enter to close..."; read; exit 1
fi

SIZE=$(du -sh "$DEST" 2>/dev/null | awk '{print $1}')
echo -e "\n  ${GREEN}✓ Backup complete — $SIZE saved${NC}"

# ── Drop the "do not pull from here" marker ───────────────────────────
cat > "$DEST/DO_NOT_USE_AS_SOURCE.txt" <<EOF
This directory is an ARCHIVAL SNAPSHOT of ~/Desktop/REX.
Created: $(date '+%Y-%m-%d %H:%M:%S %Z')
Stamp:   $STAMP
Host:    $(hostname)

DO NOT:
  • Read configuration from this folder
  • Import code or data from this folder into a build
  • Point any runtime, script, or indexer at this path
  • Restore partial files by copying from here — always use a full
    snapshot restore with a known procedure

This snapshot is WRITE-ONCE, READ-FOR-RECOVERY-ONLY.
If you find something that references this path as a SOURCE, that's a bug.
EOF
echo -e "  ${GREEN}✓ DO_NOT_USE_AS_SOURCE.txt marker written${NC}"

# ── Prune old backups ─────────────────────────────────────────────────
echo -e "\n${YELLOW}[2/4]${NC} Pruning backups older than $KEEP days..."

PRUNED=0
while IFS= read -r old_backup; do
  rm -rf "$old_backup"
  echo -e "  Removed: $(basename "$old_backup")"
  PRUNED=$((PRUNED + 1))
done < <(find "$BACKUP_ROOT" -maxdepth 1 -name "REX_*" -type d -mtime +$KEEP | sort)

if [ $PRUNED -eq 0 ]; then
  echo -e "  ${GREEN}✓ Nothing to prune${NC}"
else
  echo -e "  ${GREEN}✓ Pruned $PRUNED old backup(s)${NC}"
fi

# ── Verify governed system assets are in snapshot ────────────────────
echo -e "\n${YELLOW}[3/4]${NC} Verifying governed assets in snapshot..."

VERIFY_ERRORS=0

_check() {
  local label="$1"
  local path="$2"
  if [ -e "$DEST/$path" ]; then
    echo -e "  ${GREEN}✓${NC} $label"
  else
    echo -e "  ${RED}✗${NC} $label — NOT FOUND in snapshot (source: $REX_SRC/$path)"
    VERIFY_ERRORS=$((VERIFY_ERRORS + 1))
  fi
}

# Prompt Registry — registry index
_check "state/prompt_registry.json"        "state/prompt_registry.json"

# Prompt Registry — audit log
if [ -f "$REX_SRC/state/prompt_audit.log" ]; then
  _check "state/prompt_audit.log"          "state/prompt_audit.log"
else
  echo -e "  ${YELLOW}–${NC} state/prompt_audit.log (not yet created, skipping)"
fi

# Prompt Registry — content files
if [ -d "$REX_SRC/prompts" ]; then
  PROMPT_COUNT=$(find "$DEST/prompts" -type f 2>/dev/null | wc -l | tr -d ' ')
  VER_COUNT=$(find "$DEST/prompts/versions" -type f 2>/dev/null | wc -l | tr -d ' ')
  if [ "$PROMPT_COUNT" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} prompts/ — $PROMPT_COUNT file(s), $VER_COUNT version snapshot(s)"
  else
    echo -e "  ${RED}✗${NC} prompts/ directory empty or missing in snapshot"
    VERIFY_ERRORS=$((VERIFY_ERRORS + 1))
  fi
else
  echo -e "  ${YELLOW}–${NC} prompts/ not present in source (Prompt Registry not yet initialized)"
fi

# Prompt Registry — pending edits DB
if [ -f "$REX_SRC/data/vaults/prompt_edits.db" ]; then
  _check "data/vaults/prompt_edits.db"     "data/vaults/prompt_edits.db"
else
  echo -e "  ${YELLOW}–${NC} data/vaults/prompt_edits.db (not found, skipping)"
fi

if [ $VERIFY_ERRORS -gt 0 ]; then
  echo -e "\n  ${RED}⚠️  $VERIFY_ERRORS governed asset(s) missing from snapshot!${NC}"
  echo -e "  ${RED}   Investigate before relying on this backup for recovery.${NC}"
else
  echo -e "\n  ${GREEN}✓ All governed assets confirmed in snapshot${NC}"
fi

# ── Backup inventory ─────────────────────────────────────────────────
echo -e "\n${YELLOW}[4/4]${NC} Snapshot inventory on Cartoons:"

TOTAL=$(find "$BACKUP_ROOT" -maxdepth 1 -name "REX_*" -type d | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$BACKUP_ROOT" 2>/dev/null | awk '{print $1}')

find "$BACKUP_ROOT" -maxdepth 1 -name "REX_*" -type d | sort | while read -r d; do
  SZ=$(du -sh "$d" 2>/dev/null | awk '{print $1}')
  echo -e "  📦 $(basename "$d")  [$SZ]"
done

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $VERIFY_ERRORS -eq 0 ]; then
  echo -e "${GREEN}  ✅  Backup done! All governed assets verified.${NC}"
else
  echo -e "${RED}  ⚠️  Backup done — $VERIFY_ERRORS verification warning(s).${NC}"
fi
echo -e "${GREEN}  📁  $TOTAL snapshot(s) stored ($TOTAL_SIZE total)${NC}"
echo -e "${GREEN}  📍  Location: $BACKUP_ROOT${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Write last-backup timestamp for REX health check
# (Kept in REX root so health probes still work — this is a status
#  file, NOT a source of truth for the snapshot content.)
echo "$STAMP" > "$REX_SRC/.last_backup"
