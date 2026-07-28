#!/usr/bin/env python3
"""Fetch call data from Retell API - try v1 endpoints."""
import json, ssl, http.client, sys
from pathlib import Path

env_text = (Path.home() / "Desktop" / "REX" / ".env").read_text()
api_key = ""
for line in env_text.splitlines():
    if "RETELL_API_KEY" in line:
        api_key = line.split("=", 1)[1].strip()
        api_key = api_key.strip('"').strip("'")
        break

ctx = ssl.create_default_context()
call_id = "call_e5f66656875b458ef54b2175bf8"

# v1 style paths (same format as /list-agents, /get-agent/{id})
paths = [
    "/get-phone-call/" + call_id,
    "/get-call/" + call_id,
    "/phone-call/" + call_id,
    "/call/" + call_id,
]

for path in paths:
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
    conn.request("GET", path, headers={"Authorization": "Bearer " + api_key})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    
    if resp.status < 400:
        data = json.loads(body)
        print("SUCCESS: " + path)
        print("  call_status=" + str(data.get("call_status","?")))
        print("  duration_ms=" + str(data.get("duration_ms","?")))
        t = data.get("transcript", "NONE")
        print("  transcript=" + t[:600])
        out = Path.home() / "Desktop" / "REX" / ("call_lana_fetched_" + call_id + ".json")
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print("  Saved: " + str(out))
        sys.exit(0)
    elif resp.status == 404:
        print("404: " + path)
    else:
        print(str(resp.status) + ": " + path + " -> " + body[:150])
