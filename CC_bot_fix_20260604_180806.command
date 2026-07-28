#!/bin/bash
# CC_bot_fix — Targeted Telegram Bot 409 Fix
# Gold Health Systems · Root cause: multiple bot instances polling same token
# Run this ONCE to kill all duplicates and restart cleanly

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG="$HOME/Desktop/REX/logs/CC_bot_fix_${TIMESTAMP}.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   TELEGRAM BOT 409-CONFLICT FIX — $(date +'%Y-%m-%d %H:%M:%S')   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "ROOT CAUSE: HTTP 409 Conflict — multiple bot instances fighting"
echo "           for the same Telegram token simultaneously."
echo ""

# ── STEP 1: Show what's currently running ──────────────────────
echo "=== STEP 1: Current bot processes ==="
echo "Telegram bot processes:"
pgrep -la "rex_telegram_bot\|rex_rexxie_telegram" 2>/dev/null || echo "  (none found)"
echo ""
echo "Hermes gateway processes:"
pgrep -la "hermes_cli\|hermes.*gateway" 2>/dev/null || echo "  (none found)"
echo ""
echo "LaunchAgent status:"
launchctl list 2>/dev/null | grep -E "hermes|rex|goj|rexxie|goldhealth" || echo "  (none)"
echo ""

# ── STEP 2: Kill ALL bot instances ────────────────────────────
echo "=== STEP 2: Kill all conflicting bot processes ==="

echo "  Killing rex_telegram_bot.py instances..."
pkill -9 -f "rex_telegram_bot\.py" 2>/dev/null && echo "  ✅ Killed" || echo "  ℹ️  No rex_telegram_bot.py running"

echo "  Killing rex_rexxie_telegram_bot.py instances..."
pkill -9 -f "rex_rexxie_telegram_bot\.py" 2>/dev/null && echo "  ✅ Killed" || echo "  ℹ️  No rex_rexxie_telegram_bot.py running"

echo "  Killing all Hermes gateway instances..."
pkill -9 -f "hermes_cli.main.*gateway" 2>/dev/null && echo "  ✅ Killed Hermes gateway" || echo "  ℹ️  No Hermes gateway running"
pkill -9 -f "hermes.*gateway" 2>/dev/null || true

echo "  Waiting 5s for Telegram to release sessions..."
sleep 5
echo ""

# ── STEP 3: Check + disable zombie plist ──────────────────────
echo "=== STEP 3: Zombie plist check (com.hermes.rexxie-bot) ==="
ZOMBIE_PLIST="$HOME/Library/LaunchAgents/com.hermes.rexxie-bot.plist"
if [ -f "$ZOMBIE_PLIST" ]; then
  echo "  ⚠️  ZOMBIE PLIST EXISTS: $ZOMBIE_PLIST"
  echo "  Unloading zombie..."
  launchctl unload "$ZOMBIE_PLIST" 2>/dev/null && echo "  ✅ Unloaded zombie" || echo "  ℹ️  Was not loaded"
  echo "  Disabling with launchctl..."
  launchctl disable "gui/$(id -u)/com.hermes.rexxie-bot" 2>/dev/null || true
  echo "  ✅ Zombie suppressed (NOT deleted — keeping per CLAUDE.md)"
else
  echo "  ✅ Zombie plist not found in LaunchAgents — safe"
fi
echo ""

# ── STEP 4: Unload all Hermes + REX plists ────────────────────
echo "=== STEP 4: Unload all gateway/bot plists cleanly ==="
for PLIST in \
  "$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist" \
  "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist" \
  "$HOME/Library/LaunchAgents/com.rex.backend.plist"; do
  if [ -f "$PLIST" ]; then
    NAME=$(basename "$PLIST")
    launchctl unload "$PLIST" 2>/dev/null && echo "  ✅ Unloaded $NAME" || echo "  ℹ️  $NAME was not loaded"
  fi
done
sleep 3
echo ""

# ── STEP 5: Kill any lingering bot processes ──────────────────
echo "=== STEP 5: Final kill sweep ==="
pkill -9 -f "rex_telegram_bot\.py" 2>/dev/null || true
pkill -9 -f "rex_rexxie_telegram_bot\.py" 2>/dev/null || true
pkill -9 -f "hermes_cli\.main" 2>/dev/null || true
echo "  Done. Waiting 8s for Telegram session expiry..."
sleep 8
echo ""

