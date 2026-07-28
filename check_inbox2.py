import urllib.request, json, base64, hmac, hashlib, time, os

key_path = os.path.expanduser('~/.hermes/secmod/.session_key')
with open(key_path, 'rb') as f:
    secret = f.read()

exp = int(time.time()) + 24 * 3600
payload = json.dumps({'u': 'kato', 'exp': exp})
payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
sig = hmac.new(secret, payload_b64.encode(), hashlib.sha256).hexdigest()
token = f'{payload_b64}.{sig}'

base = 'http://127.0.0.1:9000'

def fetch(path):
    req = urllib.request.Request(f'{base}{path}')
    req.add_header('Cookie', f'hub_session={token}')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

# Get 50 inbox messages and scan for reservation keywords
data = fetch('/api/gmail/inbox?limit=50')
msgs = data.get('messages', [])
print(f"Total inbox messages returned: {len(msgs)}")

keywords = ['owner.com', 'reservation', 'booking', 'boardwalk', 'booked at', 'table for']
hits = []
for m in msgs:
    combined = f"{m.get('subject','')} {m.get('snippet','')} {m.get('from','')}".lower()
    matched = [kw for kw in keywords if kw.lower() in combined]
    if matched:
        hits.append((m, matched))
        print(f"\nHIT: {matched}")
        print(f"  From: {m.get('from','?')}")
        print(f"  Subject: {m.get('subject','?')}")
        print(f"  Date: {m.get('date','?')}")
        print(f"  Snippet: {m.get('snippet','?')[:200]}")

if not hits:
    print("\nNo reservation-related emails found in the last 50 inbox messages.")
