#!/bin/bash
# CC_install_rexxie_signal.command
# Runs Rexxie's private Signal brain (CC_rexxie_signal.py --serve) as an always-on
# launchd service: starts at login, restarts if it dies. Fully local — never cloud.
#
# PREREQ: link Rexxie to Signal first, then run this with her number:
#   signal-cli link -n "Rexxie"        # scan the QR from your phone
#   ./CC_install_rexxie_signal.command +1XXXXXXXXXX   # her Signal number
# (or export REXXIE_SIGNAL_NUMBER before running)
set -euo pipefail
LOG=~/Desktop/REX/logs/CC_install_rexxie_signal_$(date +%Y%m%d_%H%M%S).log
exec > >(tee "$LOG") 2>&1

NUM="${1:-${REXXIE_SIGNAL_NUMBER:-}}"
if [ -z "$NUM" ]; then
  echo "❌ Need Rexxie's Signal number. Usage: ./CC_install_rexxie_signal.command +1XXXXXXXXXX"
  echo "   (link first: signal-cli link -n \"Rexxie\")"
  exit 1
fi
# sanity: is signal-cli aware of this account?
if ! signal-cli -a "$NUM" listIdentities >/dev/null 2>&1; then
  echo "⚠️  signal-cli doesn't recognize $NUM yet — make sure you linked/registered it first."
fi

PLIST=~/Library/LaunchAgents/com.goj.rexxie-signal.plist
PY=~/Desktop/REX/.venv/bin/python3
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.goj.rexxie-signal</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string>
    <string>$HOME/Desktop/REX/CC_rexxie_signal.py</string><string>--serve</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>REXXIE_SIGNAL_NUMBER</key><string>$NUM</string>
    <key>KATO_SIGNAL_NUMBER</key><string>+13475879913</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>WorkingDirectory</key><string>$HOME/Desktop/REX</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$HOME/Desktop/REX/logs/rexxie_signal.log</string>
  <key>StandardErrorPath</key><string>$HOME/Desktop/REX/logs/rexxie_signal.err</string>
</dict></plist>
XML
chmod 600 "$PLIST"
plutil -lint "$PLIST"
launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"
sleep 2
launchctl list | grep -q com.goj.rexxie-signal \
  && echo "✅ Rexxie is always-on (Signal $NUM). Text her — she answers locally, encrypted, with memory." \
  || echo "❌ not loaded — check $LOG and logs/rexxie_signal.err"
echo "Stop/remove: launchctl bootout gui/$(id -u) $PLIST && rm $PLIST"