# ── STEP 6: Restart Hermes Cloud Gateway ──────────────────────
echo "=== STEP 6: Restart Hermes Cloud Gateway (port 3002) ==="
HERMES_CLOUD="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
if [ -f "$HERMES_CLOUD" ]; then
  launchctl load "$HERMES_CLOUD"
  echo "  Loaded. Waiting 12s for Telegram connection..."
  sleep 12
  HEALTH=$(curl -s --max-time 5 "http://localhost:3002/health" 2>/dev/null || echo "UNREACHABLE")
  echo "  Health (port 3002): $HEALTH"
  if echo "$HEALTH" | grep -q "UNREACHABLE"; then
    echo "  ⚠️  Gateway not responding yet — checking log..."
    tail -20 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null | grep -E "ERROR|WARNING|Telegram|started|conflict" | tail -10
  else
    echo "  ✅ Hermes Cloud Gateway UP"
  fi
else
  echo "  ❌ Plist not found: $HERMES_CLOUD"
fi
echo ""

# ── STEP 7: Restart REX Backend ───────────────────────────────
echo "=== STEP 7: Restart REX Backend (port 8000) ==="
REX_PLIST="$HOME/Library/LaunchAgents/com.rex.backend.plist"
if [ -f "$REX_PLIST" ]; then
  launchctl load "$REX_PLIST"
  echo "  Loaded. Waiting 8s..."
  sleep 8
  REX_HEALTH=$(curl -s --max-time 5 "http://localhost:8000/health" 2>/dev/null || echo "UNREACHABLE")
  echo "  Health (port 8000): $REX_HEALTH"
  if echo "$REX_HEALTH" | grep -q '"status"'; then
    echo "  ✅ REX Backend UP"
  else
    echo "  ⚠️  REX not responding yet"
  fi
else
  echo "  ❌ Plist not found: $REX_PLIST"
fi
echo ""

# ── STEP 8: Check for bot processes started by REX backend ────
echo "=== STEP 8: Post-restart bot process check ==="
sleep 5
echo "Telegram bot processes:"
pgrep -la "rex_telegram_bot\|rex_rexxie_telegram" 2>/dev/null || echo "  (none — may be started on demand)"
echo ""
echo "Hermes processes:"
pgrep -la "hermes_cli\|hermes.*gateway" 2>/dev/null || echo "  (none)"
echo ""

# ── STEP 9: Test Telegram API with both bot tokens ─────────────
echo "=== STEP 9: Live Telegram API test ==="

REX_CFG="$HOME/Desktop/REX/rex_telegram_config.json"
REXXIE_CFG="$HOME/Desktop/REX/rex_rexxie_telegram_config.json"

test_token() {
  local NAME="$1"
  local TOKEN="$2"
  local RESULT=$(curl -s --max-time 8 "https://api.telegram.org/bot${TOKEN}/getMe" 2>/dev/null)
  if echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ VALID —', d['result']['username'])" 2>/dev/null; then
    : # printed inline
  elif echo "$RESULT" | grep -q '"ok":false'; then
    ERROR=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','unknown'))" 2>/dev/null)
    echo "  ❌ $NAME token INVALID: $ERROR"
  else
    echo "  ⚠️  $NAME no response from Telegram"
  fi
}

if [ -f "$REX_CFG" ]; then
  REX_TOKEN=$(python3 -c "import json; print(json.load(open('$REX_CFG'))['bot_token'])" 2>/dev/null)
  printf "  REX Telegram Bot (@RexOfGold_bot): "
  test_token "REX" "$REX_TOKEN"
fi

if [ -f "$REXXIE_CFG" ]; then
  REXXIE_TOKEN=$(python3 -c "import json; print(json.load(open('$REXXIE_CFG'))['bot_token'])" 2>/dev/null)
  printf "  Rexxie Bot (@goldhealth_rexxie_bot): "
  test_token "Rexxie" "$REXXIE_TOKEN"
fi
echo ""

# ── STEP 10: Final status ─────────────────────────────────────
echo "=== STEP 10: FINAL SYSTEM STATUS ==="
echo ""
echo "Services:"
for PORT_INFO in "3002:Hermes Cloud GW (@Hermes_Cloud_May_bot)" "8000:REX Backend" "8080:GOJ Dashboard"; do
  PORT="${PORT_INFO%%:*}"
  NAME="${PORT_INFO#*:}"
  RESULT=$(curl -s --max-time 3 "http://localhost:${PORT}/health" 2>/dev/null)
  if [ -n "$RESULT" ]; then
    echo "  ✅ ${NAME} (port ${PORT}): UP"
  else
    echo "  ❌ ${NAME} (port ${PORT}): DOWN"
  fi
done
echo ""
echo "LaunchAgent status:"
launchctl list 2>/dev/null | grep -E "hermes|rex\.backend|goj|rexxie" || echo "  (none matched)"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo " FIX COMPLETE — $(date)"
echo " Log: $LOG"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "NOTE: If Hermes is still not receiving Telegram messages,"
echo "      check the gateway log for token conflict:"
echo "      tail -50 ~/.hermes/profiles/cloud/logs/gateway.log"
echo ""
echo "NOTE: If any bot token shows as INVALID (401/403), it needs"
echo "      to be regenerated via @BotFather — notify Kato."
