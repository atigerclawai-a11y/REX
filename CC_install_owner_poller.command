#!/bin/bash
# CC_install_owner_poller.command
# Installs + loads the owner.com reservation poller as a launchd service (every 5 min).
# Run this yourself to authorize the persistent service (Claude Code's classifier
# blocks an agent from activating new persistence without explicit owner action).
# Verified 2026-06-25: CC_owner_reservation_poller.py --dry-run runs clean (stdlib-only).
set -euo pipefail
LOG=~/Desktop/REX/logs/CC_install_owner_poller_$(date +%Y%m%d_%H%M%S).log
exec > >(tee "$LOG") 2>&1

PLIST=~/Library/LaunchAgents/com.goj.owner-poller.plist
PY=~/Desktop/REX/.venv/bin/python3   # REAL venv

echo "Writing $PLIST ..."
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.goj.owner-poller</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$HOME/Desktop/REX/CC_owner_reservation_poller.py</string>
    <string>--cron</string>
  </array>
  <key>WorkingDirectory</key><string>$HOME/Desktop/REX</string>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$HOME/Desktop/REX/logs/owner_poller_stdout.log</string>
  <key>StandardErrorPath</key><string>$HOME/Desktop/REX/logs/owner_poller_stderr.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
</dict></plist>
XML

echo "Validating ..."
plutil -lint "$PLIST"

echo "Loading ..."
launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"

echo "Verifying ..."
sleep 2
if launchctl list | grep -q com.goj.owner-poller; then
  echo "✅ com.goj.owner-poller LOADED (polls owner.com email every 5 min, --cron mode)"
else
  echo "❌ not loaded — check $LOG and 'launchctl print gui/$(id -u)/com.goj.owner-poller'"
fi
echo "To remove later: launchctl bootout gui/$(id -u) $PLIST && rm $PLIST"
