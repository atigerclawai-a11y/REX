#!/usr/bin/env python3
"""Model Router — classifies tasks and routes to the optimal model across Ollama + cloud.
Exposes HTTP API for Rexxie and Hermes to call.
Usage: python3 model_router.py --port 8767
"""

import json, sys, os, requests
from http.server import HTTPServer, BaseHTTPRequestHandler

OLLAMA = "http://localhost:11434"
DEEPSEEK = "deepseek-v4-pro"  # Cloud — strongest reasoning

# Model registry with strengths
REGISTRY = {
    "qwen2.5-coder:14b":    {"size": 9.0, "tags": ["code", "debug", "refactor", "script"], "url": f"{OLLAMA}/api/chat"},
    "mistral-hermie":       {"size": 14.3, "tags": ["private", "vault", "portfolio", "personal", "default"], "url": f"{OLLAMA}/api/chat"},
    "gemma4:latest":        {"size": 9.6, "tags": ["creative", "write", "draft", "brainstorm"], "url": f"{OLLAMA}/api/chat"},
    "qwen3:14b-hermie":     {"size": 9.3, "tags": ["analysis", "reasoning", "explain", "compare"], "url": f"{OLLAMA}/api/chat"},
    "command-r7b:7b":       {"size": 5.1, "tags": ["rag", "search", "retrieval", "facts"], "url": f"{OLLAMA}/api/chat"},
    "qwen3.5:9b":           {"size": 6.6, "tags": ["quick", "simple", "chat", "fast"], "url": f"{OLLAMA}/api/chat"},
    "llama3.2:3b":          {"size": 2.0, "tags": ["tiny", "fastest", "classify", "summarize"], "url": f"{OLLAMA}/api/chat"},
    "deepseek-v4-pro":      {"size": 0, "tags": ["complex", "audit", "security", "research", "browse", "multi-step", "orchestrate"], "url": "cloud"},
    "claude":               {"size": 0, "tags": ["creative", "nuanced", "draft", "design"], "url": "cloud"},
}

def route_task(task_description):
    """Route a task to the best model based on keyword matching."""
    task_lower = task_description.lower()
    
    # Score each model by keyword matches
    scores = {}
    for model, info in REGISTRY.items():
        score = sum(1 for tag in info["tags"] if tag in task_lower)
        scores[model] = score
    
    # Pick highest scoring
    best = max(scores, key=scores.get)
    
    # If no clear winner, use default
    if scores[best] == 0:
        best = "mistral-hermie"
    
    return {
        "model": best,
        "provider": "ollama" if REGISTRY[best]["url"] != "cloud" else "cloud",
        "size_gb": REGISTRY[best]["size"],
        "strengths": REGISTRY[best]["tags"],
        "reason": f"Matched tags: {[t for t in REGISTRY[best]['tags'] if t in task_lower] or ['default']}"
    }

def route_smart(task_description):
    """Use a lightweight model to intelligently route the task."""
    classifier_prompt = f"""Classify this task into ONE category. Reply with ONLY the category word.

Task: "{task_description}"

Categories:
- code (writing scripts, debugging, refactoring)
- private (portfolio, vault, personal data, financial)
- creative (writing, drafting, brainstorming, design)
- analysis (auditing, reasoning, explaining, comparing)
- research (browsing, searching, studying, learning)
- quick (simple questions, chat, fast responses)
- complex (multi-step, orchestration, delegation)

Category:"""
    
    try:
        r = requests.post(f"{OLLAMA}/api/generate", json={
            "model": "llama3.2:3b",
            "prompt": classifier_prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 20}
        }, timeout=15)
        category = r.json().get("response", "").strip().lower()
        
        # Map category to model
        mapping = {
            "code": "qwen2.5-coder:14b",
            "private": "mistral-hermie",
            "creative": "gemma4:latest",
            "analysis": "qwen3:14b-hermie",
            "research": "deepseek-v4-pro",
            "quick": "qwen3.5:9b",
            "complex": "deepseek-v4-pro",
        }
        
        model = mapping.get(category, "mistral-hermie")
        return {
            "model": model,
            "provider": "ollama" if REGISTRY[model]["url"] != "cloud" else "cloud",
            "category": category,
            "size_gb": REGISTRY[model]["size"],
            "strengths": REGISTRY[model]["tags"],
            "reason": f"LLM classified as: {category}"
        }
    except Exception:
        return route_task(task_description)  # Fallback to keyword


class RouterHandler(BaseHTTPRequestHandler):
    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, *args):
        pass
    
    def do_GET(self):
        if self.path == "/health":
            return self._json({"status": "ok", "models": len(REGISTRY)})
        if self.path == "/models":
            models = [{"name": m, "tags": i["tags"], "size": i["size"], "provider": "ollama" if i["url"]!="cloud" else "cloud"} for m, i in REGISTRY.items()]
            return self._json(models)
        self._json({"error": "Not found"}, 404)
    
    def do_POST(self):
        if self.path != "/route":
            return self._json({"error": "Not found"}, 404)
        
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        task = body.get("task", "")
        smart = body.get("smart", True)
        
        if not task:
            return self._json({"error": "Missing 'task' field"}, 400)
        
        result = route_smart(task) if smart else route_task(task)
        return self._json(result)


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8767
    server = HTTPServer(("127.0.0.1", port), RouterHandler)
    print(f"Model Router on :{port} — {len(REGISTRY)} models")
    server.serve_forever()