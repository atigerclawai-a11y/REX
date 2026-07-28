#!/usr/bin/env bash
# Uninstall Cloudflare WARP (move the app to Trash, then quit any remaining UI).
# Removing the system NetworkExtension itself has to happen in System Settings —
# that prompt always requires Touch ID / password and can't be scripted.
set -u
LOG="$HOME/Desktop/REX/logs/_warp_uninstall.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

APP="/Applications/Cloudflare WARP.app"
TRASH="$HOME/.Trash/"

{
  echo "── WARP uninstall — $(date '+%Y-%m-%d %H:%M:%S') ──"

  echo
  echo "── disconnect (if not already) ──"
  /usr/local/bin/warp-cli disconnect 2>&1 | head -3 || true

  echo
  echo "── quit GUI ──"
  osascript -e 'tell application "Cloudflare WARP" to quit' 2>&1 || true
  sleep 1

  echo
  echo "── unregister daemon service (if loadable as user agent) ──"
  /Applications/Cloudflare\ WARP.app/Contents/Resources/uninstall.sh 2>&1 | head -10 || echo "(no uninstall.sh — moving on)"

  echo
  echo "── move app bundle to Trash ──"
  if [ -d "$APP" ]; then
    osascript -e 'tell application "Finder" to delete POSIX file "/Applications/Cloudflare WARP.app"' 2>&1 | head -5 || true
    sleep 2
    if [ -d "$APP" ]; then
      echo "Finder delete didn't move it — likely a permissions prompt is up. If you authenticate it, this script can finish."
    else
      echo "Moved to Trash."
    fi
  else
    echo "App is already gone from /Applications."
  fi

  echo
  echo "── leftover Cloudflare WARP processes ──"
  pgrep -fl "Cloudflare WARP" 2>&1 || echo "(none running)"

  echo
  echo "── Tailscale status now ──"
  /Applications/Tailscale.app/Contents/MacOS/Tailscale status 2>&1 | head -10

  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_warp_uninstall")' >/dev/null 2>&1 || true
