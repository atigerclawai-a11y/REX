#!/usr/bin/env bash
# One-shot setup: install a LaunchAgent that triggers _rescan_master_log.command
# tonight at 22:00 local time. The rescan script removes the LaunchAgent itself
# after firing so this is truly one-shot.
set -u

LOG="$HOME/Desktop/REX/logs/_setup_rescan_launchagent.log"
mkdir -p "$HOME/Desktop/REX/logs" "$HOME/Library/LaunchAgents"
: > "$LOG"

LABEL="com.kato.goj-rescan-tue-2026-05-11"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SCRIPT="$HOME/Desktop/REX/_rescan_master_log.command"
chmod +x "$SCRIPT"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SCRIPT</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Year</key>   <integer>2026</integer>
    <key>Month</key>  <integer>5</integer>
    <key>Day</key>    <integer>11</integer>
    <key>Hour</key>   <integer>22</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>$HOME/Desktop/REX/logs/goj_master_log_rescan.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Desktop/REX/logs/goj_master_log_rescan.stderr.log</string>
</dict>
</plist>
EOF

{
  echo "── Setup at $(date '+%Y-%m-%d %H:%M:%S') ──"
  echo "Plist: $PLIST"
  echo
  echo "── Loading LaunchAgent ──"
  launchctl unload "$PLIST" 2>/dev/null
  launchctl load   "$PLIST"
  echo "Exit: $?"
  echo
  echo "── Verifying ──"
  launchctl list | grep "$LABEL" || echo "(not in list — check logs)"
  echo
  echo "Will fire at: 2026-05-11 22:00 local time"
  echo "Will pull SIGN IN master log, diff vs baseline, Telegram-alert Kato only if changed."
  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_setup_rescan_launchagent")' >/dev/null 2>&1 || true
