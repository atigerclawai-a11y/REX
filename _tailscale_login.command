#!/usr/bin/env bash
LOG="$HOME/Desktop/REX/logs/_tailscale_login.log"
: > "$LOG"

TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

{
  echo "── Login — $(date '+%Y-%m-%d %H:%M:%S') ──"
  echo "Triggering tailscale login (background; this command stays running until auth completes)…"
  # Run tailscale login in the background and capture output. It typically prints an auth URL.
  "$TS" login > /tmp/_tailscale_login_output.txt 2>&1 &
  LOGIN_PID=$!
  echo "PID: $LOGIN_PID"
  # Give it a few seconds to print the URL
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if grep -qE "https://login\.tailscale\.com|To authenticate, visit" /tmp/_tailscale_login_output.txt 2>/dev/null; then
      break
    fi
  done
  echo
  echo "── Output so far ──"
  cat /tmp/_tailscale_login_output.txt 2>/dev/null
  echo
  AUTH_URL=$(grep -oE 'https://login\.tailscale\.com/[^[:space:]]+' /tmp/_tailscale_login_output.txt 2>/dev/null | head -1)
  if [ -n "$AUTH_URL" ]; then
    echo "AUTH_URL: $AUTH_URL"
    # Save the URL and open it in the default browser
    echo "$AUTH_URL" > "$HOME/Desktop/REX/logs/_tailscale_login_url.txt"
    open "$AUTH_URL"
    echo "Opened in browser."
  else
    echo "No auth URL produced (yet). Check status."
    "$TS" status 2>&1 | head -10
  fi
  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

# Don't auto-close — the login command may still be running, want it alive
