#!/bin/zsh
# CC_telegram_watchdog.sh
# Detect and recover from Telegram polling freeze in Hermes cloud gateway.
# Part of Hermes Hardening — Fix 5 (2026-07-04)
# Run by launchd every 5 minutes via com.hermes.telegram-watchdog.plist
#
# Detection: gateway.log mtime — if the log hasn't been written in
# FREEZE_THRESHOLD seconds while the gateway process is alive, the
# Telegram polling loop is frozen and we restart.

set -uo pipefail

# ─── Config ───────────────────────────────────────────────────────────────────
LOG=/Users/mainsobhelper/Desktop/REX/logs/telegram_watchdog.log
GATEWAY_LOG=/Users/mainsobhelper/.hermes/profiles/cloud/logs/gateway.log
GATEWAY_PLIST=$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist
ENV_FILE=/Users/mainsobhelper/.hermes/profiles/cloud/.env
FREEZE_THRESHOLD=900      # 15 minutes in seconds
RESTART_COOLDOWN=600      # 10 minutes — don't double-restart
COOLDOWN_MARKER=/tmp/hermes_watchdog_cooldown
CHAT_ID=5587703834

# ─── Helpers ──────────────────────────────────────────────────────────────────
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# All output goes to log file
exec >> "$LOG" 2>&1

echo "$(ts) [watchdog] --- check start ---"

# Load bot token from .env (strip inline comment and whitespace)
BOT_TOKEN=$(grep 'TELEGRAM_BOT_TOKEN' "$ENV_FILE" | head -1 \
  | cut -d'=' -f2- | cut -d'#' -f1 | tr -d ' \t\r')

tg_notify() {
  local msg="$1"
  curl -s --max-time 10 \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${msg}" \
    > /dev/null 2>&1 || true
}

# ─── Cooldown guard ───────────────────────────────────────────────────────────
# Prevent hammering the gateway if something keeps triggering restarts.
if [[ -f "$COOLDOWN_MARKER" ]]; then
  cooldown_age=$(( ($(date +%s) - $(stat -f %m "$COOLDOWN_MARKER")) / 60 ))
  cooldown_limit=$(( RESTART_COOLDOWN / 60 ))
  if (( cooldown_age < cooldown_limit )); then
    echo "$(ts) [watchdog] In cooldown (${cooldown_age}m elapsed < ${cooldown_limit}m required). Skipping."
    exit 0
  fi
fi

# ─── Gateway process check ────────────────────────────────────────────────────
# If the process isn't running at all, launchd will revive it — nothing for
# us to do and we shouldn't restart manually.
if ! pgrep -f "hermes_cli.main.*gateway" > /dev/null 2>&1; then
  echo "$(ts) [watchdog] Gateway process not running — launchd will revive. Skipping freeze check."
  exit 0
fi

# ─── Log mtime freeze detection ───────────────────────────────────────────────
# The gateway writes to gateway.log on every inbound message and heartbeat
# tick. A live process + stale log == frozen Telegram polling loop.
if [[ ! -f "$GATEWAY_LOG" ]]; then
  echo "$(ts) [watchdog] gateway.log not found at $GATEWAY_LOG — cannot check. Skipping."
  exit 0
fi

LOG_AGE=$(( $(date +%s) - $(stat -f %m "$GATEWAY_LOG") ))
LOG_AGE_MIN=$(( LOG_AGE / 60 ))

echo "$(ts) [watchdog] gateway.log age: ${LOG_AGE}s (${LOG_AGE_MIN}m) — threshold: ${FREEZE_THRESHOLD}s."

if (( LOG_AGE < FREEZE_THRESHOLD )); then
  echo "$(ts) [watchdog] Healthy — no freeze detected. Done."
  exit 0
fi

# ─── Freeze confirmed — restart ───────────────────────────────────────────────
echo "$(ts) [watchdog] FREEZE DETECTED — gateway alive, log silent ${LOG_AGE}s (${LOG_AGE_MIN}m). Restarting."

# Set cooldown before restart so a crash loop can't bypass it
touch "$COOLDOWN_MARKER"

tg_notify "⚠️ Hermes Telegram polling freeze detected — log silent ${LOG_AGE_MIN}m. Auto-restarting cloud gateway now."

# Standard Hermes restart sequence
# Note: || true on launchctl load — a plist config issue must never propagate
# exit code 78 (EX_CONFIG) and cause this watchdog to exit non-zero.
launchctl unload "$GATEWAY_PLIST" 2>/dev/null || true
pkill -f "hermes_cli.main.*gateway" 2>/dev/null || true
sleep 8
launchctl load "$GATEWAY_PLIST" || true

echo "$(ts) [watchdog] Restart sequence issued."

# ─── Post-restart confirmation ────────────────────────────────────────────────
sleep 5
if pgrep -f "hermes_cli.main.*gateway" > /dev/null 2>&1; then
  echo "$(ts) [watchdog] ✓ Gateway confirmed running after restart."
  tg_notify "✅ Hermes cloud gateway restarted successfully after ${LOG_AGE_MIN}m freeze."
else
  echo "$(ts) [watchdog] ✗ WARNING: Gateway did NOT come back up after restart — manual intervention required."
  tg_notify "❌ Hermes cloud gateway FAILED to restart after ${LOG_AGE_MIN}m freeze — manual intervention required."
fi

echo "$(ts) [watchdog] --- check end ---"
