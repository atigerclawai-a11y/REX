#!/bin/bash
# CC_upgrade_masha.command
# Wires Masha-BBG (agent_305ba9…) into a real BBG receptionist:
#   • full BBG brain (hours, happy hour, menu, policies, reservations) from the KB
#   • bilingual (English + Russian)  • natural, non-robotic voice settings
#   • model gpt-5.4-nano → gpt-4.1   • reservation/message collection in the prompt
# (BBG is NOT GOJ — no PHI/HIPAA constraints. Phone porting of (929) 205-6408 from
#  GoHighLevel to Retell is a SEPARATE telephony task, not in this script.)
#
# Run this yourself — the harness blocks an agent from writing the live voice agent.
# Backs up the current agent + LLM first; prints how to revert.
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
LOG=~/Desktop/REX/logs/CC_upgrade_masha_$TS.log
exec > >(tee "$LOG") 2>&1

# Voice: keep retell-Cimo (de-robotified) for now. To use a specific bilingual voice
# (e.g. an imported ElevenLabs voice), set VOICE_ID + VOICE_MODEL="eleven_multilingual_v2".
VOICE_ID="retell-Cimo"
VOICE_MODEL=""

AGENT="agent_305ba9fdc34276c523766cd096"
LLM="llm_13da395e8bab02945fe497bbd1f7"
KEY=$(grep -oE 'key_[a-f0-9]+' ~/Desktop/REX/goj_victoria_caller.py | head -1)
BK=~/Desktop/REX/CC_code_backups/masha_$TS
mkdir -p "$BK"

/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 - "$KEY" "$AGENT" "$LLM" "$VOICE_ID" "$VOICE_MODEL" "$BK" <<'PY'
import json, sys, urllib.request
key, agent, llm, voice_id, voice_model, bk = sys.argv[1:7]
API="https://api.retellai.com"
def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))

print("1) Backing up current Masha config ...")
open(f"{bk}/agent_before.json","w").write(json.dumps(req("GET", f"/get-agent/{agent}"), indent=2, ensure_ascii=False))
open(f"{bk}/llm_before.json","w").write(json.dumps(req("GET", f"/get-retell-llm/{llm}"), indent=2, ensure_ascii=False))
print(f"   saved → {bk}/")

print("2) Updating agent (bilingual + natural voice) ...")
patch = {"voice_id": voice_id, "language": "multi", "voice_temperature": 0.85,
         "voice_speed": 0.95, "responsiveness": 0.9, "interruption_sensitivity": 0.6,
         "enable_backchannel": True, "backchannel_frequency": 0.7, "normalize_for_speech": True}
if voice_model: patch["voice_model"] = voice_model
req("PATCH", f"/update-agent/{agent}", patch)

print("3) Updating brain (BBG prompt + greeting + model gpt-4.1) ...")
prompt = open("/Users/mainsobhelper/Desktop/REX/CC_masha_prompt_bbg.txt").read()
begin  = open("/Users/mainsobhelper/Desktop/REX/CC_masha_begin_message.txt").read().strip()
req("PATCH", f"/update-retell-llm/{llm}", {"general_prompt": prompt, "begin_message": begin, "model": "gpt-4.1"})

print("4) Verifying ...")
a = req("GET", f"/get-agent/{agent}"); l = req("GET", f"/get-retell-llm/{llm}")
print(f"   language={a.get('language')} voice={a.get('voice_id')} temp={a.get('voice_temperature')} "
      f"backchannel={a.get('enable_backchannel')} model={l.get('model')} prompt_len={len(l.get('general_prompt') or '')}")
ok = a.get("language")=="multi" and a.get("enable_backchannel") and l.get("model")=="gpt-4.1" and len(l.get('general_prompt') or '')>800
print("✅ Masha wired for BBG — bilingual, natural, full knowledge, reservation-taking." if ok else "❌ verify values above")
print(f"Revert: re-PATCH from {bk}/agent_before.json and {bk}/llm_before.json")
PY
