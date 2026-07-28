#!/usr/bin/env bash
set -u
LOG="$HOME/Desktop/REX/logs/_hermes_tg_check.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

{
  echo "── Hermes Telegram check — $(date '+%Y-%m-%d %H:%M:%S') ──"

  TOKEN="8702536335:AAHlGlEpLVuq9RAaqNq4kugv1MqJRg4IJQY"

  echo
  echo "── 1. Bot identity (getMe) ──"
  curl -s "https://api.telegram.org/bot$TOKEN/getMe" | python3 -m json.tool

  echo
  echo "── 2. Webhook state (should be empty for long-polling mode) ──"
  curl -s "https://api.telegram.org/bot$TOKEN/getWebhookInfo" | python3 -m json.tool

  echo
  echo "── 3. Recent gateway log mentions of telegram (last 30) ──"
  grep -iE "telegram|tg|hermie" ~/.hermes/logs/gateway.log 2>/dev/null | tail -30

  echo
  echo "── 4. Gateway error log mentions of telegram (last 30) ──"
  grep -iE "telegram|tg" ~/.hermes/logs/gateway.error.log 2>/dev/null | tail -30

  echo
  echo "── 5. Active telegram-related processes ──"
  ps -axo pid,command | grep -iE "telegram|hermes.*tg" | grep -v grep | head -10

  echo
  echo "── 6. Active gateway PID(s) ──"
  pgrep -fl "hermes" | head -10

  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_hermes_tg_check")' >/dev/null 2>&1 || true
