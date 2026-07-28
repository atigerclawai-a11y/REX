#!/usr/bin/env python3
"""CC_rexxie_telegram_bot.py — Direct Telegram ↔ Rexxie bridge.
Perpetual memory via Obsidian vault. 50+ message context window.
Auto-saves important facts to Obsidian.
"""
import json, os, sys, requests, time
import urllib3.util.connection, socket
_orig_allowed = urllib3.util.connection.allowed_gai_family
def _force_ipv4():
    return socket.AF_INET
urllib3.util.connection.allowed_gai_family = _force_ipv4

from collections import defaultdict
from pathlib import Path

# TOKEN loaded from config below
with open(os.path.expanduser("~/Desktop/REX/rex_rexxie_telegram_config.json")) as _f:
    TOKEN = json.load(_f)["bot_token"]
PROXY = "http://localhost:11436/v1/chat/completions"
RAG_SERVER = "http://127.0.0.1:9777"
ALLOWED_USERS = {5587703834}
STATE_FILE = os.path.expanduser("~/Desktop/REX/.rexxie_telegram_state.json")
MEMORY_FILE = os.path.expanduser("~/Desktop/REX/.rexxie_bot_memory.json")
OBSIDIAN_MEMORY = os.path.expanduser("~/Documents/GHS-Vault/Jarvis Perpetual Memory.md")
HEARTBEAT_FILE = os.path.expanduser("~/Desktop/REX/.rexxie_bot_heartbeat")
TELEGRAM = f"https://api.telegram.org/bot{TOKEN}"
MAX_HISTORY = 50  # Last 50 message pairs — fits easily in 128K context

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f).get("offset", 0)
    except Exception:
        return 0

def save_state(offset):
    with open(STATE_FILE, "w") as f:
        json.dump({"offset": offset}, f)
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(str(int(time.time())))

def load_memory():
    try:
        with open(MEMORY_FILE) as f:
            d = json.load(f)
            return defaultdict(list, {int(k): v for k, v in d.get("chats", {}).items()})
    except Exception:
        return defaultdict(list)

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump({"chats": {str(k): v for k, v in memory.items()}}, f)

def load_perpetual_memory():
    """Read Rexxie's perpetual memory from Obsidian vault."""
    try:
        with open(OBSIDIAN_MEMORY) as f:
            content = f.read()
        if len(content) > 50:
            return content
    except Exception:
        pass
    return ""

def save_to_obsidian(fact):
    """Append a fact to Rexxie's perpetual memory in Obsidian."""
    try:
        Path(OBSIDIAN_MEMORY).parent.mkdir(parents=True, exist_ok=True)
        if not os.path.exists(OBSIDIAN_MEMORY):
            with open(OBSIDIAN_MEMORY, "w") as f:
                f.write("# Rexxie Perpetual Memory\n\nFacts Kato has shared with me. Loaded before every conversation.\n\n")
        with open(OBSIDIAN_MEMORY, "a") as f:
            f.write(f"- {time.ctime()}: {fact}\n")
    except Exception:
        pass

def send_message(chat_id, text):
    chunks = []
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4000)
        if split_at < 3000:
            split_at = text.rfind(". ", 0, 4000)
        if split_at < 3000:
            split_at = 3999
        chunks.append(text[:split_at+1])
        text = text[split_at+1:]
    chunks.append(text)
    for chunk in chunks:
        requests.post(f"{TELEGRAM}/sendMessage", json={
            "chat_id": chat_id, "text": chunk
        }, timeout=10)

def rag_search(query):
    try:
        r = requests.get(f"{RAG_SERVER}/search", params={"q": query, "n": 2}, timeout=5)
        hits = r.json().get("results", [])
        if hits:
            return "\n".join(f"[{h['source']}] {h['text'][:200]}" for h in hits)
    except Exception:
        pass
    return ""

