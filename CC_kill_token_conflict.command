#!/usr/bin/env bash
# CC_kill_token_conflict.command — kill the process holding the Hermes cloud Telegram token, then restart gateway
LOG="$HOME/Desktop/REX/logs/cc_kill_token_conflict.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

TOKEN="8648749431"  # @Hermes_Cloud_May_bot token prefix

echo "══════════════════════════════════"
echo "  Kill Telegram Token Conflict"
echo "══════════════════════════════════"
echo ""

echo "── Processes holding token $TOKEN ──"
pgrep -fla "$TOKEN" 2>/dev/null || echo "(none found by token)"

echo ""
echo "── All hermes gateway processes ──"
pgrep -fla "hermes_cli.main.*gateway\|hermes-agent.*gateway\|hermes.*run" 2>/dev/null || echo "(none)"

echo ""
echo "── Stopping ALL gateway-related plist daemons ──"
for plist_label in "ai.hermes.gateway-cloud" "ai.hermes.gateway"; do
  plist="$HOME/Library/LaunchAgents/$plist_label.plist"
  if launchctl list | grep -q "$plist_label"; then
    echo "Unloading $plist_label..."
    launchctl unload "$plist" 2>/dev/null && echo "  → unloaded" || echo "  → failed"
  else
    echo "$plist_label not loaded"
  fi
done

echo ""
echo "── Killing any surviving hermes gateway processes ──"
pkill -f "hermes_cli.main.*gateway" 2>/dev/null && echo "Killed hermes_cli.main gateway processes" || echo "(no matching processes)"
pkill -f "hermes-agent.*gateway" 2>/dev/null && echo "Killed hermes-agent gateway processes" || echo "(no matching processes)"

echo ""
echo "── Waiting 8 seconds for ports and tokens to release ──"
sleep 8

echo ""
echo "── Verifying no gateway processes remain ──"
remaining=$(pgrep -f "hermes_cli.main.*gateway\|hermes-agent.*gateway" 2>/dev/null)
if [ -n "$remaining" ]; then
  echo "Still running — force killing: $remaining"
  echo "$remaining" | xargs kill -9 2>/dev/null
  sleep 3
else
  echo "✅ Clean — no competing processes"
fi

echo ""
echo "── Loading cloud gateway ──"
PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
launchctl load "$PLIST" && echo "Loaded" || echo "Load failed"

echo ""
echo "── Waiting 8 seconds for startup ──"
sleep 8

echo ""
echo "── Gateway status ──"
launchctl list | grep "ai.hermes.gateway"

echo ""
echo "── Recent log (last 25 lines) ──"
tail -25 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null

echo ""
echo "── Checking Telegram connection ──"
tail -30 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null | grep -i "telegram\|connected\|failed"

echo ""
echo "Done."
sleep 8
