#!/bin/bash
# CC_jarvis_startup.command
# Phase 19 — Jarvis HUD Activation Script
# PAE-5 required before running this in production
#
# This script:
#   1. Confirms TigerClaw :27226 is up
#   2. Finds any Jarvis-related plist in ~/Library/LaunchAgents
#   3. Reports what it found (does NOT load plist without confirmation)
#   4. Provides exact load command for Kato to run after PAE-5 approval

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_jarvis_startup_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_jarvis_startup — Phase 19 Jarvis HUD"
echo "  $(date)"
echo "  PAE-5 required before activating production"
echo "══════════════════════════════════════════════════════"
echo ""

# ── Step 1: Check TigerClaw API ───────────────────────────
echo "── Step 1: TigerClaw API at :27226 ──────────────────"
TC_RESPONSE=$(curl -s --connect-timeout 3 http://localhost:27226/health 2>&1)
TC_STATUS=$?
if [ $TC_STATUS -eq 0 ] && [ -n "$TC_RESPONSE" ]; then
  echo "  ✅ TigerClaw :27226 RESPONDING"
  echo "  Response: $TC_RESPONSE"
else
  echo "  ❌ TigerClaw :27226 NOT RESPONDING"
  echo "  Curl exit code: $TC_STATUS"
  echo ""
  echo "  → Look for TigerClaw plist/process:"
  TIGER_PLIST=$(ls ~/Library/LaunchAgents/ 2>/dev/null | grep -iE "tiger" | head -5)
  if [ -n "$TIGER_PLIST" ]; then
    echo "  Found plists: $TIGER_PLIST"
    echo "  Run: launchctl load ~/Library/LaunchAgents/$TIGER_PLIST"
  else
    echo "  No TigerClaw plist found in ~/Library/LaunchAgents/"
    echo "  Check: ps aux | grep -i tiger"
    TIGER_PROC=$(ps aux | grep -i tiger | grep -v grep)
    if [ -n "$TIGER_PROC" ]; then
      echo "  Tiger process(es) found:"
      echo "  $TIGER_PROC"
    fi
  fi
fi
echo ""

# ── Step 2: Find Jarvis plists ────────────────────────────
echo "── Step 2: Searching for Jarvis plists ─────────────"
JARVIS_PLISTS=$(ls ~/Library/LaunchAgents/ 2>/dev/null | grep -iE "jarvis|hud")
JARVIS_DESKTOP=$(find ~/Desktop -name "*.plist" 2>/dev/null | grep -iE "jarvis|hud" | head -5)
JARVIS_REX=$(find ~/Desktop/REX -name "*.plist" 2>/dev/null | grep -iE "jarvis|hud" | head -5)

if [ -n "$JARVIS_PLISTS" ]; then
  echo "  ✅ Found in ~/Library/LaunchAgents/:"
  echo "  $JARVIS_PLISTS"
elif [ -n "$JARVIS_DESKTOP" ]; then
  echo "  Found in Desktop (needs install):"
  echo "  $JARVIS_DESKTOP"
elif [ -n "$JARVIS_REX" ]; then
  echo "  Found in REX dir (needs install):"
  echo "  $JARVIS_REX"
else
  echo "  ❌ No Jarvis plist found"
  echo "  → Phase 19 architecture: reads TigerClaw :27226 for M01-M24 stats"
  echo "  → Check ~/Desktop/REX/frontend/ or ~/Desktop/rex-ios/ for Jarvis source"
  ls ~/Desktop/REX/frontend/ 2>/dev/null | head -10 || echo "  No frontend/ dir"
fi
echo ""

# ── Step 3: Check if Jarvis process running ───────────────
echo "── Step 3: Check Jarvis process ─────────────────────"
JARVIS_PROC=$(ps aux | grep -iE "jarvis|hud" | grep -v grep | head -5)
if [ -n "$JARVIS_PROC" ]; then
  echo "  Process found:"
  echo "  $JARVIS_PROC"
else
  echo "  No Jarvis process currently running"
fi
echo ""

# ── Step 4: ShellCore (Tauri prototype) ──────────────────
echo "── Step 4: ShellCore source check ───────────────────"
SHELLCORE=$(ls ~/Desktop/dashboard/console/src-tauri/ 2>/dev/null | head -5)
if [ -n "$SHELLCORE" ]; then
  echo "  ShellCore Tauri source found at ~/Desktop/dashboard/console/src-tauri/"
  echo "  Files: $SHELLCORE"
else
  echo "  ShellCore not found at expected path"
fi
echo ""

# ── Step 5: Summary and next steps ───────────────────────
echo "══════════════════════════════════════════════════════"
echo "  SUMMARY"
echo "══════════════════════════════════════════════════════"
echo ""
if [ $TC_STATUS -eq 0 ] && [ -n "$JARVIS_PLISTS" ]; then
  echo "  ✅ READY TO ACTIVATE (PAE-5 approval required)"
  echo ""
  echo "  After PAE-5 approval, run:"
  for plist in $JARVIS_PLISTS; do
    echo "    launchctl load ~/Library/LaunchAgents/$plist"
  done
  echo "    sleep 15"
  echo "    # Verify Jarvis HUD at its expected port"
else
  echo "  ⚠️  NOT READY — resolve above issues first:"
  [ $TC_STATUS -ne 0 ] && echo "    - TigerClaw :27226 not responding"
  [ -z "$JARVIS_PLISTS" ] && echo "    - Jarvis plist not found in LaunchAgents"
  echo ""
  echo "  See CC_PAE_PROPOSALS_june4.md §PAE-5 for full activation plan"
fi
echo ""
echo "  Log: $LOG"
echo ""
read -p "Press any key to close..."
