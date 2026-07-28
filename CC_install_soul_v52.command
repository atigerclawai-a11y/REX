#!/usr/bin/env bash
# CC_install_soul_v52.command
# Installs SOUL.md v5.2 to Hermes cloud profile and restarts gateway.

SRC="$HOME/Desktop/REX/CC_SOUL_DRAFT_v5.2.md"
DEST="$HOME/.hermes/profiles/cloud/memories/SOUL.md"
LOG="$HOME/Desktop/REX/logs/cc_install_soul_v52_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_install_soul_v52 — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

if [ ! -f "$SRC" ]; then
  echo "ERROR: Draft not found at $SRC"
  sleep 8; exit 1
fi

# Backup existing SOUL.md
if [ -f "$DEST" ]; then
  BAK="${DEST}.bak_$(date +%Y%m%d_%H%M%S)"
  cp "$DEST" "$BAK"
  echo "[BACKUP] $BAK"
  echo "[BEFORE] $(wc -c < "$DEST") bytes"
fi

# Install
cp "$SRC" "$DEST"
echo "[INSTALLED] $DEST"
echo "[AFTER] $(wc -c < "$DEST") bytes"

echo ""
echo "── Gateway restart ──────────────────────────────────"
PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
launchctl unload "$PLIST" 2>/dev/null && echo "  Plist unloaded" || echo "  (wasn't loaded)"
sleep 2
pkill -f "hermes_cli.main.*gateway" 2>/dev/null && echo "  pkill sent" || echo "  (none running)"
sleep 8
launchctl load "$PLIST" && echo "  Plist loaded" || echo "  LOAD FAILED"
sleep 6

echo ""
echo "── LaunchAgent status ───────────────────────────────"
launchctl list | grep "ai.hermes.gateway-cloud" || echo "  (not found)"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  SOUL.md v5.2 installed — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""
echo "Press any key to close..."
read -n 1 -s
