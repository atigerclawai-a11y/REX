#!/bin/bash
# CC_backup_to_external.command
# Copy today's GHS governing documents to external drive (/Volumes/cartoons/)

TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
DATE=$(date +"%Y-%m-%d")
LOG=~/Desktop/REX/logs/cc_backup_to_external_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

EXTERNAL="/Volumes/cartoons"
BACKUP_DEST="$EXTERNAL/GHS_BRAIN_BACKUPS/$DATE"
BRAIN_SRC=~/Desktop/Gold_Health_Systems/BRAIN
REX_SRC=~/Desktop/REX

echo "══════════════════════════════════════════════════════"
echo "  CC_backup_to_external — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: Verify external drive is mounted ──────────────────
echo "── 1: External drive ────────────────────────────────"
if [ ! -d "$EXTERNAL" ]; then
  echo "  ❌ External drive not found at $EXTERNAL"
  echo "  Make sure the drive is connected and mounted."
  read -p "Press any key to close..."
  exit 1
fi
echo "  ✅ External drive mounted: $EXTERNAL"
AVAIL=$(df -h "$EXTERNAL" | tail -1 | awk '{print $4}')
echo "  Available space: $AVAIL"
echo ""

# ── 2: Create backup destination ─────────────────────────
echo "── 2: Creating backup directory ─────────────────────"
mkdir -p "$BACKUP_DEST"
echo "  ✅ $BACKUP_DEST"
echo ""

# ── 3: Copy BRAIN files ───────────────────────────────────
echo "── 3: Copying BRAIN/ ────────────────────────────────"
cp -R "$BRAIN_SRC" "$BACKUP_DEST/"
echo "  ✅ BRAIN/ → $(du -sh "$BACKUP_DEST/BRAIN" | cut -f1)"
echo ""

# ── 4: Copy key REX governing files ──────────────────────
echo "── 4: Copying key REX files ─────────────────────────"
mkdir -p "$BACKUP_DEST/REX_GOVERNING"
FILES=(
  "$REX_SRC/CLAUDE.md"
  "$REX_SRC/CC_SOUL_FINAL_SHORT.md"
  "$REX_SRC/CC_MEMORY_FINAL.md"
  "$REX_SRC/CC_HERMES_KNOWLEDGE.md"
  "$REX_SRC/CC_install_soul_memory.command"
  "$REX_SRC/CC_switch_to_mistral.command"
  "$REX_SRC/CC_fix_hermie_v2.command"
  "$REX_SRC/master_list.json"
)
for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    cp "$f" "$BACKUP_DEST/REX_GOVERNING/"
    echo "  ✅ $(basename "$f")"
  else
    echo "  ⚠️  Not found: $(basename "$f")"
  fi
done
echo ""

# ── 5: Verify backup ──────────────────────────────────────
echo "── 5: Backup contents ───────────────────────────────"
find "$BACKUP_DEST" -type f | sort | while read f; do
  echo "  $(du -sh "$f" | cut -f1)  ${f#$BACKUP_DEST/}"
done
TOTAL=$(du -sh "$BACKUP_DEST" | cut -f1)
echo ""
echo "  Total: $TOTAL"
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  Backup location: $BACKUP_DEST"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
