#!/usr/bin/env python3
"""Rexxie — Personal assistant. Local models. Falls back when Office Mac is down."""
import json, time, requests, sys, os, re
from pathlib import Path
from datetime import datetime
from threading import Thread

# Config
TOKEN = "8980921667:AAE4iYE3Lo6F-Ai9hz2QQDYUMsCD_I3LzTo"
OLLAMA_LOCAL = "http://127.0.0.1:11434"   # Local Ollama (always available)
MODEL_FAST = "tinyllama:latest"            # 1B, always fits
OLLAMA_THINK = "http://127.0.0.1:11434"   # Local Ollama
MODEL_THINK = "llama3.2-heretic:3b"        # 3.2B abliterated
INTAKE = os.path.expanduser("~/Documents/goj files/scans")
ALLOWED = {5587703834}
TELEGRAM = f"https://api.telegram.org/bot{TOKEN}"
STATE = os.path.expanduser("~/Desktop/REX/.rexxie_assists_state.json")
LOG = os.path.expanduser("~/Desktop/REX/logs/rexxie_assists.log")
CONV_MEMORY = os.path.expanduser("~/Desktop/REX/.rexxie_conversations.json")
PERPETUAL_PATH = os.path.expanduser("~/GHS-Vault/Jarvis Perpetual Memory.md")

SYSTEM_PROMPT = """You are Rexxie, personal assistant to Kato (Alejandro). You are a very good, well-paid human PA. You own his schedule, triage communications, track money (propose-approve ONLY), handle personal operations, draft documents, and keep the record.

## PERSONALITY
Pleasant, composed, direct. Professional without cold. Steady under pressure. No pet names, no emojis unless Kato uses them first.

## HOW YOU RESPOND
Answer FIRST. Then only the reasoning that changes what he does next. Then stop.
Brief by default; depth scales with stakes.

## HONESTY RULES
Never invent facts. If you don't know, say NOT FOUND or NOT SURE.

## CONFIDENTIALITY
Everything Kato tells you is confidential."""

Path(LOG).parent.mkdir(parents=True, exist_ok=True)
sys.stdout = open(LOG, "a")
sys.stderr = open(LOG.replace(".log", ".err"), "a")

VAULT_INDEX = os.path.expanduser("~/Desktop/REX/.rexxie_vault_index.md")
VAULT_PATH = os.path.expanduser("~/GHS-Vault")

def build_system_prompt(user_text=""):
    prompt = SYSTEM_PROMPT
    try:
        if os.path.exists(PERPETUAL_PATH):
            with open(PERPETUAL_PATH) as f:
                prompt += f"\n\nKato's Perpetual Memory:\n{f.read()[-1200:].strip()}"
    except: pass
    if user_text:
        text_lower = user_text.lower()
        try:
            with open(VAULT_INDEX) as f:
                idx = f.read()[:1500]
            prompt += f"\n\nYour Obsidian Vault (index):\n{idx}"
        except: pass
    return prompt

