#!/bin/bash
# CC_install_chairman_notify.command
# Schedules the daily Chairman call-run summary → SMS to Kato (+1-347-587-9913)
# at 3:00 PM weekdays (after Victoria's 2 PM GOJ run). GOJ summary is de-identified.
# Run this yourself to authorize the persistent job (harness blocks an agent from it).
# Test first without scheduling:  python3 CC_chairman_notify.py            (dry-run)
#                                 python3 CC_chairman_notify.py --send     (texts you now)
set -euo pipefail
LOG=~/Desktop/REX/logs/CC_install_chairman_notify_$(date +%Y%m%d_%H%M%S).log
exec > >(tee "$LOG") 2>&1
PLIST=~/Library/LaunchAgents/com.goj.chairman-notify.plist
PY=~/Desktop/REX/.venv/bin/python3

cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.goj.chairman-notify</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$HOME/Desktop/REX/CC_chairman_notify.py</string>
    <string>--send</string>
  </array>
  <key>WorkingDirectory</key><string>$HOME/Desktop/REX</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$HOME/Desktop/REX/logs/chairman_notify_stdout.log</string>
  <key>StandardErrorPath</key><string>$HOME/Desktop/REX/logs/chairman_notify_stderr.log</string>
</dict></plist>
XML
chmod 600 "$PLIST"
plutil -lint "$PLIST"
launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"
sleep 1
launchctl list | grep -q com.goj.chairman-notify \
  && echo "✅ Daily 3 PM Chairman summary → SMS to +1-347-587-9913 scheduled." \
  || echo "❌ not loaded — check $LOG"
echo "Remove: launchctl bootout gui/$(id -u) $PLIST && rm $PLIST"
