#!/usr/bin/env bash
# Try to nudge tailscaled back online without re-auth.
set -u
LOG="$HOME/Desktop/REX/logs/_tailscale_kick.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

{
  echo "── Tailscale kick — $(date '+%Y-%m-%d %H:%M:%S') ──"

  TS=""
  for CAND in \
      /Applications/Tailscale.app/Contents/MacOS/Tailscale \
      /usr/local/bin/tailscale \
      /opt/homebrew/bin/tailscale; do
    if [ -x "$CAND" ]; then TS="$CAND"; break; fi
  done
  if [ -z "$TS" ]; then
    if command -v tailscale >/dev/null 2>&1; then TS="$(command -v tailscale)"; fi
  fi
  echo "CLI: ${TS:-<not found>}"
  [ -z "$TS" ] && exit 1

  echo
  echo "── status (before) ──"
  "$TS" status 2>&1 | head -30 || true

  echo
  echo "── ping controlplane (should hit it directly) ──"
  curl -s -o /dev/null -w "controlplane: %{http_code}  time=%{time_total}s\n" \
    --max-time 10 "https://controlplane.tailscale.com/key?v=133" 2>&1 || true

  echo
  echo "── tailscale up (no auth args, just reconnect) ──"
  "$TS" up --reset --accept-routes 2>&1 || true

  echo
  echo "── status (after) ──"
  "$TS" status 2>&1 | head -30 || true

  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 5
osascript -e 'tell application "Terminal" to close (every window whose name contains "_tailscale_kick")' >/dev/null 2>&1 || true
