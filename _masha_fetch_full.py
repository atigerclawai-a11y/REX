#!/usr/bin/env python3
"""Fetch full email bodies for reservation detection."""
import json, sys, urllib.request, urllib.error, os, ssl, base64

old_token_path = os.path.expanduser("~/Desktop/REX/GOJ_Backups/GOJ_2026-05-19_22-11/gmail/gmail_token.json")
with open(old_token_path) as f:
    old_token = json.load(f)

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

msg_ids = ["19f16197edff2ef2", "19f15f52b0a5729d", "19f1533a32fab634"]

for mid in msg_ids:
    msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?format=full"
    req2 = urllib.request.Request(msg_url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        resp2 = urllib.request.urlopen(req2, context=ctx, timeout=15)
        msg_data = json.loads(resp2.read())
        
        payload = msg_data.get("payload", {})
        parts = payload.get("parts", [])
        
        body_text = ""
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body_text += base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
        
        if not body_text:
            data = payload.get("body", {}).get("data", "")
            if data:
                body_text = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
        
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        
        print(f"=== MESSAGE {mid} ===")
        print(f"From: {headers.get('from', '?')}")
        print(f"Subject: {headers.get('subject', '?')}")
        print(f"Date: {headers.get('date', '?')}")
        print(f"Body: {body_text[:3000]}")
        print(f"=== END ===\n")
        
    except Exception as e:
        print(f"ERROR for {mid}: {e}")