def send(chat_id, text):
    text = text[:4000]
    for _ in range(3):
        try:
            r = requests.post(f"{TELEGRAM}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
            if r.status_code == 200: return
        except: pass
        time.sleep(2)

def load_conversations():
    try:
        with open(CONV_MEMORY) as f: return json.load(f)
    except: return {}

def save_conversations(convos):
    with open(CONV_MEMORY, "w") as f: json.dump(convos, f)

def needs_thinking(text, msgs):
    t = (text or "").lower()
    if len(msgs) > 6: return True
    if len(t.split()) > 20: return True
    complex_kw = ["explain","analyze","plan","design","build","debug","fix","optimize","audit","strategy","compare","why","how","propose"]
    if any(k in t for k in complex_kw): return True
    return False

def chat(messages, user_text=""):
    use_think = needs_thinking(user_text, messages)
    url = OLLAMA_THINK if use_think else OLLAMA_LOCAL
    model = MODEL_THINK if use_think else MODEL_FAST
    timeout = 180 if use_think else 60
    ctx = 8192 if use_think else 4096
    
    sys_prompt = build_system_prompt(user_text)
    # Build prompt as plain text (works with any model)
    prompt_parts = []
    for m in messages:
        r = m.get("role","user")
        c = m.get("content","")
        if r == "user":
            prompt_parts.append(f"User: {c}")
        elif r == "assistant":
            prompt_parts.append(f"Assistant: {c}")
    prompt_parts.append("Assistant: ")
    prompt = "\n".join(prompt_parts)
    
    t0 = time.time()
    try:
        payload = {
            "model": model, "prompt": prompt, "system": sys_prompt,
            "stream": False, "options": {"num_ctx": ctx, "num_predict": 1024}
        }
        r = requests.post(f"{url}/api/generate", json=payload, timeout=timeout)
        resp = r.json()
        content = resp.get("response", "")
        if not content:
            # Debug: log the raw response
            print(f"{datetime.now()} -- WARN: empty response. url={url} model={model} status={r.status_code}", flush=True)
            print(f"{datetime.now()} -- WARN: raw resp keys: {list(resp.keys())}", flush=True)
        elapsed = time.time() - t0
        if content:
            print(f"{datetime.now()} -- Response: {len(content)} chars in {elapsed:.1f}s", flush=True)
        return content
    except Exception as e:
        print(f"{datetime.now()} -- Model error: {e}", flush=True)
        return "I'm having trouble connecting to my model right now. Try again in a moment."

def preload_model():
    for url, model in [(OLLAMA_LOCAL, MODEL_FAST), (OLLAMA_THINK, MODEL_THINK)]:
        for i in range(5):
            try:
                r = requests.post(f"{url}/api/generate", json={
                    "model": model, "prompt": ".", "stream": False
                }, timeout=120)
                if r.json().get("response") is not None: break
                time.sleep(3)
            except: time.sleep(3)
    return True

def keepalive():
    while True:
        time.sleep(600)
        for url, model in [(OLLAMA_LOCAL, MODEL_FAST), (OLLAMA_THINK, MODEL_THINK)]:
            try:
                requests.post(f"{url}/api/generate", json={"model": model, "prompt": ".", "stream": False}, timeout=60)
            except: pass

def load_state():
    try: return json.load(open(STATE)).get("offset", 0)
    except: return 0

def save_state(offset):
    json.dump({"offset": offset}, open(STATE, "w"))

memory = load_conversations()
print(f"{time.ctime()} -- Preloading...", flush=True)
preload_model()
print(f"{time.ctime()} -- Rexxie started. {len(memory)} convos.", flush=True)
Thread(target=keepalive, daemon=True).start()

while True:
    try:
        offset = load_state()
        for attempt in range(3):
            try:
                r = requests.get(f"{TELEGRAM}/getUpdates", params={"offset": offset+1, "timeout": 25, "limit": 5}, timeout=35)
                if r.status_code == 200: break
            except:
                if attempt == 2: raise
                time.sleep(3)
        updates = r.json().get("result", [])
        for u in updates:
            msg = u.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id"))
            user_id = msg.get("from", {}).get("id")
            text = msg.get("text", "")
            if not text or not chat_id or user_id not in ALLOWED:
                save_state(u["update_id"] + 1)
                continue
            print(f"{time.ctime()} -- [{chat_id}] {text[:80]}", flush=True)
            if text == "/start":
                send(chat_id, "Rexxie here. Personal assistant.")
            elif text == "/forget":
                memory.pop(chat_id, None)
                save_conversations(memory)
                send(chat_id, "Forgotten.")
            else:
                msgs = memory.get(chat_id, [])
                msgs.append({"role": "user", "content": text})
                if len(msgs) > 30: msgs = msgs[-30:]
                try:
                    requests.post(f"{TELEGRAM}/sendChatAction", json={"chat_id": int(chat_id), "action": "typing"}, timeout=3)
                except: pass
                reply = chat(msgs, text)
                msgs.append({"role": "assistant", "content": reply})
                memory[chat_id] = msgs
                save_conversations(memory)
                send(int(chat_id), reply)
            save_state(u["update_id"] + 1)
        time.sleep(1)
    except Exception as e:
        print(f"{time.ctime()} -- ERROR: {e}", flush=True)
        time.sleep(3)
