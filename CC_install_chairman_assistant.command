#!/bin/bash
# CC_install_chairman_assistant.command
# Runs the Chairman SMS assistant webhook (CC_chairman_assistant.py --serve) as an
# always-on launchd service on 127.0.0.1:8110. KeepAlive + RunAtLoad.
# The webhook is FAIL-CLOSED: until TWILIO_AUTH_TOKEN + CHAIRMAN_WEBHOOK_URL are set
# in ~/.hermes/.env it rejects every request, so it's safe to start early.
# Point your Twilio number's Messaging webhook at:  <public tunnel URL> -> :8110
set -euo pipefail
LOG=~/Desktop/REX/logs/CC_install_chairman_assistant_$(date +%Y%m%d_%H%M%S).log
exec > >(tee "$LOG") 2>&1
PLIST=~/Library/LaunchAgents/com.goj.chairman-assistant.plist
PY=~/Desktop/REX/.venv/bin/python3

cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.goj.chairman-assistant</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string>
    <string>$HOME/Desktop/REX/CC_chairman_assistant.py</string><string>--serve</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>WorkingDirectory</key><string>$HOME/Desktop/REX</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$HOME/Desktop/REX/logs/chairman_assistant.log</string>
  <key>StandardErrorPath</key><string>$HOME/Desktop/REX/logs/chairman_assistant.err</string>
</dict></plist>
XML
chmod 600 "$PLIST"
plutil -lint "$PLIST"
launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"
sleep 2
launchctl list | grep -q com.goj.chairman-assistant \
  && echo "✅ Chairman SMS webhook always-on at 127.0.0.1:8110 (fail-closed until secrets set)." \
  || echo "❌ not loaded — check $LOG and logs/chairman_assistant.err"
echo "Stop/remove: launchctl bootout gui/\$(id -u) $PLIST && rm $PLIST"
