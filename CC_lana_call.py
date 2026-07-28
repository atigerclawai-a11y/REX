#!/usr/bin/env python3
"""Call Lana at BBG using Retell API — New Customer/Hours scenario."""
import json, ssl, http.client, sys, time
from datetime import datetime, timezone
from pathlib import Path

REX_DIR = Path.home() / "Desktop" / "REX"

# ── Read API key from .env ──
env_text = (Path.home() / "Desktop" / "REX" / ".env").read_text()
API_KEY = ""
for line in env_text.splitlines():
    if line.startswith("RETELL_API_KEY="):
        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

FROM_NUMBER = "+164****3781"
AGENT_ID = "agent_2e730566c0ce88c1688916a635"  # Scout-Hours-Night
TO_NUMBER = "+192****6408"  # BBG secondary number
SCENARIO = "new_customer_hours"

if not API_KEY:
    print("ERROR: No API key")
    sys.exit(1)

CTX = ssl.create_default_context()

def retell_post(path, body):
    data = json.dumps(body).encode("utf-8")
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=CTX)
    conn.request("POST", path, body=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    })
    resp = conn.getresponse()
    resp_body = resp.read().decode("utf-8")
    conn.close()
    if resp.status >= 400:
        return {"error": f"HTTP {resp.status}", "body": resp_body[:500]}
    return json.loads(resp_body)

def retell_get(path):
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=CTX)
    conn.request("GET", path, headers={"Authorization": f"Bearer {API_KEY}"})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    if resp.status >= 400:
        return {"error": f"HTTP {resp.status}", "body": body[:500]}
    return json.loads(body)

# ── Step 1: Make the call ──
print(f"📞 Calling {TO_NUMBER} with agent {AGENT_ID} ({SCENARIO})...")
payload = {
    "from_number": FROM_NUMBER,
    "to_number": TO_NUMBER,
    "override_agent_id": AGENT_ID,
    "ignore_e164_validation": True,
    "metadata": {"scenario": SCENARIO, "target": "lana_bbg"}
}

result = retell_post("/v2/create-phone-call", payload)

if "error" in result:
    status_code = result["error"]
    print(f"❌ API Error: {status_code}")
    print(f"   Body: {result.get('body', '')[:300]}")
    # Check if 401/403/404 -> respond SILENT
    if any(code in status_code for code in ["401", "403", "404"]):
        print("🔇 Auth/not-found error — respond SILENT")
        sys.exit(2)
    sys.exit(1)

call_id = result.get("call_id")
call_status = result.get("call_status", "unknown")
print(f"✅ Call initiated: {call_id} (status: {call_status})")

# ── Step 2: Wait 3 minutes ──
print("⏳ Waiting 180s for call to complete...")
time.sleep(180)

# ── Step 3: Fetch call details ──
print(f"📋 Fetching call {call_id}...")
call_data = retell_get(f"/v2/get-phone-call/{call_id}")

if "error" in call_data:
    print(f"❌ Fetch error: {call_data}")
    sys.exit(1)

# ── Step 4: Save and print transcript ──
duration_ms = call_data.get("duration_ms", 0)
duration_sec = duration_ms / 1000.0
transcript = call_data.get("transcript", "NO TRANSCRIPT")
call_status_final = call_data.get("call_status", "unknown")

print(f"\n{'='*60}")
print(f"CALL RESULT: {call_id}")
print(f"Status: {call_status_final}")
print(f"Duration: {duration_sec:.1f}s")
print(f"Agent: {call_data.get('agent_name', '?')} ({call_data.get('agent_id', '?')})")
print(f"Disconnection: {call_data.get('disconnection_reason', 'N/A')}")
print(f"\nTRANSCRIPT:")
print(transcript)
print(f"{'='*60}")

# Save detailed call data
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = REX_DIR / f"call_lana_{SCENARIO}_{timestamp}.json"
out_path.write_text(json.dumps(call_data, indent=2, ensure_ascii=False))
print(f"\n💾 Saved: {out_path}")

# Save summary for analysis
summary = {
    "call_id": call_id,
    "scenario": SCENARIO,
    "duration_sec": duration_sec,
    "status": call_status_final,
    "to_number": TO_NUMBER,
    "from_number": FROM_NUMBER,
    "agent_id": AGENT_ID,
    "timestamp": timestamp,
    "transcript": transcript,
    "transcript_object": call_data.get("transcript_object", []),
    "disconnection_reason": call_data.get("disconnection_reason", "unknown"),
    "call_analysis": call_data.get("call_analysis", {}),
}
summary_path = REX_DIR / "call_lana_latest.json"
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
print(f"💾 Summary: {summary_path}")
