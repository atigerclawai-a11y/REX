#!/usr/bin/env python3
"""Fetch call with different Retell API paths."""
import json, ssl, http.client
from pathlib import Path

env_text = (Path.home() / "Desktop" / "REX" / ".env").read_text()
api_key = ""
for line in env_text.splitlines():
    if line.startswith("RETELL_API_KEY="):
        api_key = line.split("=", 1)[1].strip()
        api_key = api_key.strip('"').strip("'")
        break

ctx = ssl.create_default_context()
call_id = "call_e5f66656875b458ef54b2175bf8"

paths_to_try = [
    f"/v2/phone-call/{call_id}",
    f"/v2/phone_call/{call_id}",
    f"/v2/call/{call_id}",
    f"/v2/phone-calls/{call_id}",
    f"/phone-call/{call_id}",
    f"/phone_call/{call_id}",
    f"/call/{call_id}",
    f"/phone-calls/{call_id}",
    f"/get-phone-call/{call_id}",
    f"/v2/get-phone-call/{call_id}",
]

for path in paths_to_try:
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
    conn.request("GET", path, headers={"Authorization": f"Bearer {api_key}"})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    
    if resp.status < 400:
        data = json.loads(body)
        print(f"SUCCESS: {path} -> {resp.status}")
        print(f"  call_status={data.get('call_status','?')}")
        print(f"  duration_ms={data.get('duration_ms','?')}")
        t = data.get("transcript", "NONE")
        print(f"  transcript={t[:500]}")
        out = Path.home() / "Desktop" / "REX" / f"call_lana_fetched_{call_id}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"  Saved: {out}")
        break
    elif resp.status == 404:
        print(f"404: {path}")
    else:
        print(f"{resp.status}: {path} -> {body[:150]}")
