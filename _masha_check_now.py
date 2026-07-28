#!/usr/bin/env python3
"""Masha reservation watcher — check Gmail inbox for new bookings."""
import json, urllib.request, urllib.error, os, ssl, datetime

# Use most recent token
old_token_path = os.path.expanduser('~/.hermes/credentials/gmail_token.json')
with open(old_token_path) as f:
    old_token = json.load(f)

refresh_data = urllib.parse.urlencode({
    'client_id': old_token['client_id'],
    'client_secret': old_token['client_secret'],
    'refresh_token': old_token['refresh_token'],
    'grant_type': 'refresh_token',
}).encode()

ctx = ssl.create_default_context()
try:
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=refresh_data)
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    new_token = json.loads(resp.read())
    access_token = new_token['access_token']
    print('TOKEN OK', file=__import__('sys').stderr)
except urllib.error.HTTPError as e:
    body = e.read().decode() if e.fp else ''
    print(json.dumps({'error': f'Token refresh failed: HTTP {e.code}', 'body': body[:500]}))
    __import__('sys').exit(1)
except Exception as e:
    print(json.dumps({'error': f'Token refresh failed: {e}'}))
    __import__('sys').exit(1)

# List inbox messages
try:
    list_url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10&labelIds=INBOX'
    req2 = urllib.request.Request(list_url, headers={'Authorization': f'Bearer {access_token}'})
    resp2 = urllib.request.urlopen(req2, context=ctx, timeout=15)
    messages_data = json.loads(resp2.read())
    
    inbox = []
    for msg_meta in messages_data.get('messages', []):
        msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_meta['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        req3 = urllib.request.Request(msg_url, headers={'Authorization': f'Bearer {access_token}'})
        resp3 = urllib.request.urlopen(req3, context=ctx, timeout=15)
        msg_data = json.loads(resp3.read())
        headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
        inbox.append({
            'id': msg_data['id'],
            'threadId': msg_data.get('threadId', ''),
            'from': headers.get('from', '(unknown)'),
            'subject': headers.get('subject', '(no subject)'),
            'date': headers.get('date', ''),
            'snippet': msg_data.get('snippet', ''),
        })
    
    print(json.dumps({'ok': True, 'count': len(inbox), 'messages': inbox}))
except urllib.error.HTTPError as e:
    body = e.read().decode() if e.fp else ''
    print(json.dumps({'error': f'Gmail API error: HTTP {e.code}', 'body': body[:500]}))
except Exception as e:
    print(json.dumps({'error': f'Gmail API failed: {e}'}))
