#!/usr/bin/env python3
"""CC_qwen3_telegram_bot.py — Telegram ↔ qwen3-heretic on Office Mac.
No cloud. No filters. No injection.
"""
import json, requests, time, sys

BOT_TOKEN = "8980921667:AAHSiScYoQ4d-trGe4nDB2FPI4Fe838sIM8"
OLLAMA_URL = "http://100.99.86.60:11434/api/generate"
MODEL = "qwen3-heretic:latest"
BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text):
    requests.post(f"{BASE}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]}, timeout=10)

def ask_heretic(prompt):
    r = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.6, "num_ctx": 4096}
    }, timeout=120)
    return r.json().get("response", "No response")

print(f"Bot: {MODEL} → Office Mac", flush=True)

offset = 0
while True:
    try:
        r = requests.get(f"{BASE}/getUpdates",
            params={"offset": offset, "timeout": 5}, timeout=10)
        updates = r.json().get("result", [])
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message", {})
            txt = msg.get("text", "")
            cid = msg.get("chat", {}).get("id")
            if txt and cid:
                print(f"📩 {txt[:60]}", flush=True)
                reply = ask_heretic(txt)
                send_message(cid, reply)
                print(f"📤 {reply[:60]}", flush=True)
    except Exception as e:
        print(f"⚠️ {e}", flush=True)
        time.sleep(2)
