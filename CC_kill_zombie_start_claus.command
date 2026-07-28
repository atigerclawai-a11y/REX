#!/bin/bash
# CC_kill_zombie_start_claus.command
# 1. Kill zombie com.hermes.rexxie-bot
# 2. Restart com.hermes.claus-watchman

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_kill_zombie_start_claus_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════"
echo "  Kill Zombie + Start Claus — $(date)"
echo "══════════════════════════════════════════════"
echo ""

# ── 1: Kill zombie com.hermes.rexxie-bot ──────────
echo "── 1: Kill zombie com.hermes.rexxie-bot ──────"
PLIST=~/Library/LaunchAgents/com.hermes.rexxie-bot.plist

if launchctl list | grep -q "com.hermes.rexxie-bot"; then
  echo "  Found running — unloading..."
  launchctl unload "$PLIST" 2>/dev/null || true
  sleep 2
  # Force-kill any remaining process
  pkill -f "rexxie-bot" 2>/dev/null && echo "  pkill hit — process killed" || echo "  (no lingering process)"
  
  if launchctl list | grep -q "com.hermes.rexxie-bot"; then
    echo "  ❌ Still showing — may need manual kill"
  else
    echo "  ✅ com.hermes.rexxie-bot killed"
  fi
else
  echo "  Already gone — nothing to kill"
fi
echo ""

# ── 2: Start com.hermes.claus-watchman ────────────
echo "── 2: Start com.hermes.claus-watchman ────────"
CLAUS_PLIST=~/Library/LaunchAgents/com.hermes.claus-watchman.plist

if [ ! -f "$CLAUS_PLIST" ]; then
  echo "  ❌ Plist not found: $CLAUS_PLIST"
else
  # Unload first in case it's in a bad state
  launchctl unload "$CLAUS_PLIST" 2>/dev/null || true
  sleep 1
  launchctl load "$CLAUS_PLIST"
  sleep 3
  
  if launchctl list | grep -q "com.hermes.claus-watchman"; then
    PID=$(launchctl list | grep "com.hermes.claus-watchman" | awk '{print $1}')
    echo "  ✅ Claus Watchman started (PID $PID)"
  else
    echo "  ❌ Claus Watchman did not start — check plist"
  fi
fi
echo ""

echo "══════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
