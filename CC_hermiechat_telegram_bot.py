#!/usr/bin/env python3
"""HermieChatt — Telegram ↔ local llama3.2:3b. Office Mac fallback when available."""
import json, requests, time, os

BOT_TOKEN = "8702536335:***"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "llama3.2-heretic:3b"
BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
ALLOWED = {5587703834}
STATE = os.path.expanduser("~/.hermie_offset.json")

def send_message(chat_id, text):
    requests.post(f"{BASE}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]}, timeout=10)

def load_offset():
    try: return json.load(open(STATE)).get("offset", 0)
    except: return 0

def save_offset(offset):
    json.dump({"offset": offset}, open(STATE, "w"))

print("HermieChatt started.", flush=True)

while True:
    try:
        offset = load_offset()
        for attempt in range(3):
            try:
                r = requests.get(f"{BASE}/getUpdates",
                    params={"offset": offset+1, "timeout": 25, "limit": 5}, timeout=35)
                if r.status_code == 200: break
            except:
                if attempt == 2: raise
                time.sleep(3)
        updates = r.json().get("result", [])
        for u in updates:
            msg = u.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")
            user_id = msg.get("from", {}).get("id")
            if not text or not chat_id or user_id not in ALLOWED:
                save_offset(u["update_id"] + 1)
                continue
            print(f"[{chat_id}] {text[:60]}", flush=True)
            try:
                r = requests.post(OLLAMA_URL, json={
                    "model": MODEL,
                    "prompt": f"User: {text}\nAssistant: ",
                    "system": "You are Hermie, a helpful assistant.",
                    "stream": False,
                    "options": {"num_ctx": 4096, "num_predict": 512}
                }, timeout=120)
                reply = r.json().get("response", "")
                if reply:
                    send_message(chat_id, reply)
            except Exception as e:
                print(f"Error: {e}", flush=True)
                send_message(chat_id, "I'm having trouble connecting right now.")
            save_offset(u["update_id"] + 1)
        time.sleep(1)
    except Exception as e:
        print(f"Poll error: {e}", flush=True)
        time.sleep(3)
