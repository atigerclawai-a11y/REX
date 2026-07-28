#!/usr/bin/env bash
# CC_bot_status_check.command — check all bot status + find attendance bot + check hermes plist token
OUT="$HOME/Desktop/REX/logs/cc_bot_status.txt"
mkdir -p "$HOME/Desktop/REX/logs"

{
echo "══════════════════════════════════════════════"
echo "  BOT STATUS CHECK — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════"

echo ""
echo "── LaunchAgents (all) ──"
ls -la "$HOME/Library/LaunchAgents/" 2>/dev/null

echo ""
echo "── launchctl list: hermes/rex/bot/goj/attend ──"
launchctl list | grep -iE "hermes|rex|bot|goj|attend" | sort

echo ""
echo "── Hermes Cloud plist EnvironmentVariables ──"
cat "$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist" 2>/dev/null | grep -A3 -i "TELEGRAM\|TOKEN\|EnvironmentVariables" || echo "(not found)"

echo ""
echo "── Attendance bot search ──"
# Check plists for attendance/goj keywords
grep -rl "attend\|GojAtten\|8129962" "$HOME/Library/LaunchAgents/" 2>/dev/null || echo "(no plist matches)"

echo ""
echo "── Find attend/goj python scripts ──"
find "$HOME/Desktop" -name "*.py" 2>/dev/null | xargs grep -l "attend\|8129962\|GojAtten" 2>/dev/null | head -10 || echo "(none)"
find "$HOME" -maxdepth 5 -name "*attend*" -o -name "*goj_attend*" 2>/dev/null | grep -v "\.git\|Library/Caches" | head -10

echo ""
echo "── Running python bot processes ──"
pgrep -fla "python\|telegram\|bot" 2>/dev/null | grep -v "grep\|pyc" || echo "(none)"

echo ""
echo "── Hermes rexxie-bot plist ──"
cat "$HOME/Library/LaunchAgents/com.hermes.rexxie-bot.plist" 2>/dev/null | grep -iE "TOKEN\|TELEGRAM\|ProgramArguments" || echo "(not found)"

echo ""
echo "── com.rex.rexxie-bot plist TOKEN check ──"
cat "$HOME/Library/LaunchAgents/com.rex.rexxie-bot.plist" 2>/dev/null | grep -iE "TOKEN\|TELEGRAM\|EnvironmentVariables" | head -10 || echo "(not found)"

echo ""
echo "── receipt_processor check ──"
ls "$HOME/Desktop/receipt_processor/" 2>/dev/null && echo "EXISTS" || echo "NOT FOUND — bot cannot run"

echo ""
echo "══ DONE ══"
} | tee "$OUT"

echo ""
echo "Saved to: $OUT"
sleep 8
