#!/usr/bin/env python3
"""Cron job: Call BBG Lana via Retell API for competitive analysis."""
import requests, json, time, sys
from datetime import datetime, timezone

import os
API_KEY = os.environ.get("RETELL_API_KEY", "")
if not API_KEY:
    # Fallback: read from ~/Desktop/REX/.env (same path as other Lana scripts)
    env_path = os.path.expanduser("~/Desktop/REX/.env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("RETELL_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except FileNotFoundError:
        pass
if not API_KEY:
    print("RETELL_API_KEY not found in env or ~/Desktop/REX/.env — exiting silently")
    sys.exit(42)
BASE = "https://api.retellai.com/v2"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# Create the call — Private Event scenario (rotated from prior Large Party)
payload = {
    "agent_id": "agent_01dd3c97a1d84bfc030007e641",
    "from_number": "+164****3781",
    "to_number": "+19292056408",
    "metadata": {"scenario": "lana_study_private_event"},
    "override_agent_id": "agent_01dd3c97a1d84bfc030007e641"
}

print(f">>> [{NOW}] Creating phone call to BBG (Private Event scenario)...")
resp = requests.post(
    f"{BASE}/create-phone-call",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json=payload,
    timeout=30
)

print(f"Status: {resp.status_code}")
if resp.status_code in (401, 403, 404):
    print("API BROKEN — will report SILENT")
    sys.exit(42)  # Special code for SILENT

data = resp.json()
call_id = data.get("call_id", "unknown")
print(f"Call ID: {call_id}")
print(f"Call status: {data.get('call_status', 'unknown')}")

# Save call info
with open("/Users/mainsobhelper/Desktop/REX/call_lana_latest.json", "w") as f:
    json.dump(data, f, indent=2)
with open("/Users/mainsobhelper/Desktop/REX/call_lana_latest_id.txt", "w") as f:
    f.write(call_id)

# Check if connected
call_status = data.get("call_status", "")
if call_status in ("not_connected", "dial_failed"):
    print(f"\nCall failed to connect: {call_status}")
    # Save minimal record
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
    call_successful = call_data.get("call_successful", False)
    sentiment = call_data.get("user_sentiment", "Unknown")
    disconnection = call_data.get("disconnection_reason", "unknown")
    transcript = call_data.get("transcript", "")
    
    print(f"\n--- CALL SUMMARY ---")
    print(f"Duration: {duration_ms/1000:.1f}s")
    print(f"Successful: {call_successful}")
    print(f"Sentiment: {sentiment}")
    print(f"Disconnection: {disconnection}")
    
    # Print full transcript for analysis
    print(f"\n--- FULL CALL DATA (first 10K chars) ---")
    print(json.dumps(call_data, indent=2)[:10000])
else:
    print(f"Failed to fetch: {resp2.text[:500]}")
    sys.exit(1)
