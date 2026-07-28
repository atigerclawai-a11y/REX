#!/usr/bin/env python3
"""Full reservation watcher: fetch inbox, scan for booking emails, save results."""
import json, urllib.request, urllib.parse, urllib.error, ssl, os, re
from datetime import datetime

# ── Refresh Token ────────────────────────────────────────────
token_path = os.path.expanduser("~/.rex_google_token.json")
d = json.load(open(token_path))

refresh_data = urllib.parse.urlencode({
    "client_id": d["client_id"],
    "client_secret": d["client_secret"],
    "refresh_token": d["refresh_token"],
    "grant_type": "refresh_token",
}).encode()

ctx = ssl.create_default_context()
req = urllib.request.Request("https://oauth2.googleapis.com/token", data=refresh_data)
resp = urllib.request.urlopen(req, context=ctx, timeout=15)
nt = json.loads(resp.read())
access_token = nt["access_token"]

# ── Fetch Inbox ──────────────────────────────────────────────
list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10&labelIds=INBOX"
req2 = urllib.request.Request(list_url, headers={"Authorization": f"Bearer {access_token}"})
resp2 = urllib.request.urlopen(req2, context=ctx, timeout=15)
messages_data = json.loads(resp2.read())

inbox = []
for msg_meta in messages_data.get("messages", []):
    try:
        msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_meta['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        req3 = urllib.request.Request(msg_url, headers={"Authorization": f"Bearer {access_token}"})
        resp3 = urllib.request.urlopen(req3, context=ctx, timeout=15)
        msg_data = json.loads(resp3.read())
        headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
        inbox.append({
            "id": msg_data["id"],
            "threadId": msg_data.get("threadId", ""),
            "from": headers.get("from", "(unknown)"),
            "subject": headers.get("subject", "(no subject)"),
            "date": headers.get("date", ""),
            "snippet": msg_data.get("snippet", ""),
        })
    except Exception as e:
        inbox.append({"id": msg_meta["id"], "error": str(e)})

# ── Scan for Reservation Keywords ───────────────────────────
keywords = [
    "owner.com", "new reservation", "booking confirmed", "new booking",
    "reservation request", "table for", "booked at boardwalk"
]

reservations = []
for msg in inbox:
    combined = f"{msg.get('subject','')} {msg.get('snippet','')} {msg.get('from','')}".lower()
    for kw in keywords:
        if kw.lower() in combined:
            reservations.append(msg)
            break

# ── Save full result ────────────────────────────────────────
result = {
    "ok": True,
    "total_inbox": len(inbox),
    "reservations_found": len(reservations),
    "all_messages": inbox,
    "reservations": reservations,
    "checked_at": datetime.now().isoformat()
}

out_path = os.path.expanduser("~/Desktop/REX/_masha_inbox_result.json")
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"Total inbox: {len(inbox)}")
print(f"Reservations found: {len(reservations)}")
print()
for i, msg in enumerate(inbox):
    marker = "🔴 RESERVATION" if msg in reservations else "  "
    print(f"[{i+1}] {marker} {msg['subject'][:90]}")
    print(f"    From: {msg['from'][:70]}")
    print(f"    Date: {msg.get('date','?')[:40]}")
    print(f"    {msg['snippet'][:120]}")
    print()

print(f"Result saved to: {out_path}")
