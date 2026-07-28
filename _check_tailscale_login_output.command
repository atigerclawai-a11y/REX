#!/usr/bin/env bash
LOG="$HOME/Desktop/REX/logs/_tailscale_login_check.log"
: > "$LOG"
{
  echo "── login output capture ──"
  if [ -f /tmp/_tailscale_login_output.txt ]; then
    cat /tmp/_tailscale_login_output.txt
  else
    echo "(no file at /tmp/_tailscale_login_output.txt)"
  fi
  echo
  echo "── PIDs ──"
  ps -axo pid,command | grep -E "tailscale[ ]+(login|up)" | head -5
  echo
  echo "── status ──"
  /Applications/Tailscale.app/Contents/MacOS/Tailscale status 2>&1 | head -10
} 2>&1 | tee -a "$LOG"
sleep 3
osascript -e 'tell application "Terminal" to close (every window whose name contains "_check_tailscale_login_output")' >/dev/null 2>&1 || true
