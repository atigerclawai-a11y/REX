#!/usr/bin/env python3
"""Rexxie — Personal assistant. rexxie:12b via Office Mac. Perpetual memory."""
import json, time, requests, sys, os, re
from pathlib import Path
from datetime import datetime
from threading import Thread

# Config
TOKEN = "8980921667:AAE4iYE3Lo6F-Ai9hz2QQDYUMsCD_I3LzTo"
OLLAMA_LOCAL = "http://127.0.0.1:11435"   # Office Mac via SSH tunnel
MODEL_FAST = "rexxie:12b"                  # 12B, fast cache-hit
OLLAMA_THINK = "http://127.0.0.1:11435"   # Office Mac via SSH tunnel
MODEL_THINK = "rexxie:12b"                 # 12B, big think
MODEL = MODEL_THINK
INTAKE = os.path.expanduser("~/Documents/goj files/scans")
OLLAMA = OLLAMA_THINK
ALLOWED = {5587703834}
TELEGRAM = f"https://api.telegram.org/bot{TOKEN}"
STATE = os.path.expanduser("~/Desktop/REX/.rexxie_assists_state.json")
LOG = os.path.expanduser("~/Desktop/REX/logs/rexxie_assists.log")
CONV_MEMORY = os.path.expanduser("~/Desktop/REX/.rexxie_conversations.json")
PERPETUAL_PATH = os.path.expanduser("~/GHS-Vault/Jarvis Perpetual Memory.md")

SYSTEM_PROMPT = """You are Rexxie, personal assistant to Kato (Alejandro). You are a very good, well-paid human PA. You own his schedule, triage communications, track money (propose-approve ONLY -- never move money alone), handle personal operations, draft documents, and keep the record.

## PERSONALITY
Pleasant, composed, direct. Professional without cold. Steady under pressure. No pet names, no emojis unless Kato uses them first.

## HOW YOU RESPOND
Answer FIRST. Then only the reasoning that changes what he does next. Then stop.
Brief by default; depth scales with stakes, not enthusiasm. No filler.

## HONESTY RULES
Never invent facts. If you don't know, say NOT FOUND or NOT SURE.

## CONFIDENTIALITY
Everything Kato tells you is confidential. Private information never enters outbound text unless the task requires it."""

# Redirect output
Path(LOG).parent.mkdir(parents=True, exist_ok=True)
sys.stdout = open(LOG, "a")
sys.stderr = open(LOG.replace(".log", ".err"), "a")

VAULT_INDEX = os.path.expanduser("~/Desktop/REX/.rexxie_vault_index.md")
VAULT_PATH = os.path.expanduser("~/GHS-Vault")

def lookup_vault_files(user_text):
    text_lower = user_text.lower()
    results = []
    try:
        with open(VAULT_INDEX) as f:
            index_lines = f.readlines()
        words = set(re.findall(r'\w+', text_lower))
        matching = []
        for line in index_lines:
            line_lower = line.lower()
            score = sum(1 for w in words if len(w) > 3 and w in line_lower)
            if score >= 2:
                fnames = re.findall(r'[\w/-]+\.md', line)
                if fnames:
                    path = os.path.join(VAULT_PATH, fnames[0])
                    if os.path.exists(path):
                        matching.append((score, path, fnames[0]))
        matching.sort(reverse=True)
        for _, path, name in matching[:3]:
            try:
                with open(path) as f:
                    content = f.read()[:2000]
                results.append(f"--- vault:{name} ---\n{content}")
            except: pass
    except: pass
    return "\n\n".join(results)

def build_system_prompt(user_text=""):
    prompt = SYSTEM_PROMPT
    perpetual = load_perpetual()
    if perpetual:
        prompt += f"\n\nKato's Perpetual Memory:\n{perpetual[:1200]}"
    try:
        with open(VAULT_INDEX) as f:
            index = f.read()[:1500]
        prompt += f"\n\nYour Obsidian Vault (index):\n{index}"
    except:
        pass
    if user_text:
        vault_content = lookup_vault_files(user_text)
        if vault_content:
            prompt += f"\n\nRelevant vault files for this request:\n{vault_content}"
    return prompt

