#!/usr/bin/env python3
"""Fetch full Gmail messages for owner.com reservations found in current inbox."""
import json, sys, urllib.request, urllib.error, urllib.parse, os, ssl, base64

# Load old token that has Gmail scopes
old_token_path = os.path.expanduser("~/Desktop/REX/GOJ_Backups/GOJ_2026-05-19_22-11/gmail/gmail_token.json")
with open(old_token_path) as f:
    old_token = json.load(f)

# Refresh the token
refresh_data = urllib.parse.urlencode({
    "client_id": old_token["client_id"],
    "client_secret": old_token["client_secret"],
    "refresh_token": old_token["refresh_token"],
    "grant_type": "refresh_token",
}).encode()

ctx = ssl.create_default_context()
req = urllib.request.Request("https://oauth2.googleapis.com/token", data=refresh_data)
resp = urllib.request.urlopen(req, context=ctx, timeout=15)
new_token = json.loads(resp.read())
access_token = new_token["access_token"]

# Message IDs from current inbox + the older ones referenced
msg_ids = [
    "19efa599506bfa55",  # Jun 18 (in inbox)
    "19efa5945dffe205",  # Jun 19 (in inbox)
    "19efa5910efe4cc4",  # Jun 20 (in inbox)
    "19efa58bdf12a5be",  # Jun 21 (in inbox)
    "19efa588c9d78f6c",  # Jun 22 (older, try anyway)
    "19efa581c6394bcd",  # Jun 24 (older, try anyway)
]

results = []
for mid in msg_ids:
    try:
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?format=full"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        msg = json.loads(resp.read())
        
        # Extract headers
        headers = {}
        for h in msg.get("payload", {}).get("headers", []):
            headers[h["name"].lower()] = h["value"]
        
        # Get body text
        payload = msg.get("payload", {})
        
        def extract_body(part, parts_list=None):
            texts = []
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    try:
                        texts.append(base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace"))
                    except:
                        texts.append(base64.urlsafe_b64decode(data).decode("utf-8", errors="replace"))
            for p in part.get("parts", []):
                texts.extend(extract_body(p))
            return texts
        
        body_text = "\n".join(extract_body(payload))
        
        results.append({
            "id": mid,
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "date": headers.get("date", ""),
            "body": body_text[:3000],
        })
    except urllib.error.HTTPError as e:
        results.append({"id": mid, "error": f"HTTP {e.code}: {e.reason}"})
    except Exception as e:
        results.append({"id": mid, "error": str(e)})

print(json.dumps(results, indent=2))
