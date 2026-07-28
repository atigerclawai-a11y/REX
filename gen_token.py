import base64, json, hmac, hashlib, time, os

key_path = os.path.expanduser('~/.hermes/secmod/.session_key')
with open(key_path, 'rb') as f:
    secret = f.read()

exp = int(time.time()) + 24 * 3600
payload = json.dumps({'u': 'kato', 'exp': exp})
payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
sig = hmac.new(secret, payload_b64.encode(), hashlib.sha256).hexdigest()
token = f'{payload_b64}.{sig}'
print(token)
