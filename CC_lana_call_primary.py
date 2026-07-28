#!/usr/bin/env python3
"""Call Lana on primary number and fetch result."""
import json, ssl, http.client, time, sys
from pathlib import Path

env_text = (Path.home() / "Desktop" / "REX" / ".env").read_text()
api_key = ""
for line in env_text.splitlines():
    if "RETELL_API_KEY" in line:
        api_key = line.split("=", 1)[1].strip()
        api_key = api_key.strip('"').strip("'")
        break

FROM_NUMBER = "+164****3781"
AGENT_ID = "agent_2e730566c0ce88c1688916a635"
TO_NUMBER = "+17185170300"  # BBG primary
SCENARIO = "new_customer_hours_v2"

ctx = ssl.create_default_context()

# Create call
payload = json.dumps({
    "from_number": FROM_NUMBER,
    "to_number": TO_NUMBER,
    "override_agent_id": AGENT_ID,
    "ignore_e164_validation": True,
    "metadata": {"scenario": SCENARIO, "target": "lana_bbg"}
}).encode("utf-8")

conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
conn.request("POST", "/v2/create-phone-call", body=payload, headers={
    "Content-Type": "application/json",
    "Authorization": "Bearer " + api_key
})
resp = conn.getresponse()
body = resp.read().decode("utf-8")
conn.close()

if resp.status >= 400:
    print("ERROR: HTTP " + str(resp.status) + " " + body[:300])
    if resp.status in [401, 403, 404]:
        print("SILENT")
        sys.exit(2)
    sys.exit(1)

result = json.loads(body)
call_id = result.get("call_id")
print("Call initiated: " + str(call_id) + " -> " + TO_NUMBER)
print("Status: " + str(result.get("call_status","?")))

# Wait 3 min
print("Waiting 180s...")
time.sleep(180)

# Fetch result
conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
conn.request("GET", "/v2/get-call/" + call_id, headers={"Authorization": "Bearer " + api_key})
resp = conn.getresponse()
body = resp.read().decode("utf-8")
conn.close()

data = json.loads(body)
print("\nResult:")
print("  call_status=" + str(data.get("call_status","?")))
print("  duration_ms=" + str(data.get("duration_ms","?")))
print("  disconnection=" + str(data.get("disconnection_reason","?")))
transcript = data.get("transcript", "NONE")
print("  transcript=" + transcript[:600])

out = Path.home() / "Desktop" / "REX" / ("call_lana_primary_" + call_id + ".json")
out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print("  Saved: " + str(out))
