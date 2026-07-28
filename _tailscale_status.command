#!/usr/bin/env bash
LOG="$HOME/Desktop/REX/logs/_tailscale_status.log"
: > "$LOG"

TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
{
  echo "── Status — $(date '+%Y-%m-%d %H:%M:%S') ──"
  echo
  echo "── tailscale status --json (truncated to health + state) ──"
  "$TS" status --json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('BackendState:', d.get('BackendState'))
    print('AuthURL:', d.get('AuthURL') or '(none)')
    print('Health:')
    for h in (d.get('Health') or []):
        print(' -', h)
    print('Version:', d.get('Version'))
    print('Self.Online:', (d.get('Self') or {}).get('Online'))
except Exception as e:
    print('parse failed:', e)
"
  echo
  echo "── netstat IPv6 routes (default) ──"
  netstat -nr -f inet6 | grep -E "^default" | head -5
  echo
  echo "── IPv6 reachability test ──"
  curl -6 -s -o /dev/null -w "controlplane IPv6: %{http_code}  time=%{time_total}s\n" \
    --max-time 8 "https://controlplane.tailscale.com/key?v=133" 2>&1
  curl -4 -s -o /dev/null -w "controlplane IPv4: %{http_code}  time=%{time_total}s\n" \
    --max-time 8 "https://controlplane.tailscale.com/key?v=133" 2>&1
  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_tailscale_status")' >/dev/null 2>&1 || true
