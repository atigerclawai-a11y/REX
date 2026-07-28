#!/usr/bin/env python3
"""Create a valid Hub session token and call the Gmail API."""
import hmac, hashlib, base64, json, time, urllib.request, ssl

# Read session secret
with open("/Users/mainsobhelper/.hermes/secmod/.session_key", "rb") as f:
    secret = f.read()

# Create token for "kato"
exp = int(time.time()) + 86400  # 24h
payload = base64.urlsafe_b64encode(json.dumps({"u": "kato", "exp": exp}).encode()).decode()
sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
token = f"{payload}.{sig}"

# Call the Hub Gmail API with the session cookie
import urllib.request
req = urllib.request.Request("http://127.0.0.1:9000/api/gmail/inbox?limit=10")
req.add_header("Cookie", f"hub_session={token}")
ctx = ssl.create_default_context()
try:
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    data = json.loads(resp.read())
    print(json.dumps(data))
except urllib.error.HTTPError as e:
    body = e.read().decode() if e.fp else ""
    print(json.dumps({"error": f"HTTP {e.code}", "body": body[:500]}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
