#!/bin/bash
# CC_install_real_soul.command — Install SOUL.md v6.0 (June 1 2026) + MEMORY.md from BRAIN backups

LOG="$HOME/Desktop/REX/logs/CC_install_real_soul_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== Installing Real SOUL.md v6.0 $(date) ==="

BACKUP_DIR="$HOME/Desktop/Gold_Health_Systems/BRAIN/backups/2026-06-01"
SOUL_SOURCE="$BACKUP_DIR/CC_SOUL_FINAL_SHORT.md"
MEMORY_SOURCE="$BACKUP_DIR/CC_MEMORY_FINAL.md"
MEM_DIR="$HOME/.hermes/profiles/cloud/memories"
SOUL_DEST="$MEM_DIR/SOUL.md"
MEMORY_DEST="$MEM_DIR/MEMORY.md"

mkdir -p "$MEM_DIR"
chflags nouchg "$SOUL_DEST" "$MEMORY_DEST" 2>/dev/null

echo ""
echo "[1] Installing SOUL.md v6.0..."
cp "$SOUL_SOURCE" "$SOUL_DEST"
echo "  ✓ SOUL.md installed ($(wc -c < "$SOUL_DEST") bytes)"

echo ""
echo "[2] Installing MEMORY.md (June 1 base + June 5 note appended)..."
cp "$MEMORY_SOURCE" "$MEMORY_DEST"

# Append today's important context
cat >> "$MEMORY_DEST" << 'MEM'
§
JUNE 5 NOTE
Hermes cloud profile config.yaml was wiped by hermes setup run on June 5.
Fixed: deepseek/deepseek-v4-pro routing now hardcoded in config.yaml.
Previous issue: Nous Research was intercepting DeepSeek calls (wrong provider routing).
SOUL.md was missing — reinstalled v6.0 from BRAIN/backups/2026-06-01.
hermes_critical_backup (157MB) at ~/Desktop/hermes_critical_backup/ — full pre-reinstall snapshot.
MEM
echo "  ✓ MEMORY.md installed with June 5 note"

echo ""
echo "[3] Locking both files..."
chflags uchg "$SOUL_DEST" "$MEMORY_DEST"
echo "  ✓ Locked"

echo ""
echo "[4] Verifying SOUL.md:"
cat "$SOUL_DEST"

echo ""
echo "[5] Restarting gateway..."
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist 2>/dev/null
pkill -f "hermes_cli.main.*gateway" 2>/dev/null
sleep 8
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
echo "  ✓ Gateway restarted"

echo ""
echo "=== Done $(date) ==="
echo "Test: send 'what is my name?' to @Hermes_Cloud_May_bot"
echo ""
echo "Press any key to close..."
read -n 1
