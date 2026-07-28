#!/bin/bash
# CC_install_hermes_dreaming.command
# Install hermes-dreaming — Hermes staged self-improvement plugin
# Does NOT touch SOUL.md or MEMORY.md

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_install_hermes_dreaming_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_install_hermes_dreaming — $(date)"
echo "  SOUL.md + MEMORY.md: UNTOUCHED"
echo "══════════════════════════════════════════════════════"
echo ""

echo "── 1: Install hermes-dreaming ───────────────────────"
hermes plugins install asimons81/hermes-dreaming --enable 2>&1
RC=$?
echo ""

if [ $RC -eq 0 ]; then
  echo "  ✅ hermes-dreaming installed and enabled"
else
  echo "  ⚠️  Exit $RC — verifying..."
  hermes plugins list 2>/dev/null | grep -i dream && echo "  ✅ Already installed" || echo "  ❌ Check log above"
fi
echo ""

echo "── 2: Plugin list ───────────────────────────────────"
hermes plugins list 2>&1 | head -20
echo ""

echo "── 3: Restart cloud gateway ─────────────────────────"
PLIST=~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
launchctl unload "$PLIST" 2>/dev/null || true
pkill -f "hermes_cli.main.*cloud" 2>/dev/null || true
sleep 8
launchctl load "$PLIST"
echo "  Waiting 15s for gateway init..."
sleep 15
GW_PID=$(pgrep -f "hermes_cli.main.*cloud" | head -1)
[ -n "$GW_PID" ] && echo "  ✅ Gateway up: PID $GW_PID" || echo "  ❌ Gateway not running"
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  hermes-dreaming: staged self-improvement active"
echo "  SOUL.md + MEMORY.md: UNTOUCHED"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
