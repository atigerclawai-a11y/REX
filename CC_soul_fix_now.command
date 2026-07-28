#!/bin/bash
# CC_soul_fix_now.command — Restore correct SOUL.md from hermes_critical_backup (5673 bytes, Jun 5 09:26)

LOG="$HOME/Desktop/REX/logs/CC_soul_fix_now_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== Soul Fix $(date) ==="

SOURCE="$HOME/Desktop/hermes_critical_backup/SOUL.md"
DEST="$HOME/.hermes/profiles/cloud/memories/SOUL.md"

echo ""
echo "[1] Source file (hermes_critical_backup/SOUL.md):"
ls -la "$SOURCE"
cat "$SOURCE"

echo ""
echo "[2] Installing..."
chflags nouchg "$DEST" 2>/dev/null
cp "$DEST" "${DEST}.wrong.$(date +%H%M%S)" 2>/dev/null
cp "$SOURCE" "$DEST"
chflags uchg "$DEST"
echo "  ✓ Installed and locked"

echo ""
echo "[3] Verifying:"
cat "$DEST"

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
