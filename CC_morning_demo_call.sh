#!/bin/zsh
# ─────────────────────────────────────────────────────────────────────────────
# One-shot Hermes end-to-end DEMONSTRATION call — operator-authorized 2026-07-02.
# Fires two live calls to the operator's own phone to prove the staff-bot →
# voice-agent chain is built and working:
#   1) Masha  (BBG, English, 11labs-victoria, agent_305ba9…)  — first
#   2) Victoria (GOJ, Russian, 11labs-Kate,   agent_8a3265…)  — ~30s later
# Frozen agent/voice configs are reused unchanged; only the target differs.
# Self-disables its own launchd job after running so it NEVER repeats.
# ─────────────────────────────────────────────────────────────────────────────
set -u
PY="/Users/mainsobhelper/Desktop/REX/.venv-ocr/bin/python"
REX="/Users/mainsobhelper/Desktop/REX"
TO="+13475879913"                       # operator's own number (authorized demo target)
KATO=5587703834
LOG="$REX/logs/morning_demo_call.log"

TOKEN=$(/usr/bin/python3 -c "import json,pathlib;print(json.loads((pathlib.Path.home()/'.hermes/profiles/cloud/ghs_staff_config.json').read_text())['bot_token'])" 2>/dev/null)

notify() {
  [ -n "${TOKEN:-}" ] && curl -s --max-time 10 \
    "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$KATO" --data-urlencode "text=$1" >/dev/null 2>&1
}

echo "[$(date '+%F %T')] === Morning demo calls starting ===" >> "$LOG"
notify "🔔 Hermes demo — placing your two end-to-end test calls NOW: Masha (English) first, then Victoria (Russian) ~30s later. Answer your phone."

echo "[$(date '+%F %T')] Masha (BBG) → $TO" >> "$LOG"
"$PY" "$REX/bbg_masha_caller.py" --to "$TO" --name "Kato" --type followup \
   --note "Hermes end-to-end demonstration — this is a test call confirming the automated system is built and working" >> "$LOG" 2>&1
MRC=$?

sleep 30

echo "[$(date '+%F %T')] Victoria (GOJ) → $TO" >> "$LOG"
"$PY" "$REX/goj_victoria_caller.py" --to "$TO" --name "Kato" >> "$LOG" 2>&1
VRC=$?

# Honest per-call reporting — never claim success for a call that errored.
masha_ok="✅"; [ "$MRC" -ne 0 ] && masha_ok="❌"
vic_ok="✅";   [ "$VRC" -ne 0 ] && vic_ok="❌"
if [ "$MRC" -eq 0 ] && [ "$VRC" -eq 0 ]; then
  notify "$masha_ok Masha (BBG) + $vic_ok Victoria (GOJ) — BOTH demo calls placed. The staff-bot → Retell voice-agent chain is fully live. This one-shot demo will not repeat."
else
  notify "⚠️ Demo result: Masha $masha_ok (rc=$MRC), Victoria $vic_ok (rc=$VRC). One or both did NOT place — see $LOG. (One-shot; will not repeat.)"
fi
echo "[$(date '+%F %T')] Masha rc=$MRC  Victoria rc=$VRC" >> "$LOG"
echo "[$(date '+%F %T')] === Done; self-disabling one-shot job ===" >> "$LOG"

# One-shot guarantee: remove self so it never fires again.
launchctl bootout "gui/$(id -u)/com.goj.morning-demo-call" 2>/dev/null
