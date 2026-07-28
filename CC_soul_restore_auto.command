#!/bin/bash
# CC_soul_restore_auto.command — Auto-restore SOUL.md from best available backup, no prompts

LOG="$HOME/Desktop/REX/logs/CC_soul_restore_auto_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== Auto Soul Restore $(date) ==="

SOUL_DEST="$HOME/.hermes/profiles/cloud/memories/SOUL.md"
chflags nouchg "$SOUL_DEST" 2>/dev/null

# Search all backup locations, pick the largest/most recent SOUL.md
# (larger = more content = more likely to be the real hand-crafted one)
echo ""
echo "[1] Scanning all backup locations..."

BEST=""
BEST_SIZE=0

while IFS= read -r f; do
    SIZE=$(wc -c < "$f" 2>/dev/null || echo 0)
    echo "  Found: $f ($SIZE bytes)"
    if [ "$SIZE" -gt "$BEST_SIZE" ]; then
        BEST_SIZE=$SIZE
        BEST="$f"
    fi
done < <(find \
    /Volumes/cartoons/ \
    ~/Desktop/hermes_critical_backup/ \
    ~/.hermes/backups/ \
    ~/.hermes/email-backups/ \
    ~/Desktop/Gold_Health_Systems/ \
    -name "SOUL.md" 2>/dev/null | grep -v "node_modules" | grep -v "/.Trash/")

echo ""
if [ -n "$BEST" ]; then
    echo "[2] Best candidate: $BEST ($BEST_SIZE bytes)"
    echo "--- Content ---"
    cat "$BEST"
    echo ""
    echo "[3] Restoring..."
    cp "$SOUL_DEST" "${SOUL_DEST}.pre-restore.$(date +%H%M%S)" 2>/dev/null
    cp "$BEST" "$SOUL_DEST"
    chflags uchg "$SOUL_DEST"
    echo "  ✓ SOUL.md restored and locked"
else
    echo "[2] No backup found on drive. Keeping current SOUL.md (rebuilt from MASTER.md)."
    echo "    Current SOUL.md:"
    cat "$SOUL_DEST"
fi

echo ""
echo "[4] Restarting gateway..."
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist 2>/dev/null
pkill -f "hermes_cli.main.*gateway" 2>/dev/null
sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
echo "  ✓ Done"

echo ""
echo "=== Done $(date) ==="
echo ""
echo "Press any key to close..."
read -n 1
