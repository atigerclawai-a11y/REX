#!/bin/bash
# CC_upgrade_victoria.command
# Upgrades the canonical Victoria-GOJ agent (agent_26e3…):
#   • bilingual (Russian + English)  • natural, non-robotic voice settings
#   • rewritten warm prompt with a "leave a message" path
# Voice notes are already captured (Retell records every call; the webhook stores
# recording_url + transcript). SMS is a separate build — not in this script.
#
# Run this yourself — the harness blocks an agent from writing the live voice agent.
# Backs up the current agent + LLM config first; prints how to revert.
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
LOG=~/Desktop/REX/logs/CC_upgrade_victoria_$TS.log
exec > >(tee "$LOG") 2>&1

# ── Voice choice ──────────────────────────────────────────────────────────────
# Default keeps the familiar Elena voice (only the robotic SETTINGS change).
# To use a different voice, set VOICE_ID (and VOICE_MODEL for ElevenLabs). Preview
# voices first: https://docs.retellai.com  or the preview_audio_url from list-voices.
#   Natural multilingual options:  11labs-Lily (American), 11labs-Dorothy (British),
#   cartesia-Cleo (American).  For 11labs set VOICE_MODEL="eleven_multilingual_v2".
# INTERIM: cartesia-Elena (the only "Elena" in Retell's catalog) + de-robotify settings.
# Kato wants the ElevenLabs "Elena" — that lives in his EL account and must be IMPORTED into
# Retell first (needs the EL voice_id). Once imported, set VOICE_ID to the new custom voice id
# and VOICE_MODEL="eleven_multilingual_v2".
VOICE_ID="cartesia-Elena"
VOICE_MODEL=""

AGENT="agent_26e3746829ae6e174f4a012bbd"
LLM="llm_747a0abde4ba8a89ec1759cd3944"
KEY=$(grep -oE 'key_[a-f0-9]+' ~/Desktop/REX/goj_victoria_caller.py | head -1)
BK=~/Desktop/REX/CC_code_backups/victoria_$TS
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

print("1) Backing up current config ...")
cur_agent = req("GET", f"/get-agent/{agent}")
cur_llm   = req("GET", f"/get-retell-llm/{llm}")
open(f"{bk}/agent_before.json","w").write(json.dumps(cur_agent, indent=2, ensure_ascii=False))
open(f"{bk}/llm_before.json","w").write(json.dumps(cur_llm, indent=2, ensure_ascii=False))
print(f"   saved → {bk}/")

print("2) Updating agent (bilingual + natural voice settings) ...")
agent_patch = {
    "voice_id": voice_id,
    "language": "multi",
    "voice_temperature": 0.85,
    "voice_speed": 0.95,
    "responsiveness": 0.85,
    "interruption_sensitivity": 0.4,
    "enable_backchannel": True,
    "backchannel_frequency": 0.6,
    "normalize_for_speech": True,
    "ambient_sound": "coffee-shop",   # background sound (like Masha) so she feels human
}
if voice_model:
    agent_patch["voice_model"] = voice_model
req("PATCH", f"/update-agent/{agent}", agent_patch)

print("3) Updating prompt + greeting (warm, bilingual, message-taking) ...")
prompt = open("/Users/mainsobhelper/Desktop/REX/CC_victoria_prompt_ru_en.txt").read()
begin  = open("/Users/mainsobhelper/Desktop/REX/CC_victoria_begin_message.txt").read().strip()
req("PATCH", f"/update-retell-llm/{llm}", {"general_prompt": prompt, "begin_message": begin})

print("4) Verifying ...")
a = req("GET", f"/get-agent/{agent}")
print(f"   language={a.get('language')} voice={a.get('voice_id')} temp={a.get('voice_temperature')} "
      f"speed={a.get('voice_speed')} backchannel={a.get('enable_backchannel')}")
ok = a.get("language")=="multi" and a.get("enable_backchannel") and a.get("voice_temperature")==0.85
print("✅ Victoria upgraded — bilingual + natural + message-taking." if ok else "❌ verify the values above")
print(f"Revert: re-PATCH from {bk}/agent_before.json and {bk}/llm_before.json")
PY