def chat_with_rexxie(chat_id, user_msg):
    memory = load_memory()
    history = memory.get(chat_id, [])
    perpetual = load_perpetual_memory()
    
    # Build messages
    messages = []
    
    # Perpetual memory first (injected as system context)
    if perpetual:
        messages.append({
            "role": "system", 
            "content": f"You are Rexxie, personal assistant to Kato (Alejandro). Answer first, then reasoning if needed, then stop. Bad news in the first line. Never invent facts — say NOT FOUND if unsure. Never use emojis unless Kato does first. You are a professional chief-of-staff, composed and direct.\n\nKato's perpetual memory:\n{perpetual[:1500]}"
        })
    
    # RAG context
    context = rag_search(user_msg)
    if context:
        messages.append({
            "role": "system",
            "content": f"Relevant knowledge from Kato's vault:\n{context}"
        })
    
    # Conversation history
    for h in history[-MAX_HISTORY * 2:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_msg})
    
    # Detect memory-saving intent: if Kato says "remember", "save", or "note" something
    save_instruction = ""
    memory_triggers = ["remember that", "save this", "note this", "remember:", "save:", "note:", 
                       "don't forget", "perpetual memory", "remember this"]
    if any(t in user_msg.lower() for t in memory_triggers):
        save_instruction = "\n\nIf Kato is sharing personal facts, preferences, or decisions with permanent intent, end your response with [MEMORY: <one-line summary to save>] so it gets stored in his Obsidian vault."
    
    if save_instruction:
        messages.insert(-1, {"role": "system", "content": save_instruction})
    
    r = requests.post(PROXY, json={"messages": messages}, timeout=120)
    return r.json()["choices"][0]["message"]["content"]

def process_update(update):
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    text = msg.get("text", "")
    
    if not text or not chat_id:
        return
    
    if user_id not in ALLOWED_USERS:
        send_message(chat_id, "Access denied.")
        return
    
    if text == "/start":
        pmem = "loaded" if os.path.exists(OBSIDIAN_MEMORY) else "empty"
        send_message(chat_id, f"Rexxie here — Gemma 3 12B, 50-message memory, perpetual memory: {pmem}.\n/health /forget — What do you need, Kato?")
        return
    
    if text == "/health":
        mem = load_memory()
        msgs = len(mem.get(chat_id, [])) // 2
        pmem = "yes" if os.path.exists(OBSIDIAN_MEMORY) else "no"
        send_message(chat_id, f"✅ Rexxie alive\nModel: Gemma 4 12B uncensored\nMemory: {msgs} exchanges active\nPerpetual: {pmem}\nRAG: 31K chunks")
        return
    
    if text == "/forget":
        memory = load_memory()
        memory[chat_id] = []
        save_memory(memory)
        send_message(chat_id, "Memory cleared.")
        return
    
    try:
        requests.post(f"{TELEGRAM}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass
    
    try:
        reply = chat_with_rexxie(chat_id, text)
        
        # Check for perpetual memory save instruction
        if "[MEMORY:" in reply:
            parts = reply.split("[MEMORY:", 1)
            reply = parts[0].strip()
            fact = parts[1].split("]", 1)[0].strip()
            save_to_obsidian(fact)
            reply += f"\n\n📝 Saved to perpetual memory."
        
        # Save to conversation memory
        memory = load_memory()
        history = memory.get(chat_id, [])
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        if len(history) > MAX_HISTORY * 2:
            history = history[-(MAX_HISTORY * 2):]
        memory[chat_id] = history
        save_memory(memory)
        
        send_message(chat_id, reply)
    except Exception as e:
        send_message(chat_id, f"⚠️ Error: {str(e)[:200]}")

def main():
    sys.stdout = open(os.path.expanduser("~/Desktop/REX/logs/rexxie_telegram_bot.log"), "a")
    sys.stderr = open(os.path.expanduser("~/Desktop/REX/logs/rexxie_telegram_bot.error.log"), "a")
    print(f"{time.ctime()} — Bot v3 with perpetual memory started", flush=True)
    
    while True:
        try:
            offset = load_state()
            print(f"{time.ctime()} — DEBUG: calling getUpdates, offset={offset}", flush=True)
            r = requests.get(f"{TELEGRAM}/getUpdates", params={
                "offset": offset + 1, "timeout": 0, "limit": 5
            }, timeout=30)
            print(f"{time.ctime()} — DEBUG: getUpdates returned, status={r.status_code}", flush=True)

            if r.status_code == 409:
                time.sleep(30)
                continue
            if r.status_code != 200:
                time.sleep(5)
                continue

            
            updates = r.json().get("result", [])
            if updates:
                print(f"{time.ctime()} — Got {len(updates)} update(s)", flush=True)
            
            for upd in updates:
                process_update(upd)
                save_state(upd["update_id"])
            time.sleep(2)
        except requests.exceptions.ReadTimeout:
            time.sleep(2)
            continue
        except requests.exceptions.ConnectionError:
            time.sleep(5)
        except Exception as e:
            print(f"{time.ctime()} — Error: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
