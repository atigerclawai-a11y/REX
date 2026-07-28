#!/usr/bin/env bash
# Bounce tailscaled via launchctl kickstart. Will prompt for admin password
# via a macOS dialog (osascript) — that's the only thing that needs the password.
set -u
LOG="$HOME/Desktop/REX/logs/_tailscale_daemon_kick.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

{
  echo "── Daemon kick — $(date '+%Y-%m-%d %H:%M:%S') ──"

  # Pop a single macOS password dialog and run the kickstart through sudo -A.
  # The dialog is the only place a password is typed; the bash session never sees it.
  SUDO_ASKPASS_SCRIPT="$(mktemp)"
  cat > "$SUDO_ASKPASS_SCRIPT" <<'ASK'
#!/usr/bin/env bash
osascript -e 'Tell application "System Events" to display dialog "Tailscale daemon is wedged — restarting tailscaled to clear it.\n\nEnter your Mac password:" default answer "" with hidden answer with title "Restart Tailscale" buttons {"Cancel","OK"} default button "OK"' -e 'text returned of result' 2>/dev/null
ASK
  chmod +x "$SUDO_ASKPASS_SCRIPT"

  echo "── Restarting tailscaled ──"
  SUDO_ASKPASS="$SUDO_ASKPASS_SCRIPT" sudo -A -p "" launchctl kickstart -k system/com.tailscale.tailscaled
  RC=$?
  rm -f "$SUDO_ASKPASS_SCRIPT"
  echo "kickstart exit: $RC"

  sleep 3
  echo
  echo "── tailscale status (after) ──"
  /Applications/Tailscale.app/Contents/MacOS/Tailscale status 2>&1 | head -20
  echo
  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_tailscale_daemon_kick")' >/dev/null 2>&1 || true
