#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  REX — GOJ Operational Backup
#  Backs up GOJ-specific data to ~/Desktop/REX/GOJ_Backups/GOJ_YYYY-MM-DD_HH-MM/
#  Keeps 30 days of backups. Safe to run manually or via scheduled task.
#  FIRST TIME: Right-click → Open (to allow macOS to run it)
#
#  Sections:
#    [1/5] Telegram config & channel cache
#    [2/5] Authorization document uploads
#    [3/5] Gmail config & cached scan results
#    [4/5] Google Drive sync manifest
#    [5/5] Prompt Registry (governed system assets)
# ─────────────────────────────────────────────────────────────────────

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

REX_SRC="$HOME/Desktop/REX"
# Resolve to the real physical path so the MANIFEST records true paths even
# when run by a scheduler with a sandboxed HOME (e.g. HOME=/tmp/rexhome).
[ -d "$REX_SRC" ] && REX_SRC="$(cd "$REX_SRC" && pwd -P)"
BACKUP_ROOT="$REX_SRC/GOJ_Backups"
STAMP=$(date '+%Y-%m-%d_%H-%M')
DEST="$BACKUP_ROOT/GOJ_$STAMP"
KEEP_DAYS=30

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   🗂️  REX GOJ Operational Backup${NC}"
echo -e "${BLUE}   $(date '+%A, %B %d %Y  %H:%M')${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Sanity check ───────────────────────────────────────────────────────
if [ ! -d "$REX_SRC" ]; then
  echo -e "${RED}✗ REX source not found at $REX_SRC${NC}"
  echo "Press Enter to close..."; read; exit 1
fi

mkdir -p "$DEST/telegram" "$DEST/gmail" "$DEST/uploads" "$DEST/drive" "$DEST/prompt_registry"

ERRORS=0

# ── [1/5] Telegram channel cache & config ─────────────────────────────
echo -e "${YELLOW}[1/5]${NC} Telegram config & channel cache"

for f in \
  "$HOME/.telegram_channel_cache.json" \
  "$REX_SRC/rex_telegram_config.json" \
  "$REX_SRC/rex_rexxie_telegram_config.json"; do
  if [ -f "$f" ]; then
    cp "$f" "$DEST/telegram/"
    echo -e "  ${GREEN}✓${NC} $(basename "$f")"
  else
    echo -e "  ${YELLOW}–${NC} $(basename "$f") (not found, skipping)"
  fi
done

# ── [2/5] Authorization document uploads ──────────────────────────────
echo -e "\n${YELLOW}[2/5]${NC} Authorization document uploads"

