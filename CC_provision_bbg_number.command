#!/bin/bash
# CC_provision_bbg_number.command  (Runbook Step 4, Option A)
# Buys a new Retell phone number (Brooklyn area code) and binds it to Masha-BBG.
# This is a PURCHASE (~$2/mo) on your Retell account — run it yourself.
# Use this to get Masha a live BBG line fast; later forward/port (929) 205-6408 to it.
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
LOG=~/Desktop/REX/logs/CC_provision_bbg_number_$TS.log
exec > >(tee "$LOG") 2>&1

MASHA="agent_305ba9fdc34276c523766cd096"
AREA_CODE=929                 # Brooklyn; change to 718 or 646 if 929 has no stock
KEY=$(grep -oE 'key_[a-f0-9]+' ~/Desktop/REX/goj_victoria_caller.py | head -1)

echo "Provisioning a new Retell number (area code $AREA_CODE) bound to Masha ..."
/Users/mainsobhelper/Desktop/REX/.venv/bin/python3 - "$KEY" "$MASHA" "$AREA_CODE" <<'PY'
import json, sys, urllib.request, urllib.error
key, masha, area = sys.argv[1:4]
API="https://api.retellai.com"
def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=40))
try:
    res = req("POST", "/create-phone-number", {
        "area_code": int(area),
        "inbound_agent_id": masha,
        "outbound_agent_id": masha,
        "nickname": "BBG - Masha",
    })
    num = res.get("phone_number") or res.get("phone_number_pretty")
    print(f"✅ Provisioned {num} → bound to Masha (inbound+outbound).")
    print("   Next: forward or port (929) 205-6408 to this number so the public BBG line reaches Masha.")
except urllib.error.HTTPError as e:
    print("❌ Provision failed:", e.code, e.read().decode()[:300])
    print("   If 'no numbers available' for 929, edit AREA_CODE to 718 or 646 and re-run.")
PY
