#!/usr/bin/env python3
"""List available phone numbers in Retell."""
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

# List phone numbers
for path in ["/list-phone-numbers", "/phone-numbers", "/v2/list-phone-numbers", "/v2/phone-numbers"]:
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
    conn.request("GET", path, headers={"Authorization": "Bearer " + api_key})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    
    if resp.status < 400:
        data = json.loads(body)
        print("SUCCESS: " + path)
        if isinstance(data, list):
            for p in data:
                print("  " + str(p.get("phone_number","?")) + " | " + str(p.get("status","?")) + " | agent=" + str(p.get("agent_id","?")))
        else:
            print(json.dumps(data, indent=2)[:1000])
        break
    elif resp.status == 404:
        print("404: " + path)
    else:
        print(str(resp.status) + ": " + path + " -> " + body[:150])
