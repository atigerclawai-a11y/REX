#!/bin/bash
# Pre-call red team check — runs at 1:45 PM before 2 PM caller
LOG=~/Desktop/REX/logs/victoria_pre_checks.log
touch "$LOG"
echo "=== $(date '+%Y-%m-%d %H:%M') ===" >> "$LOG"

PASS=0
FAIL=0

check() {
    local what=$1; shift
    if "$@" &>/dev/null; then
        echo "  ✅ $what" >> "$LOG"; ((PASS++))
    else
        echo "  ❌ $what" >> "$LOG"; ((FAIL++))
    fi
}

check "Agent alive" curl -s --max-time 5 "https://api.retellai.com/v2/get-agent/agent_8a326510567e7dc3e2dc5221df" -H "Authorization: Bearer key_48a2ed4781d093c125451e40ddb4"
check "Caller plist" launchctl list | grep -q com.goj.victoria-caller
check "Drive reachable" curl -s --max-time 5 "https://www.googleapis.com/drive/v3/files" -H "Authorization: Bearer $(grep DRIVE_TOKEN ~/Desktop/REX/.env 2>/dev/null | cut -d= -f2)"
check "DB accessible" sqlite3 ~/Documents/goj\ files/proprietary/goj_proprietary.db "SELECT COUNT(*) FROM clients" &>/dev/null
check "Token fresh" python3 -c "
from datetime import datetime; import os
# Heartbeat = token-refresh watchdog log (written daily 13:00). Phantom ~/.victoria_token was never created by any script.
t = os.path.getmtime('$HOME/Desktop/REX/logs/victoria_token_refresh.log')
age = (datetime.now() - datetime.fromtimestamp(t)).total_seconds()
exit(1 if age > 3600 else 0)
"

echo "  $PASS passed, $FAIL failed" >> "$LOG"
[ "$FAIL" -eq 0 ] && echo "✅ ALL CLEAR" >> "$LOG" || echo "⚠️ $FAIL CHECKS FAILED" >> "$LOG"
echo "" >> "$LOG"