UPLOADS_SRC="$REX_SRC/uploads"
if [ -d "$UPLOADS_SRC" ]; then
  COUNT=$(find "$UPLOADS_SRC" -maxdepth 1 \( -name "*.pdf" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.docx" -o -name "*.doc" \) | wc -l | tr -d ' ')
  if [ "$COUNT" -gt 0 ]; then
    rsync -a \
      --include="*.pdf" --include="*.jpg" --include="*.jpeg" \
      --include="*.png" --include="*.docx" --include="*.doc" \
      --exclude="*" \
      "$UPLOADS_SRC/" "$DEST/uploads/"
    echo -e "  ${GREEN}✓${NC} $COUNT file(s) copied from uploads/"
  else
    echo -e "  ${YELLOW}–${NC} uploads/ is empty, nothing to copy"
  fi
else
  echo -e "  ${YELLOW}–${NC} uploads/ directory not found, skipping"
fi

# ── [3/5] Gmail label rules & cached scan results ─────────────────────
echo -e "\n${YELLOW}[3/5]${NC} Gmail config & cached scan results"

for f in \
  "$REX_SRC/rex_gmail_auth.py" \
  "$REX_SRC/rex_paperless_config.json" \
  "$REX_SRC/rex_queue_config.json" \
  "$REX_SRC/gmail_token.json" \
  "$REX_SRC/goj_signin_processed.json"; do
  if [ -f "$f" ]; then
    cp "$f" "$DEST/gmail/"
    echo -e "  ${GREEN}✓${NC} $(basename "$f")"
  else
    echo -e "  ${YELLOW}–${NC} $(basename "$f") (not found, skipping)"
  fi
done

# ── [4/5] Google Drive sync manifest ──────────────────────────────────
echo -e "\n${YELLOW}[4/5]${NC} Google Drive sync manifest"

for f in \
  "$REX_SRC/.drive_sync.json" \
  "$REX_SRC/GOJ_Master_Routes.json"; do
  if [ -f "$f" ]; then
    cp "$f" "$DEST/drive/"
    echo -e "  ${GREEN}✓${NC} $(basename "$f")"
  else
    echo -e "  ${YELLOW}–${NC} $(basename "$f") (not found, skipping)"
  fi
done

# ── [5/5] Prompt Registry (governed system assets) ────────────────────
echo -e "\n${YELLOW}[5/5]${NC} Prompt Registry (governed system assets)"

PROMPT_ERRORS=0

# Registry index
if [ -f "$REX_SRC/state/prompt_registry.json" ]; then
  cp "$REX_SRC/state/prompt_registry.json" "$DEST/prompt_registry/"
  echo -e "  ${GREEN}✓${NC} state/prompt_registry.json"
else
  echo -e "  ${RED}✗${NC} state/prompt_registry.json (MISSING — registry index not found)"
  PROMPT_ERRORS=$((PROMPT_ERRORS + 1))
fi

# Audit log
if [ -f "$REX_SRC/state/prompt_audit.log" ]; then
  cp "$REX_SRC/state/prompt_audit.log" "$DEST/prompt_registry/"
  AUDIT_LINES=$(wc -l < "$REX_SRC/state/prompt_audit.log" | tr -d ' ')
  echo -e "  ${GREEN}✓${NC} state/prompt_audit.log ($AUDIT_LINES entries)"
else
  echo -e "  ${YELLOW}–${NC} state/prompt_audit.log (not found, skipping)"
fi

# Pending edits DB
if [ -f "$REX_SRC/data/vaults/prompt_edits.db" ]; then
  cp "$REX_SRC/data/vaults/prompt_edits.db" "$DEST/prompt_registry/"
  echo -e "  ${GREEN}✓${NC} data/vaults/prompt_edits.db"
else
  echo -e "  ${YELLOW}–${NC} data/vaults/prompt_edits.db (not found, skipping)"
fi

# Prompt content files (prompts/ tree — all categories including versions)
if [ -d "$REX_SRC/prompts" ]; then
  rsync -a "$REX_SRC/prompts/" "$DEST/prompt_registry/prompts/"
  PROMPT_FILE_COUNT=$(find "$DEST/prompt_registry/prompts" -type f | wc -l | tr -d ' ')
  PROMPT_VER_COUNT=$(find "$DEST/prompt_registry/prompts/versions" -type f 2>/dev/null | wc -l | tr -d ' ')
  echo -e "  ${GREEN}✓${NC} prompts/ — $PROMPT_FILE_COUNT file(s) ($PROMPT_VER_COUNT version snapshot(s))"
else
  echo -e "  ${RED}✗${NC} prompts/ directory not found"
  PROMPT_ERRORS=$((PROMPT_ERRORS + 1))
fi

# Fail loudly if the registry index or prompts dir was missing — these are critical
if [ $PROMPT_ERRORS -gt 0 ]; then
  echo -e "\n  ${RED}⚠️  $PROMPT_ERRORS critical prompt registry item(s) missing from backup!${NC}"
  echo -e "  ${RED}   Check that the Prompt Registry was initialized correctly.${NC}"
  ERRORS=$((ERRORS + PROMPT_ERRORS))
fi

# ── Write MANIFEST.txt ─────────────────────────────────────────────────
{
  echo "REX GOJ Backup Manifest"
  echo "Generated: $(date)"
  echo "Backup Dir: $DEST"
  echo ""
  echo "Files:"
  find "$DEST" -type f | sort
  echo ""
  echo "Total files: $(find "$DEST" -type f | wc -l | tr -d ' ')"
} > "$DEST/MANIFEST.txt"

echo -e "\n  ${GREEN}✓ MANIFEST.txt written${NC}"

# ── Stamp last-backup timestamp ────────────────────────────────────────
date > "$REX_SRC/.last_goj_backup"

# ── Prune backups older than KEEP_DAYS ────────────────────────────────
echo -e "\n${YELLOW}[+]${NC} Pruning backups older than $KEEP_DAYS days..."

PRUNED=0
while IFS= read -r old; do
  rm -rf "$old"
  echo -e "  Removed: $(basename "$old")"
  PRUNED=$((PRUNED + 1))
done < <(find "$BACKUP_ROOT" -maxdepth 1 -name "GOJ_*" -type d -mtime +$KEEP_DAYS | sort)

if [ $PRUNED -eq 0 ]; then
  echo -e "  ${GREEN}✓ Nothing to prune${NC}"
else
  echo -e "  ${GREEN}✓ Pruned $PRUNED old backup(s)${NC}"
fi

# ── Summary ────────────────────────────────────────────────────────────
TOTAL=$(find "$BACKUP_ROOT" -maxdepth 1 -name "GOJ_*" -type d | wc -l | tr -d ' ')
FILE_COUNT=$(find "$DEST" -type f | wc -l | tr -d ' ')
SIZE=$(du -sh "$DEST" 2>/dev/null | awk '{print $1}')

PROMPT_BACKED=$(find "$DEST/prompt_registry" -type f 2>/dev/null | wc -l | tr -d ' ')

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $ERRORS -eq 0 ]; then
  echo -e "${GREEN}  ✅  GOJ Backup complete!${NC}"
else
  echo -e "${RED}  ⚠️  GOJ Backup complete with $ERRORS error(s)${NC}"
fi
echo -e "${GREEN}  📁  $FILE_COUNT file(s) backed up ($SIZE)${NC}"
echo -e "${GREEN}  📋  $PROMPT_BACKED prompt registry file(s) captured${NC}"
echo -e "${GREEN}  📦  $TOTAL total snapshot(s) in GOJ_Backups/${NC}"
echo -e "${GREEN}  📍  $DEST${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
