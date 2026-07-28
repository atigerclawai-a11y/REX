#!/bin/bash
# CC_backup_rex_files.command — Backup all CC_ files to a timestamped archive
exec > >(tee "$HOME/Desktop/REX/logs/backup_rex_$(date +%Y%m%d_%H%M%S).log") 2>&1

echo "=== GHS REX FILE BACKUP ==="
echo "Time: $(date)"
echo ""

REX_DIR="$HOME/Desktop/REX"
BACKUP_BASE="$HOME/Desktop/REX/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/REX_backup_$TIMESTAMP"

# 1. Create backup directory
echo "[1/4] Creating backup directory..."
mkdir -p "$BACKUP_DIR"
echo "✅ Backup target: $BACKUP_DIR"

# 2. Copy all CC_ files
echo ""
echo "[2/4] Copying all CC_ files..."
COUNT=0
for f in "$REX_DIR"/CC_*; do
    if [ -f "$f" ]; then
        cp "$f" "$BACKUP_DIR/"
        ((COUNT++))
    elif [ -d "$f" ]; then
        # Copy directories (like CC_nerve_center/)
        cp -r "$f" "$BACKUP_DIR/"
        ((COUNT++))
    fi
done
echo "✅ Copied $COUNT items"

# 3. Copy key config files
echo ""
echo "[3/4] Copying key support files..."
[ -f "$REX_DIR/CC_build_progress.json" ] && cp "$REX_DIR/CC_build_progress.json" "$BACKUP_DIR/"
[ -f "$REX_DIR/master_list.json" ] && cp "$REX_DIR/master_list.json" "$BACKUP_DIR/"
[ -f "$REX_DIR/CLAUDE.md" ] && cp "$REX_DIR/CLAUDE.md" "$BACKUP_DIR/"
echo "✅ Support files copied"

# 4. Create manifest
echo ""
echo "[4/4] Creating manifest..."
MANIFEST="$BACKUP_DIR/MANIFEST.txt"
{
    echo "GHS REX Backup — $TIMESTAMP"
    echo "Source: $REX_DIR"
    echo ""
    echo "Files:"
    ls -la "$BACKUP_DIR/" | grep -v "^total"
} > "$MANIFEST"
echo "✅ Manifest written"

# Summary
echo ""
echo "=== BACKUP COMPLETE ==="
echo "Location: $BACKUP_DIR"
echo "Files: $COUNT"
du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print "Size: " $1}'
echo ""
echo "To restore: cp -r '$BACKUP_DIR/'* '$REX_DIR/'"
echo ""

# Also create a zip for easy emailing
echo "Creating zip archive..."
ZIP_PATH="$BACKUP_BASE/REX_backup_$TIMESTAMP.zip"
cd "$BACKUP_BASE"
zip -rq "REX_backup_$TIMESTAMP.zip" "REX_backup_$TIMESTAMP/" 2>/dev/null
if [ -f "$ZIP_PATH" ]; then
    ZIP_SIZE=$(du -sh "$ZIP_PATH" | awk '{print $1}')
    echo "✅ Zip: $ZIP_PATH ($ZIP_SIZE)"
    echo ""
    echo "To email: attach $ZIP_PATH"
else
    echo "⚠️  zip not available — backup folder is still complete"
fi

echo ""
read -p "Press Enter to close..."
