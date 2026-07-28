#!/usr/bin/env python3
"""Quick script to list Retell agents and make a call to Lana."""
import json, ssl, http.client, os, sys, time
from pathlib import Path

REX_DIR = Path.home() / "Desktop" / "REX"
env_text = (REX_DIR / ".env").read_text()
API_KEY = ""
for line in env_text.splitlines():
    if line.startswith("RETELL_API_KEY="):
        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

if not API_KEY:
    print("ERROR: No RETELL_API_KEY found")
    sys.exit(1)

CTX = ssl.create_default_context()

def retell_get(path):
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=CTX)
    conn.request("GET", path, headers={"Authorization": f"Bearer {API_KEY}"})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    if resp.status >= 400:
        return {"error": f"HTTP {resp.status}: {body[:300]}"}
    return json.loads(body)

# List all agents - try multiple paths
for path in ["/list-agents", "/v2/list-agents", "/agents", "/v2/agents"]:
    print(f"=== Trying: {path} ===")
    agents = retell_get(path)
    if isinstance(agents, list):
        for a in agents:
            aid = a.get("agent_id", "?")
            name = a.get("agent_name", "?")
            lang = a.get("language", "?")
            voice = a.get("voice_id", "?")
            print(f"  {aid} | {name} | lang={lang} | voice={voice}")
        print(f"\nTotal agents: {len(agents)}")
        break
    else:
        err = agents.get("error", str(agents))
        print(f"  Failed: {err[:100]}")
else:
    print("All paths failed.")
    sys.exit(1)
