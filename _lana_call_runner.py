#!/usr/bin/env python3
"""One-shot: Call BBG Lana — New Customer scenario. Secondary number."""
import requests, json, time, sys
from datetime import datetime, timezone

API_KEY = "key_48a2ed4781d093c125451e40ddb4"
BASE = "https://api.retellai.com/v2"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

FROM = "+19293685460"
TO = "+19292056408"  # secondary BBG number

payload = {
    "agent_id": "agent_2e730566c0ce88c1688916a635",
    "from_number": FROM,
    "to_number": TO,
    "metadata": {"scenario": "lana_study_new_customer"},
    "override_agent_id": "agent_2e730566c0ce88c1688916a635"
}

print(f">>> [{NOW}] Creating call to BBG (New Customer, secondary number)...")
print(f"    From: {FROM} → To: {TO}")

resp = requests.post(
    f"{BASE}/create-phone-call",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json=payload,
    timeout=30
)

print(f"Status: {resp.status_code}")
if resp.status_code in (401, 403, 404):
    print("API BROKEN — SILENT exit")
    sys.exit(42)
if resp.status_code != 201:
    print(f"Response: {resp.text[:1000]}")
    sys.exit(1)

data = resp.json()
call_id = data.get("call_id", "unknown")
print(f"Call ID: {call_id}")
print(f"Call status: {data.get('call_status', 'unknown')}")

with open("/Users/mainsobhelper/Desktop/REX/call_lana_latest.json", "w") as f:
    json.dump(data, f, indent=2)
with open("/Users/mainsobhelper/Desktop/REX/call_lana_latest_id.txt", "w") as f:
    f.write(call_id)

call_status = data.get("call_status", "")
if call_status in ("not_connected", "dial_failed"):
    print(f"\nCall failed: {call_status}")
    with open(f"/Users/mainsobhelper/Desktop/REX/lana_call_{call_id}.json", "w") as f:
        json.dump(data, f, indent=2)
    sys.exit(0)

print("\nWaiting 3 minutes for call to complete...")
time.sleep(180)

print("\n>>> Fetching call result...")
resp2 = requests.get(
    f"{BASE}/get-call/{call_id}",
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=30
)
print(f"Status: {resp2.status_code}")

if resp2.status_code == 200:
    call_data = resp2.json()
    with open(f"/Users/mainsobhelper/Desktop/REX/lana_call_{call_id}.json", "w") as f:
        json.dump(call_data, f, indent=2)
    
    duration_ms = call_data.get("duration_ms", 0)
    disconnection = call_data.get("disconnection_reason", "unknown")
    transcript = call_data.get("transcript", "")
    
    print(f"\n--- CALL SUMMARY ---")
    print(f"Duration: {duration_ms/1000:.1f}s")
    print(f"Disconnection: {disconnection}")
    print(f"\n--- TRANSCRIPT ---")
    print(transcript[:8000])
else:
    print(f"Failed: {resp2.text[:500]}")
    sys.exit(1)