def send(chat_id, text):
    text = text[:4000]
    for attempt in range(3):
        try:
            r = requests.post(f"{TELEGRAM}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
            if r.status_code == 200:
                return
        except:
            pass
        time.sleep(2)

def load_perpetual():
    try:
        if os.path.exists(PERPETUAL_PATH):
            with open(PERPETUAL_PATH) as f:
                content = f.read()
            return content[-2000:].strip()
    except:
        pass
    return ""

def save_perpetual(fact):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n- [{timestamp}] (Rexxie) {fact}"
        with open(PERPETUAL_PATH, "a") as f:
            f.write(entry)
        return True
    except:
        return False

def load_conversations():
    try:
        with open(CONV_MEMORY) as f:
            return json.load(f)
    except:
        return {}

def save_conversations(convos):
    with open(CONV_MEMORY, "w") as f:
        json.dump(convos, f)

def needs_thinking(user_text, messages):
    text = (user_text or "").lower()
    history_len = len(messages)
    simple = ["hello", "hi", "hey", "ok", "thanks", "bye", "good morning", "good night",
              "how are you", "what's up", "status", "who are you", "what can you do",
              "remember", "forget", "/remember", "/forget"]
    if any(s in text for s in simple) and len(text.split()) < 5:
        return False
    complex_signals = ["explain", "analyze", "plan", "design", "build", "debug", "fix",
                       "optimize", "audit", "strategy", "compare", "evaluate", "review",
                       "why", "how", "what if", "propose", "architect", "refactor",
                       "diagnose", "investigate", "reason", "decide"]
    if any(s in text for s in complex_signals):
        return True
    if len(text.split()) > 20:
        return True
    if history_len > 6:
        return True
    return False

def format_chat_prompt(messages, system_prompt):
    """Format messages into a prompt string for /api/generate using Gemma format."""
    prompt = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            prompt += f"<start_of_turn>system\n{content}<end_of_turn>\n"
        elif role == "user":
            prompt += f"<start_of_turn>user\n{content}<end_of_turn>\n"
        elif role == "assistant":
            prompt += f"<start_of_turn>model\n{content}<end_of_turn>\n"
    prompt += "<start_of_turn>model\n"
    return prompt

def chat(messages, user_text=""):
    use_think = needs_thinking(user_text, messages)
    ollama_url = OLLAMA_THINK if use_think else OLLAMA_LOCAL
    model = MODEL_THINK if use_think else MODEL_FAST
    timeout = 180 if use_think else 60
    ctx = 8192 if use_think else 4096
    max_tok = 2048 if use_think else 512
    
    sys_prompt = build_system_prompt(user_text)
    # Prepend system as a message
    all_msgs = [{"role": "system", "content": sys_prompt}] + messages
    prompt_str = format_chat_prompt(all_msgs, sys_prompt)
    
    t0 = time.time()
    r = requests.post(f"{ollama_url}/api/generate", json={
        "model": model,
        "prompt": prompt_str,
        "system": sys_prompt,
        "stream": False,
        "options": {"num_ctx": ctx, "num_predict": max_tok}
    }, timeout=timeout)
    elapsed = time.time() - t0
    result = r.json()
    content = result.get("response", "")
    model_name = "think" if use_think else "fast"
    if content:
        print(f"{datetime.now()} -- [{model_name}] Response: {len(content)} chars in {elapsed:.1f}s", flush=True)
    return content

def preload_model():
    for url, model in [(OLLAMA_LOCAL, MODEL_FAST), (OLLAMA_THINK, MODEL_THINK)]:
        for i in range(5):
            try:
                r = requests.post(f"{url}/api/generate", json={
                    "model": model,
                    "prompt": ".",
                    "stream": False
                }, timeout=120)
                if r.json().get("response") is not None:
                    break
                time.sleep(3)
            except:
                time.sleep(3)
    return True

def keepalive():
    while True:
        time.sleep(600)
        for url, model in [(OLLAMA_LOCAL, MODEL_FAST), (OLLAMA_THINK, MODEL_THINK)]:
            try:
                requests.post(f"{url}/api/generate", json={
                    "model": model,
                    "prompt": ".",
                    "stream": False
                }, timeout=60)
            except:
                pass

def load_state():
    try:
        return json.load(open(STATE)).get("offset", 0)
    except:
        return 0

def save_state(offset):
    json.dump({"offset": offset}, open(STATE, "w"))

memory = load_conversations()
print(f"{time.ctime()} -- Preloading models ({MODEL_FAST} + {MODEL_THINK})...", flush=True)
if preload_model():
    print(f"{time.ctime()} -- Model preloaded.", flush=True)
else:
    print(f"{time.ctime()} -- WARNING: Model preload failed!", flush=True)
Thread(target=keepalive, daemon=True).start()
print(f"{time.ctime()} -- Rexxie Assists started. Conversations loaded: {len(memory)}", flush=True)

while True:
    try:
        offset = load_state()
        for attempt in range(3):
            try:
                r = requests.get(f"{TELEGRAM}/getUpdates", 
                    params={"offset": offset+1, "timeout": 25, "limit": 5}, timeout=35)
                if r.status_code == 200:
                    break
            except:
                if attempt == 2:
                    raise
                time.sleep(3)
        updates = r.json().get("result", [])
        for u in updates:
            msg = u.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id"))
            user_id = msg.get("from", {}).get("id")
            text = msg.get("text", "")
            doc = msg.get("document")
            photo = msg.get("photo")
            caption = msg.get("caption", "")
            if (doc or photo) and chat_id and user_id in ALLOWED:
                try:
                    file_id = None
                    ext = ".pdf"
                    if doc:
                        file_id = doc.get("file_id")
                        fname = doc.get("file_name", "document.pdf")
                        ext = os.path.splitext(fname)[1] or ".pdf"
                    elif photo:
                        file_id = photo[-1]["file_id"]
                        ext = ".jpg"
                    if file_id:
                        gf = requests.get(f"{TELEGRAM}/getFile", params={"file_id": file_id}, timeout=15).json()
                        fp = gf.get("result", {}).get("file_path")
                        if fp:
                            dl_url = f"https://api.telegram.org/file/bot{TOKEN}/{fp}"
                            dl = requests.get(dl_url, timeout=30)
                            ts = int(time.time())
                            dest = os.path.join(INTAKE, f"tg_{ts}{ext}")
                            with open(dest, "wb") as f:
                                f.write(dl.content)
                            send(chat_id, f"Saved to OCR intake: {os.path.basename(dest)}")
                            print(f"{time.ctime()} -- [{chat_id}] OCR intake: {dest}", flush=True)
                except Exception as e:
                    print(f"{time.ctime()} -- OCR intake error: {e}", flush=True)
                    send(chat_id, "Could not save file for OCR.")
                save_state(u["update_id"] + 1)
                continue
            if not text or not chat_id or user_id not in ALLOWED:
                save_state(u["update_id"] + 1)
                continue
            print(f"{time.ctime()} -- [{chat_id}] {text[:80]}", flush=True)
            if text == "/start":
                send(chat_id, "Rexxie here. Your personal assistant with perpetual memory. I remember.")
            elif text == "/forget":
                memory.pop(chat_id, None)
                save_conversations(memory)
                send(chat_id, "Conversation cleared.")
            else:
                msgs = memory.get(chat_id, [])
                msgs.append({"role": "user", "content": text})
                if len(msgs) > 30:
                    msgs = msgs[-30:]
                try:
                    requests.post(f"{TELEGRAM}/sendChatAction", json={"chat_id": int(chat_id), "action": "typing"}, timeout=3)
                except:
                    pass
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
