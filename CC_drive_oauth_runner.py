#!/usr/bin/env python3
"""
CC_drive_oauth_runner.py
Runs Google Drive OAuth flow: starts local callback server on port 8085,
prints the auth URL, waits for the browser redirect, saves token.
Run once; token auto-renews forever after.
"""
import json, os, sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

CREDS  = os.path.expanduser('~/Desktop/REX/google_credentials.json')
TOKEN  = os.path.expanduser('~/.rex_google_token.json')
LOG    = os.path.expanduser('~/Desktop/REX/logs/CC_drive_oauth.log')

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/gmail.modify',
]

def log(msg):
    print(msg, flush=True)
    with open(LOG, 'a') as f:
        f.write(msg + '\n')

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    log('ERROR: google-auth-oauthlib not installed')
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(CREDS, scopes=SCOPES)
flow.redirect_uri = 'http://localhost:8085/'

auth_url, _ = flow.authorization_url(
    access_type='offline',
    prompt='consent',
    include_granted_scopes='false',
)

log(f'AUTH_URL_START')
log(auth_url)
log(f'AUTH_URL_END')
log('Waiting for browser redirect on localhost:8085 ...')

token_saved = False

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global token_saved
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        code = params.get('code', [None])[0]
        error = params.get('error', [None])[0]

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

        if error:
            self.wfile.write(f'<h1>Auth error: {error}</h1>'.encode())
            log(f'AUTH_ERROR:{error}')
            token_saved = True  # stop loop
            return

        if not code:
            # preflight / favicon / other — ignore and keep waiting
            log(f'IGNORED_REQUEST:{self.path}')
            self.wfile.write(b'<h1>Waiting for auth...</h1>')
            return

        try:
            flow.fetch_token(code=code)
            creds = flow.credentials
            token_data = {
                'token':         creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri':     creds.token_uri,
                'client_id':     creds.client_id,
                'client_secret': creds.client_secret,
                'scopes':        list(creds.scopes) if creds.scopes else SCOPES,
                'universe_domain': 'googleapis.com',
                'account':       '',
            }
            Path(TOKEN).write_text(json.dumps(token_data, indent=2))
            token_saved = True
            log(f'TOKEN_SAVED:{TOKEN}')
            log(f'HAS_REFRESH_TOKEN:{"YES" if creds.refresh_token else "NO"}')
            log(f'SCOPES_GRANTED:{list(creds.scopes)}')
            self.wfile.write(b'<h1>&#x2705; Auth complete! You can close this tab.</h1>')
        except Exception as e:
            log(f'TOKEN_EXCHANGE_ERROR:{e}')
            self.wfile.write(f'<h1>Error: {e}</h1>'.encode())
            token_saved = True  # stop loop on error too

    def log_message(self, *args): pass

HTTPServer.allow_reuse_address = True
server = HTTPServer(('localhost', 8085), Handler)
log('SERVER_LISTENING:8085')

# Loop until we get the real auth code (handles Chrome extension preflights)
while not token_saved:
    server.handle_request()

log('DONE')
