#!/usr/bin/env bash
# CC_identify_pid77588.command — find what's holding the Telegram token
LOG="$HOME/Desktop/REX/logs/cc_identify_pid77588.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════"
echo "  Identify Token-Conflict Process"
echo "══════════════════════════════════"
echo ""

TOKEN_PREFIX="8648749431"

echo "── What is PID 77588? ──"
ps -p 77588 -o pid,ppid,comm,args 2>/dev/null || echo "PID 77588 not currently running"

echo ""
echo "── All processes holding bot token $TOKEN_PREFIX ──"
pgrep -fla "$TOKEN_PREFIX" 2>/dev/null || echo "(none)"

echo ""
echo "── All Python/node processes with 'hermes' or 'vellum' ──"
ps aux | grep -iE "hermes|vellum" | grep -v grep | grep -v "hermes-workspace"

echo ""
echo "── LaunchAgents that might spawn this ──"
grep -rl "$TOKEN_PREFIX" "$HOME/Library/LaunchAgents/" 2>/dev/null
grep -rl "vellum" "$HOME/Library/LaunchAgents/" 2>/dev/null -i

echo ""
echo "── What is Vellum — list vellum-related processes ──"
ps aux | grep -i vellum | grep -v grep

echo ""
echo "── Vellum LaunchAgents ──"
ls "$HOME/Library/LaunchAgents/" | grep -i vellum

echo ""
echo "── If a Vellum LaunchAgent exists, show its plist ──"
for f in "$HOME/Library/LaunchAgents/"*vellum* "$HOME/Library/LaunchAgents/"*Vellum*; do
  [ -f "$f" ] && echo "=== $f ===" && cat "$f"
done

echo ""
echo "Done."
sleep 8
