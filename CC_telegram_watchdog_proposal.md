# Fix 5: Telegram Polling Freeze Watchdog — Proposal
# Gold Health Systems · Hermes Hardening · 2026-07-03
# Status: PROPOSED — do not build until Kato approves (PAE)

## Problem

The Telegram inbound polling loop can silently freeze: the gateway process is
alive, launchd thinks it's healthy, but no messages are being processed.
Current detection method: Kato notices Hermes stopped responding and manually
restarts. Mean time to detection can be hours.

## Proposed Fix: `CC_telegram_watchdog.sh`

A launchd-managed script that runs every 5 minutes and checks whether the
gateway's Telegram loop is actually alive. If it detects a freeze, it restarts
the cloud gateway and logs the event.

### Freeze detection heuristic

The gateway writes to `~/.hermes/profiles/cloud/logs/gateway.log` on every
inbound Telegram message and on every heartbeat tick. If the log has not been
modified in more than FREEZE_THRESHOLD_MINUTES AND the gateway PID is alive,
the loop is frozen (process up, polling dead).

A log that hasn't grown isn't enough on its own — the gateway could just be
idle. The second condition (PID alive but no log writes) is the key. To avoid
false restarts during legitimate idle periods, the threshold should be at least
15 minutes (well above normal idle between Kato messages).

### Implementation sketch

```bash
#!/bin/zsh
# CC_telegram_watchdog.sh
# Detect and recover from Telegram polling freeze in Hermes cloud gateway.
# Run by launchd every 5 minutes via com.goj.telegram-watchdog.plist

set -euo pipefail
LOG=/Users/mainsobhelper/Desktop/REX/logs/telegram_watchdog.log
GATEWAY_LOG=/Users/mainsobhelper/.hermes/profiles/cloud/logs/gateway.log
GATEWAY_PID_FILE=/Users/mainsobhelper/.hermes/profiles/cloud/gateway.pid
GATEWAY_PLIST=~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
FREEZE_THRESHOLD_MINUTES=15
RESTART_COOLDOWN_MINUTES=10
COOLDOWN_MARKER=/tmp/hermes_watchdog_cooldown

exec >> "$LOG" 2>&1

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Cooldown: don't restart more than once per RESTART_COOLDOWN_MINUTES
if [[ -f "$COOLDOWN_MARKER" ]]; then
  cooldown_age=$(( ($(date +%s) - $(stat -f %m "$COOLDOWN_MARKER")) / 60 ))
  if (( cooldown_age < RESTART_COOLDOWN_MINUTES )); then
    echo "$(ts) [watchdog] In cooldown (${cooldown_age}m < ${RESTART_COOLDOWN_MINUTES}m). Skipping."
    exit 0
  fi
fi

# Check if gateway PID is alive
if [[ ! -f "$GATEWAY_PID_FILE" ]]; then
  echo "$(ts) [watchdog] No PID file found — gateway not running (launchd will revive). Exiting."
  exit 0
fi
GATEWAY_PID=$(cat "$GATEWAY_PID_FILE")
if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
  echo "$(ts) [watchdog] PID $GATEWAY_PID not alive — launchd will revive. Exiting."
  exit 0
fi

# Check last log write age
LOG_AGE_MINUTES=$(( ($(date +%s) - $(stat -f %m "$GATEWAY_LOG")) / 60 ))
if (( LOG_AGE_MINUTES < FREEZE_THRESHOLD_MINUTES )); then
  echo "$(ts) [watchdog] Gateway log updated ${LOG_AGE_MINUTES}m ago. Healthy."
  exit 0
fi

# Freeze confirmed: PID alive, log silent > threshold
echo "$(ts) [watchdog] FREEZE DETECTED — PID $GATEWAY_PID alive, log silent ${LOG_AGE_MINUTES}m. Restarting gateway."
touch "$COOLDOWN_MARKER"

launchctl unload "$GATEWAY_PLIST" 2>/dev/null || true
pkill -f "hermes_cli.main.*gateway.*cloud" 2>/dev/null || true
sleep 8
launchctl load "$GATEWAY_PLIST"

echo "$(ts) [watchdog] Gateway restart issued."
```

### launchd plist: `com.goj.telegram-watchdog.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.goj.telegram-watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>/Users/mainsobhelper/Desktop/REX/CC_telegram_watchdog.sh</string>
  </array>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/Users/mainsobhelper/Desktop/REX/logs/telegram_watchdog.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/mainsobhelper/Desktop/REX/logs/telegram_watchdog.log</string>
</dict>
</plist>
```

Install with:
```bash
cp ~/Library/LaunchAgents/com.goj.telegram-watchdog.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.goj.telegram-watchdog.plist
```

## Open questions before building

1. Is FREEZE_THRESHOLD_MINUTES=15 right? Too aggressive = spurious restarts during
   legitimate idle. Too loose = long outages. Kato to confirm.
2. Should the watchdog send a Telegram notification to Kato when it fires?
   (via @Hermes_Cloud_May_bot or a direct curl to the bot API)
3. Better heuristic available: check state.db for last message timestamp in the
   telegram session, rather than relying on log file mtime. More precise but
   requires sqlite3 in the watchdog. Worth it?

## Decision required (PAE)

PROPOSE: CC_telegram_watchdog.sh + com.goj.telegram-watchdog.plist as above.
APPROVE: Kato signs off on threshold, notification preference, and heuristic.
EXECUTE: Build + install only after approval.
