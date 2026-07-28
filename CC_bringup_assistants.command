#!/bin/bash
# CC_bringup_assistants.command — ONE command to bring up Kato's personal-assistant stack.
# Idempotent + safe: smoke-tests both brains locally, starts every service whose
# prerequisites are met, and prints an exact checklist for whatever still needs you.
# Re-run it any time — it only starts what's ready and never breaks what's working.
#
#   Usage:  ./CC_bringup_assistants.command [REXXIE_SIGNAL_NUMBER]
#   (or export REXXIE_SIGNAL_NUMBER beforehand)
set -uo pipefail   # not -e: we want to run every check and report, not abort on first miss
REX=~/Desktop/REX
PY=$REX/.venv/bin/python3
ENVF=~/.hermes/.env
LOG=$REX/logs/CC_bringup_$(date +%Y%m%d_%H%M%S).log
mkdir -p "$REX/logs"
exec > >(tee "$LOG") 2>&1
ok(){ printf "  ✅ %s\n" "$1"; }
no(){ printf "  ⛔ %s\n" "$1"; }
hd(){ printf "\n\033[1m%s\033[0m\n" "$1"; }
TODO=()

hd "1) Local prerequisites"
pgrep -x ollama >/dev/null && ok "Ollama running" || { open -a Ollama 2>/dev/null; sleep 3; pgrep -x ollama >/dev/null && ok "Ollama started" || { no "Ollama not running"; TODO+=("Start Ollama: open -a Ollama"); }; }
ollama list 2>/dev/null | grep -qi "llama3.2:3b" && ok "llama3.2:3b present" || { no "model missing — pulling"; ollama pull llama3.2:3b && ok "pulled"; }
[ -x "$PY" ] && ok "REAL venv present" || { no "venv missing"; TODO+=("Recreate ~/Desktop/REX/.venv"); }
command -v signal-cli >/dev/null && ok "signal-cli installed" || { no "signal-cli missing"; TODO+=("brew install signal-cli"); }

hd "2) Smoke-test the brains locally (no Signal / no Twilio needed)"
R=$("$PY" "$REX/CC_rexxie_signal.py" "In one line: are you online and local?" 2>&1 | head -1)
[ -n "$R" ] && ok "Rexxie brain: $R" || no "Rexxie brain gave no reply (is Ollama up?)"
C=$("$PY" "$REX/CC_chairman_assistant.py" "help" 2>&1 | head -1)
echo "$C" | grep -qi "Chairman" && ok "Chairman assistant replies" || no "Chairman assistant: $C"

hd "3) Secrets & links preflight (presence only — values never shown)"
have(){ [ -f "$ENVF" ] && grep -q "^$1=" "$ENVF" && [ -n "$(grep "^$1=" "$ENVF" | head -1 | cut -d= -f2- | tr -d '\"'\'' ')" ]; }
SIG_NUM="${1:-${REXXIE_SIGNAL_NUMBER:-}}"
[ -z "$SIG_NUM" ] && SIG_NUM=$(ls ~/.local/share/signal-cli/data/*.d 2>/dev/null | head -1 | xargs -I{} basename {} .d 2>/dev/null)
if [ -n "$SIG_NUM" ] && signal-cli -a "$SIG_NUM" listIdentities >/dev/null 2>&1; then
  ok "Rexxie Signal account linked: $SIG_NUM"; SIG_READY=1
else
  no "Rexxie not linked to Signal"; SIG_READY=0
  TODO+=("Link Rexxie to Signal:  signal-cli link -n \"Rexxie\"   (scan QR in phone → Linked Devices), then re-run with her number")
fi
have CHAIRMAN_PIN        && ok "CHAIRMAN_PIN set"        || { no "CHAIRMAN_PIN missing";        TODO+=("Add to $ENVF:  CHAIRMAN_PIN=<your pin>"); }
have TWILIO_AUTH_TOKEN   && ok "TWILIO_AUTH_TOKEN set"   || { no "TWILIO_AUTH_TOKEN missing";   TODO+=("Add to $ENVF:  TWILIO_AUTH_TOKEN=<from Twilio console>"); }
have CHAIRMAN_WEBHOOK_URL&& ok "CHAIRMAN_WEBHOOK_URL set"|| { no "CHAIRMAN_WEBHOOK_URL missing"; TODO+=("Add to $ENVF:  CHAIRMAN_WEBHOOK_URL=https://<your-tunnel>/  (the public URL Twilio POSTs to)"); }

hd "4) Bring up always-on services (only what's ready)"
if [ "$SIG_READY" = 1 ]; then
  REXXIE_SIGNAL_NUMBER="$SIG_NUM" bash "$REX/CC_install_rexxie_signal.command" "$SIG_NUM"
else
  no "Skipping Rexxie Signal service — not linked yet (see checklist)"
fi
bash "$REX/CC_install_chairman_assistant.command"   # fail-closed; safe to start now
bash "$REX/CC_install_chairman_notify.command"      # schedules daily 3 PM SMS summary

hd "5) Status"
launchctl list | grep -E "com.goj.(rexxie-signal|chairman-assistant|chairman-notify)" | awk '{printf "  %s  pid=%s\n",$3,$1}'

hd "WHAT'S LEFT (do these, then re-run this one command)"
if [ ${#TODO[@]} -eq 0 ]; then
  echo "  🎉 Nothing — the stack is fully live. Text Rexxie on Signal; text the Chairman number for SMS."
  echo "  Last step if you just set secrets: in the Twilio console point the number's Messaging webhook"
  echo "  at your CHAIRMAN_WEBHOOK_URL (forwarding to :8110)."
else
  i=1; for t in "${TODO[@]}"; do printf "  %d. %s\n" "$i" "$t"; i=$((i+1)); done
fi
echo
echo "Full log: $LOG"
