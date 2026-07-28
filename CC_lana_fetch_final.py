#!/usr/bin/env python3
"""Fetch call data using correct endpoint /v2/get-call/{call_id}."""
import json, ssl, http.client
from pathlib import Path

env_text = (Path.home() / "Desktop" / "REX" / ".env").read_text()
api_key = ""
for line in env_text.splitlines():
    if "RETELL_API_KEY" in line:
        api_key = line.split("=", 1)[1].strip()
        api_key = api_key.strip('"').strip("'")
        break

ctx = ssl.create_default_context()
call_id = "call_4db1fac94da8e82beccc83368f1"
path = "/v2/get-call/" + call_id

conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
conn.request("GET", path, headers={"Authorization": "Bearer " + api_key})
resp = conn.getresponse()
body = resp.read().decode("utf-8")
conn.close()

print("Status: " + str(resp.status))
if resp.status < 400:
    data = json.loads(body)
    print("call_status=" + str(data.get("call_status","?")))
    print("duration_ms=" + str(data.get("duration_ms","?")))
    print("disconnection=" + str(data.get("disconnection_reason","?")))
    transcript = data.get("transcript", "NONE")
    print("\nTRANSCRIPT:")
    print(transcript)
    
    out = Path.home() / "Desktop" / "REX" / ("call_lana_result_" + call_id + ".json")
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print("\nSaved: " + str(out))
else:
    print("Error body: " + body[:500])
