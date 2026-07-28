#!/bin/bash
# CC_bind_masha_number.command  (Runbook Step 4)
# Binds the number you ALREADY own — +1-877-768-2887 — to Masha-BBG, and verifies.
# PREREQUISITE: import +18777682887 into Retell first (dashboard → Import/Connect Number,
# using your Twilio SID + Auth Token). This script then sets it as Masha's inbound+outbound
# agent. If the number isn't imported yet, it tells you.
# Run it yourself — the harness blocks an agent from changing live phone routing.
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
LOG=~/Desktop/REX/logs/CC_bind_masha_number_$TS.log
exec > >(tee "$LOG") 2>&1

NUM="+18777682887"
MASHA="agent_305ba9fdc34276c523766cd096"
KEY=$(grep -oE 'key_[a-f0-9]+' ~/Desktop/REX/goj_victoria_caller.py | head -1)

/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 - "$KEY" "$NUM" "$MASHA" <<'PY'
import json, sys, urllib.request, urllib.error
key, num, masha = sys.argv[1:4]
API="https://api.retellai.com"
def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))

# Is the number imported into Retell yet?
try:
    cur = req("GET", f"/get-phone-number/{num}")
except urllib.error.HTTPError as e:
    if e.code == 404:
        print(f"❌ {num} is NOT imported into Retell yet.")
        print("   Do this first: app.retellai.com → Phone Numbers → Import/Connect Number")
        print("   → enter your Twilio Account SID + Auth Token + +18777682887, then re-run this.")
        sys.exit(1)
    raise
print(f"1) Found {num} in Retell (current inbound={cur.get('inbound_agent_id')}, outbound={cur.get('outbound_agent_id')}).")

print("2) Binding inbound + outbound → Masha ...")
req("PATCH", f"/update-phone-number/{num}",
    {"inbound_agent_id": masha, "outbound_agent_id": masha, "nickname": "BBG - Masha"})

v = req("GET", f"/get-phone-number/{num}")
ok = v.get("inbound_agent_id")==masha and v.get("outbound_agent_id")==masha
print(f"3) inbound={v.get('inbound_agent_id')} outbound={v.get('outbound_agent_id')}")
print("✅ Masha bound to +1-877-768-2887. Call it to test the BBG receptionist." if ok else "❌ bind not applied")
print("   (Remember: also run CC_fix_victoria_routing so the GOJ number stops borrowing to v2.)")
PY
