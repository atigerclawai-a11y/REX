#!/usr/bin/env python3
import requests, json

API_KEY = "key_48a2ed4781d093c125451e40ddb4"
BASE = "https://api.retellai.com/v2"

# List phone numbers
r = requests.get(f"{BASE}/list-phone-numbers", 
    headers={"Authorization": f"Bearer {API_KEY}"}, timeout=15)
print(f"Status: {r.status_code}")
data = r.json()
if isinstance(data, list):
    for item in data:
        pn = item.get("phone_number", "N/A")
        pp = item.get("phone_number_pretty", "")
        nick = item.get("nickname", "")
        print(f"  {pn} | {pp} | {nick}")
elif isinstance(data, dict):
    print(json.dumps(data, indent=2)[:2000])
else:
    print(data)
