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

# Check inbox with different queries
for q in [None, 'owner.com', 'reservation', 'booking', 'boardwalk', 'table for']:
    path = '/api/gmail/inbox?limit=10'
    if q:
        path = f'/api/gmail/inbox?limit=10&query={urllib.request.quote(q)}'
    try:
        data = fetch(path)
        msgs = data.get('messages', [])
        print(f"\n=== Query: {q or '(none)'} — {len(msgs)} messages ===")
        for m in msgs:
            print(f"  {m.get('from','?')[:60]} | {m.get('subject','?')[:80]}")
            print(f"    {m.get('snippet','')[:120]}")
    except Exception as e:
        print(f"\n=== Query: {q} — ERROR: {e} ===")
