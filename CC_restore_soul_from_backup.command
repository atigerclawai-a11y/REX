#!/bin/bash
# CC_restore_soul_from_backup.command — Find and restore SOUL.md from nightly backup

LOG="$HOME/Desktop/REX/logs/CC_restore_soul_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== SOUL.md Restore from Backup $(date) ==="

SOUL_DEST="$HOME/.hermes/profiles/cloud/memories/SOUL.md"

echo ""
echo "[1] Searching all backup locations for SOUL.md..."

# Find all SOUL.md files, sorted by modification time (newest first)
echo ""
echo "  All SOUL.md files found:"
find /Volumes/cartoons/ ~/Desktop/hermes_critical_backup/ ~/.hermes/backups/ ~/Desktop/Gold_Health_Systems/ \
  -name "SOUL.md" 2>/dev/null | while read f; do
    echo "  $(ls -la "$f" 2>/dev/null) → $f"
done

echo ""
echo "[2] Most recent SOUL.md backups on cartoons drive:"
find /Volumes/cartoons/ -name "SOUL.md" 2>/dev/null | xargs ls -lt 2>/dev/null | head -10

echo ""
echo "[3] Backup folder structure on cartoons drive:"
ls /Volumes/cartoons/ 2>/dev/null
echo ""
find /Volumes/cartoons/ -maxdepth 3 -name "*.md" 2>/dev/null | grep -i "soul\|hermes\|memory" | head -20

echo ""
echo "[4] Checking hermes_critical_backup:"
find ~/Desktop/hermes_critical_backup/ -name "SOUL.md" 2>/dev/null
ls ~/Desktop/hermes_critical_backup/ 2>/dev/null

echo ""
echo "[5] Checking ~/.hermes/backups/:"
find ~/.hermes/backups/ -name "SOUL.md" 2>/dev/null
ls ~/.hermes/backups/ 2>/dev/null | head -20

echo ""
echo "--- Contents of best candidate SOUL.md files ---"
BEST=$(find /Volumes/cartoons/ ~/Desktop/hermes_critical_backup/ ~/.hermes/backups/ \
  -name "SOUL.md" 2>/dev/null | head -1)

if [ -n "$BEST" ]; then
    echo ""
    echo "Best candidate: $BEST"
    echo "--- Content ---"
    cat "$BEST"
    echo ""
    echo "Restore this file? It will replace current SOUL.md."
    echo "Current SOUL.md will be saved to SOUL.md.pre-restore"
    echo ""
    read -p "Press Y to restore, any other key to skip: " CONFIRM
    if [ "$CONFIRM" = "Y" ] || [ "$CONFIRM" = "y" ]; then
        chflags nouchg "$SOUL_DEST" 2>/dev/null
        cp "$SOUL_DEST" "${SOUL_DEST}.pre-restore" 2>/dev/null
        cp "$BEST" "$SOUL_DEST"
        chflags uchg "$SOUL_DEST"
        echo "  ✓ SOUL.md restored from $BEST"
        echo "  ✓ Locked"
        echo ""
        echo "  Restarting gateway..."
        launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist 2>/dev/null
        pkill -f "hermes_cli.main.*gateway" 2>/dev/null
        sleep 8
        launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
        echo "  ✓ Gateway restarted"
    else
        echo "  Skipped restore."
    fi
else
    echo "  No SOUL.md found in backup locations."
fi

echo ""
echo "=== Done $(date) ==="
echo ""
echo "Press any key to close..."
read -n 1
