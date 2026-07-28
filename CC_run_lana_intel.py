#!/usr/bin/env python3
"""Masha BBG competitive intelligence — single-call runner with proper error handling."""
import json, ssl, http.client, sys, time
from pathlib import Path
from datetime import datetime, timezone

REX_DIR = Path("/Users/mainsobhelper/Desktop/REX")

# ── Read API key from .env ──
env_text = (REX_DIR / ".env").read_text()
API_KEY = ""
for line in env_text.splitlines():
    if line.startswith("RETELL_API_KEY="):
        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

if not API_KEY:
    print("ERROR: No API key in .env")
    sys.exit(1)

FROM_NUMBER = "+164****3781"
TO_NUMBER = "+19292056408"  # BBG secondary — primary mailbox confirmed full
AGENT_ID = "agent_01dd3c97a1d84bfc030007e641"  # Scout-Reservations (English)
SCENARIO = "lana_study_large_party"

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
print(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

payload = {
    "from_number": FROM_NUMBER,
    "to_number": TO_NUMBER,
    "override_agent_id": AGENT_ID,
    "ignore_e164_validation": True,
    "metadata": {"scenario": SCENARIO, "target": "lana_bbg", "study": "competitive_intelligence"}
}

result = retell_post("/v2/create-phone-call", payload)

if "error" in result:
    status_code = result["error"]
    print(f"❌ API Error: {status_code}")
    print(f"   Body: {result.get('body', '')[:300]}")
    if any(code in status_code for code in ["401", "403", "404"]):
        print("🔇 Auth/not-found error — SILENT per spec")
        sys.exit(2)
    sys.exit(1)

call_id = result.get("call_id")
call_status = result.get("call_status", "unknown")
print(f"✅ Call initiated: {call_id} (status: {call_status})")

# ── Step 2: Wait 3 minutes ──
print("⏳ Waiting 180s for call to complete...")
time.sleep(180)

# ── Step 3: Fetch call details (correct endpoint /v2/get-call/) ──
print(f"📋 Fetching call {call_id}...")
call_data = retell_get(f"/v2/get-call/{call_id}")

if "error" in call_data:
    print(f"❌ Fetch error: {call_data}")
    sys.exit(1)

# ── Step 4: Print key details ──
duration_ms = call_data.get("duration_ms", 0)
duration_sec = duration_ms / 1000.0
transcript = call_data.get("transcript", "NO TRANSCRIPT")
call_status_final = call_data.get("call_status", "unknown")
disconnect_reason = call_data.get("disconnection_reason", "unknown")

print(f"\n{'='*60}")
print(f"CALL RESULT: {call_id}")
print(f"Status: {call_status_final} (disconnect: {disconnect_reason})")
print(f"Duration: {duration_sec:.1f}s")
print(f"Agent: {call_data.get('agent_name', '?')}")
print(f"Successful: {call_data.get('call_successful', '?')}")
print(f"Sentiment: {call_data.get('user_sentiment', '?')}")
print(f"{'='*60}")
print(f"\n📝 TRANSCRIPT:\n{transcript[:3000]}")
if len(transcript) > 3000:
    print(f"\n... [truncated, full length: {len(transcript)} chars]")

# Save raw to file
out_file = REX_DIR / f"lana_call_{call_id}.json"
out_file.write_text(json.dumps(call_data, indent=2))
print(f"\n💾 Full data saved to {out_file}")
