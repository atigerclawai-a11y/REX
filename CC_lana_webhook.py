#!/usr/bin/env python3
"""Check webhook URLs on Scout agents and look for our call data."""
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

# Check webhook URL on our agent
agent_id = "agent_2e730566c0ce88c1688916a635"  # Scout-Hours-Night
conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=ctx)
conn.request("GET", "/get-agent/" + agent_id, headers={"Authorization": "Bearer " + api_key})
resp = conn.getresponse()
body = resp.read().decode("utf-8")
conn.close()

if resp.status < 400:
    data = json.loads(body)
    wh = data.get("webhook_url", "NONE")
    name = data.get("agent_name", "?")
    print("Agent: " + name)
    print("Webhook URL: " + wh)
    print("Language: " + str(data.get("language", "?")))
else:
    print("Error: " + str(resp.status) + " " + body[:200])

# Also check if call data exists in victoria_call_log
print("\n--- Checking call logs ---")
import sqlite3
db_path = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
try:
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT * FROM victoria_call_log WHERE retell_call_id LIKE '%e5f6665%' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(dict(r))
    if not rows:
        print("No matching rows in victoria_call_log")
    db.close()
except Exception as e:
    print("DB error: " + str(e))
