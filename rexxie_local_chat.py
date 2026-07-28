#!/usr/bin/env python3
'''Rexxie Local Chat — fully private web interface on localhost:8420'''
import json, requests, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

OLLAMA = "http://127.0.0.1:11435"
MODEL = "jikepjikep_16HEX/gemma-4-12b-nightshift-heretic-uncensored-qat-q4"
PORT = 8420

SYSTEM_PROMPT = '''You are Rexxie, Kato's personal assistant. Fully local and private.
Same employment contract, 2-source rule, and personality as always.
Answer first. Bad news upfront. Brief by default. No filler. No inventions.'''

VAULT_INDEX = os.path.expanduser("~/Desktop/REX/.rexxie_vault_index.md")
PERPETUAL = os.path.expanduser("~/GHS-Vault/Jarvis Perpetual Memory.md")
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rexxie_chat_ui.html")

def load_perpetual():
    try:
        if os.path.exists(PERPETUAL):
            with open(PERPETUAL) as f: return f.read()[-1500:]
    except: pass
    return ""

def load_vault_index():
    try:
        with open(VAULT_INDEX) as f: return f.read()[:1500]
    except: pass
    return ""

def load_html():
    try:
        with open(HTML_FILE) as f: return f.read()
    except: return "<h1>UI not found</h1>"

def chat(messages, user_text=""):
    prompt = SYSTEM_PROMPT
    prompt += "\n\nPerpetual Memory:\n" + load_perpetual()
    prompt += "\n\nVault Index:\n" + load_vault_index()
    full = [{"role": "system", "content": prompt}] + messages
    try:
        r = requests.post(f"{OLLAMA}/v1/chat/completions",
            json={"model": MODEL, "messages": full,
                  "max_tokens": 2048, "options": {"num_ctx": 8192}},
            timeout=120)
        choice = r.json().get("choices", [{}])[0].get("message", {})
        return choice.get("content", "") or choice.get("reasoning", "")
    except Exception as e:
        return f"[Rexxie is thinking — please retry. {str(e)[:80]}]"

class Handler(BaseHTTPRequestHandler):
    html_cache = None
    
    def do_GET(self):
        if self.path == "/":
            if not Handler.html_cache:
                Handler.html_cache = load_html()
            self._serve(200, "text/html", Handler.html_cache.encode())
        elif self.path == "/manifest.json":
            self._serve(200, "application/json", json.dumps({
                "name": "Rexxie", "short_name": "Rexxie",
                "start_url": "/", "display": "standalone",
                "background_color": "#0a0a0f", "theme_color": "#0a0a0f",
                "description": "Fully local private AI assistant"
            }).encode())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == "/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            text = body.get("text", "")
            history = body.get("history", [])
            msgs = [{"role": h["role"], "content": h["content"]} for h in history]
            msgs.append({"role": "user", "content": text})
            reply = chat(msgs, text)
            self._serve(200, "application/json", json.dumps({"reply": reply}).encode())
        else:
            self.send_response(404); self.end_headers()

    def _serve(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args): pass

print(f"Rexxie at http://localhost:{PORT}  |  https://rexxie.goldhealthsys.com")
HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
