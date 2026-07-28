#!/usr/bin/env bash
# Disconnect Cloudflare WARP so it stops claiming the network-extension slot
# Tailscale needs. Doesn't uninstall WARP — just disconnects it.
set -u
LOG="$HOME/Desktop/REX/logs/_warp_disconnect.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

WARP_CLI=""
for CAND in /usr/local/bin/warp-cli /opt/homebrew/bin/warp-cli; do
  [ -x "$CAND" ] && WARP_CLI="$CAND" && break
done
[ -z "$WARP_CLI" ] && command -v warp-cli >/dev/null 2>&1 && WARP_CLI="$(command -v warp-cli)"

{
  echo "── WARP disconnect — $(date '+%Y-%m-%d %H:%M:%S') ──"
  echo "warp-cli: ${WARP_CLI:-<not found>}"
  echo

  if [ -n "$WARP_CLI" ]; then
    echo "── status (before) ──"
    "$WARP_CLI" status 2>&1 | head -5
    echo
    echo "── disconnect ──"
    "$WARP_CLI" disconnect 2>&1 | head -5
    sleep 2
    echo
    echo "── status (after) ──"
    "$WARP_CLI" status 2>&1 | head -5
  else
    echo "warp-cli not found — falling back to quitting the GUI app."
    osascript -e 'tell application "Cloudflare WARP" to quit' 2>&1
  fi

  echo
  echo "── pkill any lingering warp processes (best-effort, no sudo) ──"
  pkill -x "Cloudflare WARP"     2>&1 || true
  pkill -x "CloudflareWARP"      2>&1 || true

  echo
  echo "── Tailscale status after WARP gone ──"
  sleep 3
  /Applications/Tailscale.app/Contents/MacOS/Tailscale status 2>&1 | head -10
  echo
  echo "── controlplane reachability ──"
  curl -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" --max-time 6 \
    "https://controlplane.tailscale.com/key?v=133" 2>&1
  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_warp_disconnect")' >/dev/null 2>&1 || true
