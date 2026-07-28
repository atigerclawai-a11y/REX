#!/usr/bin/env python3
"""Fetch full body of owner.com reservation emails via Gmail API."""
import json, urllib.request, urllib.parse, os, ssl, base64, sys

old_token_path = os.path.expanduser('~/Desktop/REX/GOJ_Backups/GOJ_2026-05-19_22-11/gmail/gmail_token.json')
with open(old_token_path) as f:
    old_token = json.load(f)

refresh_data = urllib.parse.urlencode({
    'client_id': old_token['client_id'],
    'client_secret': old_token['client_secret'],
    'refresh_token': old_token['refresh_token'],
    'grant_type': 'refresh_token',
}).encode()

ctx = ssl.create_default_context()
req = urllib.request.Request('https://oauth2.googleapis.com/token', data=refresh_data)
resp = urllib.request.urlopen(req, context=ctx, timeout=15)
new_token = json.loads(resp.read())
access_token = new_token['access_token']

def decode_body(payload):
    body = ''
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
    elif 'parts' in payload:
        for part in payload['parts']:
            body += decode_body(part)
    return body

results = []
for msg_id in sys.argv[1:]:
    msg_url = f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full'
    req2 = urllib.request.Request(msg_url, headers={'Authorization': f'Bearer {access_token}'})
    resp2 = urllib.request.urlopen(req2, context=ctx, timeout=15)
    msg_data = json.loads(resp2.read())
    headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
    body_text = decode_body(msg_data['payload'])
    results.append({
        'id': msg_id,
        'from': headers.get('from', ''),
        'subject': headers.get('subject', ''),
        'date': headers.get('date', ''),
        'body': body_text,
    })

print(json.dumps(results, indent=2))
