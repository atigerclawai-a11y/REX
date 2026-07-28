#!/usr/bin/env python3
"""
GOJ Data Receiver — run this on your Mac to receive data posted from the browser.
Usage: python3 receive_goj_data.py
Then in Chrome console on the Google Sheet page, run the POST command shown below.
Data saves to: REX/data/goj_live_data.json
"""
import http.server
import json
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'goj_live_data.json')

class Handler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
            with open(OUTPUT_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ Saved {len(data.get('members', []))} members to {OUTPUT_PATH}")
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except Exception as e:
            print(f"✗ Error: {e}")
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress default logs

print("GOJ Data Receiver running on http://localhost:9999")
print("Waiting for data from browser...")
httpd = http.server.HTTPServer(('localhost', 9999), Handler)
httpd.handle_request()  # handle one request then exit
print("Done!")
