#!/usr/bin/env python3
"""Cloud-fallback proxy: routes simple tasks to local Ollama, complex to DeepSeek.
Listens on :11436. LibreChat points here instead of :11434 directly.
"""

import json, os, sys, requests
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

OLLAMA = "http://localhost:11434"          # M4's local Ollama
OLLAMA_OFFICE = "http://localhost:11434"  # Office Mac — Rexxie
# ROUTER DISABLED 2026-07-12 — was hijacking to random models. NEVER re-enable.

# Model Selector — reads active model from CC_model_selector.py config
MODEL_SELECTOR_CONFIG = os.path.expanduser("~/Desktop/REX/.model_selector.json")

def _load_model_map():
    """Build model map — reads from model_selector.json, falls back to hardcoded."""
    MODELS = {
        "rexxie": "gemma4:4b-heretic",
        "coder": "ghs-coder:latest",
        "hermes4": "rexxie-hermes4:latest",
        "gemma": "gemma4:12b-heretic",
    }
    try:
        with open(MODEL_SELECTOR_CONFIG) as f:
            cfg = json.load(f)
            # Merge config values over hardcoded defaults
            for key, val in cfg.get("models", {}).items():
                if isinstance(val, dict) and "ollama" in val:
                    MODELS[key] = val["ollama"]
                elif isinstance(val, str):
                    MODELS[key] = val
            active = cfg.get("active", "rexxie")
            if active in MODELS:
                return MODELS, MODELS[active]
            return MODELS, MODELS.get("rexxie", "gemma4:4b-heretic")
    except Exception:
        return MODELS, MODELS.get("rexxie", "gemma4:4b-heretic")

MODEL_MAP, _ = _load_model_map()

def get_active_model():
    """Read which model Kato wants to use right now."""
    _, active = _load_model_map()
    return active

AUTHORIZED_MODELS = list(MODEL_MAP.values())  # All allowed models
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_KEY:
    # Fallback: read from Hermes .env file
    env_path = os.path.expanduser("~/.hermes/profiles/cloud/.env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    DEEPSEEK_KEY = line.strip().split("=", 1)[1]
                    break
    except Exception:
        pass

CLOUD_KEYWORDS = [
    "code", "debug", "refactor", "script", "function", "python", "javascript",
    "complex", "analyze", "research", "audit", "security", "browse",
    "multi-step", "orchestrate", "explain in detail", "compare and contrast",
    "write a program", "implement", "algorithm", "architecture",
]
FORCE_LOCAL = ["private", "vault", "portfolio", "personal", "default"]

class ProxyHandler(BaseHTTPRequestHandler):
    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, task):
        task_lower = task.lower()
        if any(kw in task_lower for kw in CLOUD_KEYWORDS):
            return ("cloud", "deepseek-chat")
        # DEFAULT: use active model from selector
        active = get_active_model()
        return ("ollama", active)

    def _ollama_chat(self, messages):
        active_model = get_active_model()
        r = requests.post(f"{OLLAMA_OFFICE}/api/chat", json={
            "model": active_model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": 8000, "temperature": 0.7},
        }, timeout=120)
        data = r.json()
        # VERIFY: only accept responses from authorized models
        resp_model = data.get("model", "")
        if resp_model and resp_model not in AUTHORIZED_MODELS and resp_model.replace(":latest","") not in AUTHORIZED_MODELS:
            print(f"⚠️ MODEL MISMATCH! Got '{resp_model}', expected one of {AUTHORIZED_MODELS}. BLOCKED.", flush=True)
            return {
                "id": "chatcmpl-blocked",
                "object": "chat.completion",
                "created": 0,
                "model": "security-blocked",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "[Security: unauthorized model response blocked]"}, "finish_reason": "blocked"}]
            }
        return {
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "created": data.get("created_at", 0),
            "model": active_model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": data.get("message", {}).get("content", "")
                },
                "finish_reason": data.get("done_reason", "stop")
            }]
        }

    def _deepseek_chat(self, messages):
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        }
        r = requests.post(DEEPSEEK_URL, json={
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000,
        }, headers=headers, timeout=120)
        return r.json()

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/api/chat"):
            return self._json({"error": "Not found"}, 404)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        messages = body.get("messages", [])
        if not messages:
            return self._json({"error": "No messages"}, 400)
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        task = user_msgs[-1] if user_msgs else ""
        provider, model = self._route(task)
        if provider == "cloud":
            print(f"☁️  CLOUD → {task[:80]}...")
            result = self._deepseek_chat(messages)
        else:
            print(f"🏠 LOCAL → {task[:80]}...")
            result = self._ollama_chat(messages)
        self._json(result)

    def do_GET(self):
        if self.path == "/health":
            active = get_active_model()
            return self._json({"status": "ok", "mode": "local+cloud", "active_model": active})
        if self.path == "/v1/models":
            active = get_active_model()
            return self._json({
                "object": "list",
                "data": [
                    {"id": active, "object": "model", "owned_by": "ollama", "active": True},
                    {"id": "rexxie-qwen3:latest", "object": "model", "owned_by": "ollama"},
                    {"id": "ghs-coder:latest", "object": "model", "owned_by": "ollama"},
                    {"id": "rexxie-hermes4:latest", "object": "model", "owned_by": "ollama"},
                    {"id": "gemma4:12b-heretic", "object": "model", "owned_by": "ollama"},
                    {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"},
                ]
            })
        self._json({"error": "Not found"}, 404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not DEEPSEEK_KEY:
        print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    server = ThreadingHTTPServer(("0.0.0.0", 11436), ProxyHandler)
    print(f"🧠 Model Selector Proxy on :11436", flush=True)
    print(f"   Active: {get_active_model()}", flush=True)
    print(f"   Switch: python3 ~/Desktop/REX/CC_model_selector.py [rexxie|coder|hermes4|gemma]", flush=True)
    server.serve_forever()
