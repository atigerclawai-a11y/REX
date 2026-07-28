#!/usr/bin/env python3
"""
CC_ghs_staff_daemon.py — GHS Staff Bot
One bot, two roles:
  - Masha  → BBG Front of House (menu, hours, FAQs, social posting)
  - Viktoriya → GOJ Front Desk (attendance, client lookup, call tracking)
  - Kato   → Admin (manage staff, switch roles, broadcast)

Pattern: same as CC_higgsfield_telegram_daemon.py — Python async, Telegram long-poll.
"""
import asyncio, json, os, sys, traceback, sqlite3, random
from pathlib import Path
from datetime import datetime, timedelta
import httpx

# Persistent memory & knowledge
from CC_ghs_memory import GHSMemory, extract_knowledge_from_message, get_memory
_ghs_memory = get_memory()

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════

CONFIG_PATH = Path.home() / ".hermes" / "profiles" / "cloud" / "ghs_staff_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text())
BOT_TOKEN = CONFIG.get("bot_token", "")
BOT_USERNAME = CONFIG.get("bot_username", "@GHS_Staff_Bot")
STAFF = CONFIG.get("staff", {})

if not BOT_TOKEN or "PLACEHOLDER" in BOT_TOKEN:
    print("ERROR: Bot token not configured. Edit:", CONFIG_PATH, file=sys.stderr)
    sys.exit(1)

TELEGRAM_API = "https://api.telegram.org"
SOCIAL_ROUTER = "http://127.0.0.1:8000/social"
REX_BASE = "http://127.0.0.1:8000"
AUTH_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
BUSINESS_MEMORY_FILE = Path.home() / "Desktop" / "REX" / "higgsfield_business_memory.json"

STATE_FILE = Path.home() / ".hermes" / "profiles" / "cloud" / "ghs_staff_state.json"
LOG_FILE = Path.home() / "Desktop" / "REX" / "logs" / "ghs_staff_daemon.log"
os.makedirs(LOG_FILE.parent, exist_ok=True)

# In-memory overrides (admin role switching)
role_overrides: dict = {}
_active_call_lists: dict = {}

# ═══════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

async def send_message(chat_id: int, text: str, reply_markup=None):
    """Send a Telegram message. Robust fallback: plain text if Markdown fails."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Try Markdown first
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            resp = await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage", json=payload)
            if resp.status_code == 200:
                _store_outgoing(chat_id, text, role=None)  # role detected inside
                return True

            # Markdown failed — log and retry plain text
            err = resp.json()
            log(f"send_message Markdown fail ({resp.status_code}): {err.get('description','')[:150]}")
            payload.pop("parse_mode", None)
            resp2 = await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage", json=payload)
            if resp2.status_code == 200:
                _store_outgoing(chat_id, text, role=None)
                return True
            err2 = resp2.json()
            log(f"send_message plain fail: {err2.get('description','')[:150]}")
            return False
    except Exception as e:
        log(f"send_message exception: {e}")
        return False

def _store_outgoing(chat_id: int, text: str, role: str = None):
    """Store outgoing bot message in persistent memory."""
    try:
        if role is None:
            role = get_staff_role(chat_id)
        agent = role if role in ("masha", "viktoriya") else "general"
        _ghs_memory.remember_message(chat_id, "assistant", text, agent)
    except Exception:
        pass

def _store_incoming(chat_id: int, text: str):
    """Store incoming user message in persistent memory."""
    try:
        role = get_staff_role(chat_id)
        agent = role if role in ("masha", "viktoriya") else "general"
        _ghs_memory.remember_message(chat_id, "user", text, agent)
    except Exception:
        pass

async def answer_callback(callback_id: str, text: str = ""):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{TELEGRAM_API}/bot{BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text},
            )
    except Exception:
        pass

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed_updates": []}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))

# ═══════════════════════════════════════════════════════════
# Business Memory
# ═══════════════════════════════════════════════════════════

_bm_cache = None

def load_business_memory():
    global _bm_cache
    if _bm_cache is not None:
        return _bm_cache
    if BUSINESS_MEMORY_FILE.exists():
        try:
            _bm_cache = json.loads(BUSINESS_MEMORY_FILE.read_text())
            return _bm_cache
        except Exception:
            pass
    _bm_cache = {}
    return _bm_cache

# ═══════════════════════════════════════════════════════════
# Role Detection
# ═══════════════════════════════════════════════════════════

def get_staff_role(chat_id: int) -> str:
    """Return 'masha', 'viktoriya', 'admin', or 'unknown'."""
    if chat_id in role_overrides:
        return role_overrides[chat_id]
    return STAFF.get(str(chat_id), {}).get("role", "unknown")

def get_staff_name(chat_id: int) -> str:
    return STAFF.get(str(chat_id), {}).get("name", "Unknown")

# ═══════════════════════════════════════════════════════════
# BBG Caption Generator (shared with Higgsfield bot pattern)
# ═══════════════════════════════════════════════════════════

def get_branded_caption(template_key: str, prompt: str, model: str = "text") -> str:
    """Generate a BBG-branded social caption."""
    bm = load_business_memory()
    templates = bm.get("caption_templates", {})
    hashtags = bm.get("hashtag_bank", {})
    business = bm.get("business", {})
    promo = business.get("current_promotion", "Buy 2 Get 1 Free")

    template = templates.get(template_key, templates.get("generic",
        "[HOOK]\n\n🍺 {promo}\n\n📍 Brighton Beach, Brooklyn\n\n{hashtags}"))

    always = " ".join(hashtags.get("always", ["#BoardwalkBeerGarden"]))
    brooklyn = " ".join(random.sample(hashtags.get("brooklyn", []), min(2, len(hashtags.get("brooklyn", [])))))
    food = " ".join(random.sample(hashtags.get("food_drink", []), min(2, len(hashtags.get("food_drink", [])))))
    vibes = " ".join(random.sample(hashtags.get("vibes", []), min(2, len(hashtags.get("vibes", [])))))

    weekend_vibes = ""
    if datetime.now().strftime("%A") in ("Saturday", "Sunday"):
        weekend_vibes = " " + " ".join(random.sample(hashtags.get("weekend_default", []), 1))

    hashtag_str = f"{always} {brooklyn} {food} {vibes}{weekend_vibes}"
    caption = template.replace("{promo}", promo).replace("{hashtags}", hashtag_str)

    if "[HOOK" in caption:
        caption = caption.replace("[HOOK — what's happening right now]", f"🌊 {prompt[:80]}")
        caption = caption.replace("[HOOK — first line grabs attention]", f"🌊 {prompt[:80]}")
        caption = caption.replace("[HOOK", f"🌊 {prompt[:80]}")

    if len(caption) < 1800:
        caption += "\n\n✨ Via GHS Staff Bot"
    return caption[:2200]

# ═══════════════════════════════════════════════════════════
# LLM Intelligence — DeepSeek (intent routing) + MiniMax (reasoning)
# ═══════════════════════════════════════════════════════════

import os as _os

def _load_deepseek_key():
    """Load DeepSeek API key from .env files."""
    env_paths = [
        Path.home() / ".hermes" / "profiles" / "cloud" / ".env",
        Path.home() / ".hermes" / ".env",
    ]
    for p in env_paths:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def _load_minimax_config():
    """Load MiniMax API key and base URL from .env files."""
    env_paths = [
        Path.home() / ".hermes" / "profiles" / "cloud" / ".env",
        Path.home() / ".hermes" / ".env",
    ]
    key = ""
    base_url = "https://api.minimax.io/v1"
    for p in env_paths:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("MINIMAX_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("MINIMAX_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key, base_url

DEEPSEEK_KEY = _load_deepseek_key()
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

MINIMAX_KEY, MINIMAX_URL = _load_minimax_config()
MINIMAX_CHAT_URL = f"{MINIMAX_URL}/chat/completions"

# Cache the last LLM answer per chat to avoid repeat calls
_last_llm: dict = {}

async def llm_understand(chat_id: int, text: str, role: str) -> str | None:
    """
    Send user's message to DeepSeek for intent understanding.
    Returns: intent string ("menu", "attendance", etc.) or None if LLM can't help.
    """
    if not DEEPSEEK_KEY or len(text) < 3:
        return None

    # Don't spam LLM for very short/generic messages
    if len(text) < 5 and text.lower() in ("ok", "hi", "hey", "yes", "no", "thanks", "thx"):
        return None

    prompt = f"""You are a routing assistant for a Telegram bot. Analyze this message and return a short JSON.

User message: "{text}"

Available intents:
- menu: food, drinks, menu items
- hours: opening/closing times
- specials: promotions, deals
- events: sports, games, happenings
- faq: questions about policies, parking, reservations, kids, dogs
- brain: questions about CRM, voice agent, strategy, pipeline, procedures
- attendance: who's here, counts
- client: looking up a specific client
- expiring: auth expirations
- calls: call lists, call tracking
- checkin: marking someone as arrived
- schedule_update: someone not coming, changing days, can come, switching schedules, absent, sick
- report: daily summary
- post: posting to social media
- flag: reporting an issue/problem
- unknown: nothing matches

Return ONLY: {{"intent": "menu", "query": "burgers"}}
If user asks a simple question you can answer directly, add: {{"intent": "direct", "answer": "..."}}
If someone mentions not coming/changing days/switching schedules, use "schedule_update".

JSON ONLY, no other text:"""

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.post(
                DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0,
                },
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Extract JSON from response
            import re as _re
            match = _re.search(r'\{[^}]+\}', content)
            if not match:
                return None

            result = json.loads(match.group())
            intent = result.get("intent", "unknown")

            # If direct answer
            if intent == "direct" and "answer" in result:
                await send_message(chat_id, result["answer"])
                return "direct"

            # Cache query for routing
            _last_llm[chat_id] = result.get("query", text)
            return intent

    except Exception as e:
        log(f"LLM fallback error: {e}")
        return None

# ── Reasoning with Memory ──────────────────────────────────────────

async def minimax_reason(chat_id: int, text: str, role: str = "general") -> str | None:
    """
    Use MiniMax for deep reasoning and natural conversation.
    Falls back to DeepSeek if MiniMax is unavailable.
    NOW WITH PERSISTENT MEMORY — remembers conversations, injects knowledge.
    """
    if not MINIMAX_KEY and not DEEPSEEK_KEY:
        log("No LLM keys configured for reasoning")
        return None

    # Load recent conversation from persistent memory
    recent = _ghs_memory.get_recent_history(chat_id, 10)
    
    # Build rich context from memory
    ctx = _ghs_memory.build_context(chat_id, text, role)
    knowledge_block = _ghs_memory.format_context_for_prompt(ctx, max_chars=800)
    
    system_prompts = {
        "masha": (
            "You are Masha, the friendly front-of-house AI for Boardwalk Beer Garden (BBG) "
            "in Brighton Beach, Brooklyn. You help with menu questions, hours, "
            "specials, events, and general info. Warm English with occasional "
            "Russian phrases. Concise but helpful — 2-3 sentences max."
        ),
        "viktoriya": (
            "You are Viktoriya, the front-desk AI for Garden of Joy Adult Day Care (GOJ) "
            "in Brooklyn. You help with client lookups, attendance, authorization expirations, "
            "call scheduling, and daily procedures. Professional English with "
            "occasional Russian. Concise — 2-3 sentences."
        ),
        "general": (
            "You are the GHS Staff AI assistant for Gold Health Systems. You help with "
            "Boardwalk Beer Garden (BBG) and Garden of Joy (GOJ) operations. Helpful, "
            "concise, and knowledgeable. 2-3 sentences unless asked for detail."
        ),
    }
    
    system_prompt = system_prompts.get(role, system_prompts["general"])
    if knowledge_block:
        system_prompt += f"\n\n---\n{knowledge_block}\n---\nUse this context to give a better answer."
    
    messages = [{"role": "system", "content": system_prompt}]
    # Add last 10 exchanges from persistent memory
    for h in recent:
        role_key = "assistant" if h["role"] == "assistant" else "user"
        messages.append({"role": role_key, "content": h["content"][:500]})
    messages.append({"role": "user", "content": text})
    
    # Try MiniMax first, fall back to DeepSeek
    providers = []
    if MINIMAX_KEY:
        providers.append(("minimax", MINIMAX_CHAT_URL, MINIMAX_KEY, "minimax-m3"))
    if DEEPSEEK_KEY:
        providers.append(("deepseek", DEEPSEEK_URL, DEEPSEEK_KEY, "deepseek-chat"))
    
    for name, url, key, model in providers:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 400,
                        "temperature": 0.7,
                    },
                )
                if resp.status_code != 200:
                    log(f"Minimax reason fail ({name}): {resp.status_code}")
                    continue
                
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip()
                
                # Store in persistent memory (already handled by send_message)
                log(f"Reason ({name}/{model}): {answer[:80]}...")
                
                # Auto-extract knowledge from this exchange (fire-and-forget)
                asyncio.create_task(_extract_knowledge_async(chat_id, role, text))
                
                return answer
                
        except Exception as e:
            log(f"Minimax reason error ({name}): {e}")
            continue
    
    return None


async def _extract_knowledge_async(chat_id: int, agent: str, text: str):
    """Background task: extract knowledge from user message."""
    try:
        facts = await extract_knowledge_from_message(
            _ghs_memory, chat_id, agent, text,
            deepseek_key=DEEPSEEK_KEY, deepseek_url=DEEPSEEK_URL
        )
        if facts:
            log(f"Extracted {len(facts)} knowledge facts from chat {chat_id}")
    except Exception:
        pass

CALL_SCRIPTS = {
    "auth_expired_urgent": (
        "Здравствуйте, {name}. Это Виктория из Garden of Joy. "
        "У вас истекла страховка — мы должны обновить, чтобы вы могли продолжать приходить. "
        "Когда вы сможете принести документы?"
    ),
    "auth_expiring_soon": (
        "Здравствуйте, {name}. Это Виктория из Garden of Joy. "
        "Напоминаю, что ваша страховка заканчивается {expiry_date}. "
        "Пожалуйста, принесите обновленные документы в ближайшее время."
    ),
    "absent_yesterday": (
        "Здравствуйте, {name}. Это Виктория из Garden of Joy. "
        "Мы заметили, что вас вчера не было. Всё в порядке? "
        "Придёте завтра?"
    ),
    "schedule_change": (
        "Здравствуйте, {name}. Это Виктория из Garden of Joy. "
        "У нас небольшое изменение в расписании на {day}. "
        "Сможете прийти?"
    ),
}

# ═══════════════════════════════════════════════════════════
# Masha: BBG Front-of-House Commands
# ═══════════════════════════════════════════════════════════

async def masha_menu(chat_id: int, category: str = None):
    bm = load_business_memory()
    foh = bm.get("foh", {})
    menu = foh.get("menu", {}).get("categories", [])

    if category:
        menu = [c for c in menu if category.lower() in c.get("name", "").lower()]

    if not menu:
        await send_message(chat_id, "Menu not available yet.")
        return

    text = "🍽️ *BBG Menu*\n\n"
    for cat in menu:
        text += f"*{cat['name']}*\n"
        for item in cat.get("items", []):
            text += f"  • {item['name']} — ${item['price']}"
            if item.get("description"):
                text += f" _({item['description']})_"
            text += "\n"
        text += "\n"

    promo = bm.get("business", {}).get("current_promotion", "Buy 2 Get 1 Free")
    text += f"🍺 *Promo:* {promo}"
    await send_message(chat_id, text)


async def masha_drinks(chat_id: int):
    bm = load_business_memory()
    foh = bm.get("foh", {})
    drinks = foh.get("drinks", {})

    text = "🍺 *BBG Drinks*\n\n"
    if drinks.get("draft_beers"):
        text += "*Draft Beers:*\n" + "\n".join(f"  • {b}" for b in drinks["draft_beers"]) + "\n\n"
    if drinks.get("cocktails"):
        text += "*Cocktails:*\n" + "\n".join(f"  • {c}" for c in drinks["cocktails"]) + "\n\n"
    if drinks.get("wine"):
        text += "*Wine:*\n" + "\n".join(f"  • {w}" for w in drinks["wine"]) + "\n\n"

    promo = bm.get("business", {}).get("current_promotion", "Buy 2 Get 1 Free")
    text += f"🍺 *Promo:* {promo}"
    await send_message(chat_id, text)


async def masha_hours(chat_id: int):
    bm = load_business_memory()
    business = bm.get("business", {})
    hours = business.get("hours", {})
    today = datetime.now().strftime("%A").lower()

    text = "⏰ *BBG Hours*\n\n"
    text += f"Today ({datetime.now().strftime('%A')}): *{hours.get(today, 'Closed')}*\n\n"
    text += "*Weekend Hours:*\n"
    text += f"  Saturday: {hours.get('saturday', '12:00 PM – 1:00 AM')}\n"
    text += f"  Sunday: {hours.get('sunday', '12:00 PM – 1:00 AM')}\n\n"
    text += f"📍 {business.get('location', 'Brighton Beach, Brooklyn')}"
    await send_message(chat_id, text)


async def masha_specials(chat_id: int):
    bm = load_business_memory()
    business = bm.get("business", {})
    promo = business.get("current_promotion", "Buy 2 Get 1 Free")
    hours = business.get("hours", {})

    text = (
        f"🎉 *Current Promotion*\n\n"
        f"🍺 *{promo}*\n\n"
        f"_All weekend long!_\n\n"
        f"📍 {business.get('location', 'Brighton Beach, Brooklyn')}\n"
        f"⏰ Sat: {hours.get('saturday', '12:00 PM – 1:00 AM')} • Sun: {hours.get('sunday', '12:00 PM – 1:00 AM')}"
    )
    await send_message(chat_id, text)


async def masha_events(chat_id: int):
    bm = load_business_memory()
    calendar = bm.get("content_calendar", {})
    today = datetime.now().strftime("%A").lower()

    text = f"📅 *BBG Events — {datetime.now().strftime('%A, %B %d')}*\n\n"

    if today in ("saturday", "sunday"):
        slot_key = f"{today}_morning" if today == "saturday" else "sunday"
        slot = calendar.get(slot_key, {}) if today == "saturday" else calendar.get("sunday", {})
        text += f"_{slot.get('tone', 'Great vibes today!')}_\n\n"
        text += f"🍺 {bm.get('business', {}).get('current_promotion', 'Buy 2 Get 1 Free')}\n"
        text += "🎯 Full menu: Slavic classics, burger bar, seafood, shawarma\n"
    else:
        text += "BBG is closed on weekdays.\n"
        text += "See you Saturday at 11:30 AM! 🌊\n"

    text += f"\n📍 Brighton Beach, Brooklyn"
    await send_message(chat_id, text)


async def masha_faq(chat_id: int, query: str = None):
    bm = load_business_memory()
    faqs = bm.get("foh", {}).get("faq", [])

    if query:
        query_lower = query.lower()
        matches = [f for f in faqs if query_lower in f["q"].lower() or query_lower in f["a"].lower()]
        if not matches:
            # Fuzzy: try keyword match
            matches = [f for f in faqs if any(word in f["q"].lower() or word in f["a"].lower()
                                               for word in query_lower.split())]
        faqs = matches

    if not faqs:
        await send_message(chat_id, "No FAQ matches found. Try: parking, reservations, kids, dogs, payment, groups")
        return

    if not query:
        text = "❓ *BBG FAQ*\n\n"
        for f in faqs[:10]:
            text += f"*Q:* {f['q']}\n*A:* {f['a']}\n\n"
    else:
        text = f"🔍 *FAQ: {query}*\n\n"
        for f in faqs[:3]:
            text += f"*Q:* {f['q']}\n*A:* {f['a']}\n\n"

    await send_message(chat_id, text)


async def masha_policy(chat_id: int, topic: str = None):
    bm = load_business_memory()
    policies = bm.get("foh", {}).get("policies", {})

    if topic:
        topic_lower = topic.lower()
        text = f"📋 *BBG Policy: {topic}*\n\n"
        found = False
        for key, val in policies.items():
            if topic_lower in key.lower() or topic_lower in val.lower():
                text += f"*{key.replace('_', ' ').title()}:*\n{val}\n\n"
                found = True
        if not found:
            text += f"No policy found for '{topic}'.\n\nAvailable: {', '.join(policies.keys())}"
    else:
        text = "📋 *BBG Policies*\n\n"
        for key, val in policies.items():
            text += f"*{key.replace('_', ' ').title()}:*\n{val}\n\n"

    await send_message(chat_id, text)


async def masha_flag(chat_id: int, issue: str):
    """Flag an issue to Kato."""
    log(f"MASHA FLAG: {issue}")
    # DM Kato
    kato_id = 5587703834
    await send_message(kato_id, f"⚠️ *Masha flagged an issue:*\n\n_{issue}_\n\n⏰ {datetime.now().strftime('%I:%M %p')}")
    await send_message(chat_id, f"✅ Flagged to Kato: _{issue}_")


async def masha_brain(chat_id: int, query: str = ""):
    """Search Obsidian vault for BBG knowledge."""
    if not query.strip():
        await send_message(chat_id,
            "🧠 *BBG Brain Search*\n\n"
            "I can search Kato's knowledge base for BBG info.\n"
            "Try: `/brain CRM migration` or `/brain voice agent` or just ask naturally.")
        return

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Search the Obsidian vault via API
            resp = await client.get(f"http://127.0.0.1:27125/vault/", params={"q": query})
            if resp.status_code != 200:
                # Fallback: static search of known BBG notes
                await masha_brain_static(chat_id, query)
                return

            results = resp.json()
            if not results or not isinstance(results, list):
                await masha_brain_static(chat_id, query)
                return

            text = f"🧠 *BBG Knowledge: \"{query[:60]}\"*\n\n"
            for r in results[:5]:
                note = r.get("note", r.get("path", "unknown"))
                snippet = r.get("snippet", r.get("content", ""))[:200]
                text += f"📄 *{note}*\n_{snippet}_\n\n"

            if not results or len(results) == 0:
                text += "_No results found in Obsidian vault._\n\n"
                text += "Try: CRM, voice agent, pipeline, social media, Masha, Elena"

            await send_message(chat_id, text)
    except Exception as e:
        log(f"Brain search error: {e}")
        await masha_brain_static(chat_id, query)


async def masha_brain_static(chat_id: int, query: str):
    """Fallback static brain search using known BBG notes."""
    q = query.lower()
    text = f"🧠 *BBG Knowledge: \"{query[:60]}\"*\n\n"

    if any(w in q for w in ["crm", "lead", "ghl", "gohighlevel", "migration"]):
        text += (
            "*CRM Migration Plan:*\n"
            "• Current: GoHighLevel ($97-297/mo)\n"
            "• Target: Masha (voice) + n8n (automation) + Twilio (SMS)\n"
            "• Gaps: missed-call SMS, consolidated inbox, auto-review requests\n\n"
            "• Competitor 'Lana' on GHL: 929-205-6408\n"
            "• Target: Port 929-205-6408 to Retell (Masha)\n"
        )

    if any(w in q for w in ["lana", "lead connector", "lead automation", "nurture"]):
        text += (
            "*LANA Software Analysis (researched June 19, 2026):*\n"
            "• Full name: Lead Automation Nurture Application\n"
            "• Website: lanasoftware.com.au — pricing $140-350 AUD/mo\n"
            "• Core: AI-powered CRM for trade businesses — captures ALL leads (calls, texts, emails, social)\n"
            "• Killer features: AI receptionist 24/7, auto-quote chasing, self-booking widget, post-job reviews\n"
            "• 5-step journey: Capture → Integrate → CRM → Book → Push\n"
            "• BBG can replicate: Masha as AI receptionist + self-booking + auto-review requests\n"
            "• Full analysis saved: ~/Desktop/REX/bbg_lana_analysis.md\n"
            "• Priority builds for BBG: (1) self-booking widget, (2) AI phone receptionist, (3) auto-review requests\n"
        )

    if any(w in q for w in ["voice", "masha", "retell", "phone", "agent"]):
        text += (
            "*Masha Voice Agent:*\n"
            "• Platform: Retell AI\n"
            "• Agent ID: agent_305ba9fdc34276c523766cd096\n"
            "• Voice: 11labs-Billy (needs bilingual RU/EN)\n"
            "• Language: Russian primary, code-switches to English\n"
            "• Phone: NONE — +164****3781 deregistered\n"
            "• Target: Port 929-205-6408 from Lead Connector\n\n"
        )

    if any(w in q for w in ["social", "instagram", "content", "pipeline", "posting"]):
        text += (
            "*BBG Social Pipeline:*\n"
            "• 28 skills in social-media category\n"
            "• Instagram: @boardwalkbeergarden (ID: 27923669980556036)\n"
            "• Hashtags: #BoardwalkBeerGarden #BrightonBeach #BrooklynEats\n"
            "• Default workflow: bbg-app-showdown (3-tool comparison)\n"
            "• Caption pipeline: bbg-multi-model-caption\n"
            "• Video: bbg-video-pipeline\n\n"
        )

    if any(w in q for w in ["pos", "clover", "payment", "register"]):
        text += (
            "*POS System:*\n"
            "• Clover POS: C051UQ41540458\n"
        )

    if any(w in q for w in ["adult", "hours", "age", "8pm", "policy"]):
        text += (
            "*BBG Age Policy:*\n"
            "• Adults-only after 8 PM\n"
            "• Family-friendly during daytime\n"
            "• No DJ until summer (as of June 2026)\n"
        )

    if text == f"🧠 *BBG Knowledge: \"{query[:60]}\"*\n\n":
        text += "_Nothing specific found in the brain. Try these topics:_\n"
        text += "• CRM / Lead Connector / Migration\n"
        text += "• Voice Agent / Masha / Retell\n"
        text += "• Social Media / Pipeline / Instagram\n"
        text += "• POS / Clover\n"
        text += "• Hours / Age Policy"

    await send_message(chat_id, text)


async def handle_ask(chat_id: int, question: str, role: str = "general"):
    """Handle /ask command — direct MiniMax reasoning."""
    if not question.strip():
        await send_message(chat_id, "Usage: /ask <your question>\n\nAsk me anything about BBG, GOJ, or operations!")
        return
    
    await send_message(chat_id, "🤔 Thinking...")
    answer = await minimax_reason(chat_id, question, role)
    if answer:
        await send_message(chat_id, answer)
    else:
        await send_message(chat_id, "❌ Sorry, I couldn't process that. The AI reasoning service may be unavailable.")

async def masha_loop(chat_id: int):
    """Check for new BBG info — Obsidian updates, menu changes, post history."""
    now = datetime.now().strftime("%I:%M %p — %A, %B %d")
    text = f"🔄 *Masha — 8-Hour Check*  |  {now}\n\n"

    # Check business memory freshness
    bm = load_business_memory()
    post_history = bm.get("post_history", [])
    last_post = post_history[-1]["ts"] if post_history else "never"
    text += f"📢 *Last social post:* {last_post}\n"
    text += f"📊 *Total posts tracked:* {len(post_history)}\n\n"

    # Check for new events
    today = datetime.now().strftime("%A").lower()
    calendar = bm.get("content_calendar", {})
    if today in ("friday", "saturday", "sunday"):
        slot = calendar.get(f"{today}_evening" if today == "friday" else 
                           (f"{today}_morning" if today == "saturday" and datetime.now().hour < 12 else
                            "saturday_afternoon" if today == "saturday" else "sunday"), {})
        text += f"📅 *Today's strategy:* {slot.get('goal', 'General')}\n"
        text += f"🎯 *Tone:* {slot.get('tone', 'Energetic')}\n\n"
    else:
        text += "📅 *Weekday:* BBG closed. Teaser/throwback content only.\n\n"

    # Check if Obsidian has BBG updates (via vault API)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("http://127.0.0.1:27125/health")
            if resp.status_code == 200:
                text += "🧠 *Obsidian brain:* Connected ✅\n"
            else:
                text += "🧠 *Obsidian brain:* Offline ❌\n"
    except Exception:
        text += "🧠 *Obsidian brain:* Offline ❌\n"

    text += f"\n⏰ _Next check in 8 hours_"
    await send_message(chat_id, text)


async def masha_post(chat_id: int, args: str):
    """Masha posts to social media."""
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id,
            "Usage: `/post [ig|tg|both] <message>`\n\n"
            "Examples:\n"
            "`/post ig World Cup tonight! Half off drafts ⚽🍺`\n"
            "`/post both We're open! Come through 🌊`")
        return

    platform_word = parts[0].lower()
    message = parts[1].strip()

    if platform_word in ("ig", "instagram"):
        platforms = ["instagram"]
    elif platform_word in ("tg", "telegram"):
        platforms = ["telegram"]
    elif platform_word == "both":
        platforms = ["instagram", "telegram"]
    else:
        platforms = ["instagram"]
        message = args.strip()

    await send_message(chat_id, f"📢 Posting to *{', '.join(platforms)}*...\n\n_{message[:200]}_")

    for platform in platforms:
        caption = get_branded_caption("generic", message)
        entity = "BBG" if platform == "instagram" else "GHS"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                draft = await client.post(f"{SOCIAL_ROUTER}/draft", json={
                    "topic": message[:150],
                    "platforms": [platform],
                    "context": "Posted by Masha via GHS Staff Bot",
                    "entity": entity,
                })
                if draft.status_code != 200:
                    await send_message(chat_id, f"❌ Draft failed for {platform}: {draft.status_code}")
                    continue

                drafts = draft.json()
                created = drafts.get("created", [])
                if not created:
                    await send_message(chat_id, f"❌ No draft created for {platform}")
                    continue

                draft_id = created[0]["draft_id"]
                await client.post(f"{SOCIAL_ROUTER}/draft/{draft_id}/approve")
                exec_resp = await client.post(f"{SOCIAL_ROUTER}/post/{draft_id}/execute")

                if exec_resp.status_code == 200:
                    await send_message(chat_id,
                        f"✅ *Posted to {platform}!*\nDraft: `{draft_id}`\n\n_{caption[:200]}_")
                else:
                    await send_message(chat_id, f"❌ Execute failed for {platform}: {exec_resp.status_code}")
        except Exception as e:
            log(f"Masha post error ({platform}): {e}")
            await send_message(chat_id, f"❌ Error posting to {platform}: {e}")


async def masha_help(chat_id: int):
    text = (
        "🤖 *Masha — BBG Front of House*\n\n"
        "*Commands:*\n"
        "`/menu [category]` — Full menu or filter by category\n"
        "`/drinks` — Draft beers, cocktails, wine\n"
        "`/hours` — Today's hours\n"
        "`/specials` — Current promotions\n"
        "`/events` — Today's events & sports\n"
        "`/faq [keyword]` — Search FAQs (parking, kids, reservations)\n"
        "`/policy [topic]` — Look up a policy\n"
        "`/flag <issue>` — Report an issue to Kato\n"
        "`/post ig|tg|both <msg>` — Post to social media\n"
        "`/brain <query>` — Search BBG knowledge (Obsidian)\n"
        "`/reservations` — Check for new owner.com bookings\n\n"
        "*Or just ask naturally:*\n"
        "\"what time do we close?\" \"do we have burgers?\" \"kids allowed?\" \"CRM plan?\" \"voice agent status?\""
    )
    await send_message(chat_id, text)


# ═══════════════════════════════════════════════════════════
# Masha: Intent Detection
# ═══════════════════════════════════════════════════════════

MASHA_INTENTS = {
    "menu": ["menu", "food", "what to eat", "burger", "pelmeni", "borscht", "chebureki", "dish", "meal"],
    "drinks": ["drink", "beer", "draft", "tap", "cocktail", "wine", "on tap", "drinks"],
    "hours": ["close", "closing", "open", "hours", "time", "late", "tonight", "until"],
    "specials": ["special", "promo", "deal", "discount", "offer", "free", "price"],
    "events": ["game", "match", "sports", "world cup", "event", "playing", "showing"],
    "faq": ["reservation", "parking", "kids", "dog", "vegetarian", "card", "payment", "table", "allowed"],
    "policy": ["policy", "rule", "permitted", "can i", "do you allow"],
    "post": ["post", "announce", "put on", "share", "broadcast", "publish"],
    "flag": ["out of", "ran out", "broken", "not working", "problem", "issue", "missing"],
    "brain": ["crm", "voice agent", "pipeline", "strategy", "plan", "retell", "lead connector", "ghl", "migration", "social media plan", "competitor", "lana"],
    "reservations": ["booking", "booked", "owner.com", "table for", "new reservation", "check reservations"],
}


def detect_masha_intent(text: str) -> tuple:
    t = text.lower()
    for intent, keywords in MASHA_INTENTS.items():
        if any(kw in t for kw in keywords):
            return (intent, text)
    return ("unknown", text)


async def route_masha_intent(chat_id: int, intent: str, query: str):
    if intent == "menu":
        # Extract category if mentioned
        for cat in ["burger", "slavic", "seafood", "shawarma", "dessert"]:
            if cat in query.lower():
                await masha_menu(chat_id, cat)
                return
        await masha_menu(chat_id)
    elif intent == "drinks":
        await masha_drinks(chat_id)
    elif intent == "hours":
        await masha_hours(chat_id)
    elif intent == "specials":
        await masha_specials(chat_id)
    elif intent == "events":
        await masha_events(chat_id)
    elif intent == "faq":
        await masha_faq(chat_id, query)
    elif intent == "policy":
        # Extract topic
        topic = query.lower().replace("policy", "").replace("rule", "").strip()
        await masha_policy(chat_id, topic or None)
    elif intent == "post":
        await masha_post(chat_id, query)
    elif intent == "flag":
        await masha_flag(chat_id, query)
    elif intent == "brain":
        await masha_brain(chat_id, query)
    elif intent == "reservations":
        await masha_check_reservations(chat_id)
    else:
        # Keyword didn't match — try LLM intent routing
        llm_intent = await llm_understand(chat_id, query, "masha")
        if llm_intent and llm_intent != "unknown":
            await route_masha_intent(chat_id, llm_intent, _last_llm.get(chat_id, query))
        else:
            # Intent routing failed — use MiniMax reasoning
            answer = await minimax_reason(chat_id, query, "masha")
            if answer:
                await send_message(chat_id, answer)
            else:
                await send_message(chat_id, "I didn't catch that. Try `/help` to see what I can do!")


async def route_masha_command(chat_id: int, cmd: str, args: str):
    handlers = {
        "/menu": lambda: masha_menu(chat_id, args.strip() if args else None),
        "/drinks": lambda: masha_drinks(chat_id),
        "/hours": lambda: masha_hours(chat_id),
        "/specials": lambda: masha_specials(chat_id),
        "/events": lambda: masha_events(chat_id),
        "/faq": lambda: masha_faq(chat_id, args.strip() if args else None),
        "/policy": lambda: masha_policy(chat_id, args.strip() if args else None),
        "/flag": lambda: masha_flag(chat_id, args.strip()),
        "/post": lambda: masha_post(chat_id, args.strip()),
        "/brain": lambda: masha_brain(chat_id, args.strip()),
        "/voicecall": lambda: masha_voicecall(chat_id, args),
        "/reservations": lambda: masha_check_reservations(chat_id),
        "/tally": lambda: masha_show_tally(chat_id),
        "/ask": lambda: handle_ask(chat_id, args.strip(), "masha"),
        "/loop": lambda: masha_loop(chat_id),
        "/help": lambda: masha_help(chat_id),
        "/start": lambda: masha_help(chat_id),
    }
    handler = handlers.get(cmd)
    if handler:
        await handler()
    else:
        await send_message(chat_id, f"Unknown command: `{cmd}`. Try `/help`.")

# ═══════════════════════════════════════════════════════════
# Viktoriya: GOJ Front Desk — Attendance & Client Lookup
# ═══════════════════════════════════════════════════════════

def _goj_query(query: str, params=()):
    """Run a read-only query against auth_tracker.db."""
    if not AUTH_DB.exists():
        return None, "auth_tracker.db not found"
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return rows, None
    except Exception as e:
        return None, str(e)


async def viktoriya_attendance(chat_id: int):
    rows, err = _goj_query("""
        SELECT log_date, COUNT(*) as cnt, 
               SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) as present
        FROM attendance_log
        WHERE log_date >= date('now', '-1 days')
        GROUP BY log_date
        ORDER BY log_date DESC
    """)
    if err:
        await send_message(chat_id, f"❌ Could not fetch attendance: {err}")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_data = next((r for r in rows if r["log_date"] == today), None)
    yesterday_data = next((r for r in rows if r["log_date"] == yesterday), None)

    text = "📋 *Today's Attendance*\n\n"
    if today_data:
        text += (
            f"Date: *{today}*\n"
            f"Present: *{today_data['present']}*\n"
            f"Total logged: *{today_data['cnt']}*\n\n"
        )
    else:
        text += f"Date: *{today}*\n_No attendance logged yet._\n\n"

    if yesterday_data:
        text += f"Yesterday: *{yesterday_data['present']}* present of *{yesterday_data['cnt']}* logged"

    await send_message(chat_id, text)


async def viktoriya_client(chat_id: int, name: str):
    if not name.strip():
        await send_message(chat_id, "Usage: `/client <name>` — partial name works")
        return

    rows, err = _goj_query("""
        SELECT c.name, c.phone, c.shift, c.active,
               a.status as auth_status, a.service_end_date,
               a.authorized_days_per_week
        FROM clients c
        LEFT JOIN (
            SELECT client_name, status, service_end_date, authorized_days_per_week,
                   ROW_NUMBER() OVER (PARTITION BY client_name ORDER BY last_updated_timestamp DESC) as rn
            FROM authorization
        ) a ON c.name = a.client_name AND a.rn = 1
        WHERE c.name LIKE ?
        ORDER BY c.name
        LIMIT 5
    """, (f"%{name}%",))

    if err:
        await send_message(chat_id, f"❌ Error: {err}")
        return

    if not rows:
        await send_message(chat_id, f"No client matching '*{name}*' found.")
        return

    text = f"🔍 *Client Lookup: {name}*\n\n"
    for r in rows:
        text += (
            f"*{r['name']}*\n"
            f"  📞 {r['phone'] or 'N/A'}\n"
            f"  Auth: `{r['auth_status'] or 'N/A'}`\n"
            f"  Expires: {r['service_end_date'] or 'N/A'}\n"
            f"  Shift: {r['shift'] or 'N/A'} | Active: {'✅' if r['active'] else '❌'}\n\n"
        )
    await send_message(chat_id, text)


# ═══════════════════════════════════════════════════════════
# Masha: Reservation Watcher — polls Gmail for owner.com bookings
# ═══════════════════════════════════════════════════════════

RESERVATION_KEYWORDS = ["owner.com", "new reservation", "booking confirmed", "new booking",
                        "reservation request", "table for", "booked at boardwalk"]

async def masha_check_reservations(chat_id: int):
    """Check olympusbbg@gmail.com for new owner.com reservation emails."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"http://127.0.0.1:9000/api/gmail/inbox?limit=10",
            )
            if resp.status_code != 200:
                await send_message(chat_id, "❌ Could not reach Gmail. Hub may be down.")
                return

            data = resp.json()
            threads = data.get("threads", [])

            if not threads:
                await send_message(chat_id, "📭 No recent emails in olympusbbg inbox.")
                return

            found = []
            for t in threads[:10]:
                subject = (t.get("subject") or "").lower()
                sender = (t.get("from") or "").lower()
                snippet = (t.get("snippet") or "").lower()

                is_reservation = any(
                    kw in subject or kw in sender or kw in snippet
                    for kw in RESERVATION_KEYWORDS
                )
                if is_reservation:
                    found.append(t)

            if not found:
                await send_message(chat_id,
                    "✅ No new reservation emails found in the last 10 inbox messages.\n\n"
                    "_Checked olympusbbg@gmail.com_")
                return

            # Format results
            text = f"📋 *Reservation Watcher — {len(found)} booking email(s)*\n\n"
            for t in found[:5]:
                subject = t.get("subject", "No subject")[:80]
                sender = t.get("from", "Unknown")[:60]
                date = t.get("date", "")[:16]
                snippet = t.get("snippet", "")[:120]
                text += (
                    f"📧 *{subject}*\n"
                    f"   From: {sender}\n"
                    f"   Date: {date}\n"
                    f"   _{snippet}_\n\n"
                )

            text += "_Open owner.com to confirm details._"
            await send_message(chat_id, text)

            # Auto-relay to Kato via Hermes if new bookings found
            if found:
                await masha_relay_to_hermes(
                    f"📋 Found {len(found)} new booking email(s) in olympusbbg. "
                    f"First: {found[0].get('subject', 'Unknown')[:60]}. "
                    f"Should I confirm these or flag anything?"
                )

    except Exception as e:
        log(f"Masha reservation check error: {e}")
        await send_message(chat_id, f"❌ Reservation check failed: {e}")


# ═══════════════════════════════════════════════════════════
# Masha ↔ Hermes Chat Relay
# ═══════════════════════════════════════════════════════════
RELAY_FILE = Path.home() / "Desktop" / "REX" / "masha_relay.json"
TALLY_FILE = Path.home() / "Desktop" / "REX" / "bbg_reservation_tally.json"


def _load_relay() -> dict:
    if RELAY_FILE.exists():
        try:
            return json.loads(RELAY_FILE.read_text())
        except Exception:
            pass
    return {"pending": [], "responses": [], "last_read_by_hermes": ""}


def _save_relay(data: dict):
    RELAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    RELAY_FILE.write_text(json.dumps(data, indent=2, default=str))


def _load_tally() -> dict:
    if TALLY_FILE.exists():
        try:
            return json.loads(TALLY_FILE.read_text())
        except Exception:
            pass
    return {"days": {}, "last_updated": ""}


def _save_tally(data: dict):
    TALLY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    TALLY_FILE.write_text(json.dumps(data, indent=2, default=str))


def update_reservation_tally(date_str: str, bookings: int, guests: int, source: str = "email"):
    """Increment the daily reservation tally."""
    tally = _load_tally()
    day = tally["days"].get(date_str, {"bookings": 0, "guests": 0, "sources": []})

    # Only increment if these are new (dedup by checking if source already recorded)
    day["bookings"] = bookings if bookings > day["bookings"] else day["bookings"]
    day["guests"] = max(day.get("guests", 0), guests)
    if source not in day.get("sources", []):
        day.setdefault("sources", []).append(source)

    tally["days"][date_str] = day
    _save_tally(tally)
    return day


def get_reservation_tally(days_ahead: int = 14) -> dict:
    """Get reservation counts for upcoming days."""
    from datetime import date, timedelta
    tally = _load_tally()

    result = {}
    today = date.today()
    for i in range(days_ahead):
        day = today + timedelta(days=i)
        key = day.isoformat()
        day_data = tally["days"].get(key, {"bookings": 0, "guests": 0})
        dow = day.strftime("%a")
        result[key] = {
            "dow": dow,
            "date": key,
            "bookings": day_data.get("bookings", 0),
            "guests": day_data.get("guests", 0),
        }

    return result


async def masha_relay_to_hermes(message: str):
    """Masha sends a message to Kato through the Hermes relay."""
    data = _load_relay()
    data["pending"].append({
        "from": "masha",
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "needs_confirmation": True,
    })
    _save_relay(data)
    log(f"Masha → Hermes relay: {message[:80]}")


async def masha_relay_poll_responses(chat_id: int):
    """Masha checks if Hermes/Kato responded to any relay messages."""
    data = _load_relay()
    responses = data.get("responses", [])
    if not responses:
        return

    for resp in responses:
        await send_message(chat_id,
            f"📩 *Response from Kato:*\n{resp.get('message', '')[:500]}")

    data["responses"] = []
    _save_relay(data)
    log(f"Masha processed {len(responses)} relay response(s)")


async def masha_show_tally(chat_id: int):
    """Show daily reservation tally for the next 14 days."""
    tally = get_reservation_tally(14)

    text = "📊 *BBG Reservation Tally — Next 14 Days*\n\n"
    # Only show Fri-Sun (BBG operating days)
    weekend_days = {day for day, data in tally.items() if data["dow"] in ("Fri", "Sat", "Sun")}
    weekday_days = {day for day, data in tally.items() if data["dow"] not in ("Fri", "Sat", "Sun")}

    if weekend_days:
        text += "*Weekends:*\n"
        for day, data in tally.items():
            if day in weekend_days:
                bar = "█" * min(data["guests"], 20) if data["guests"] > 0 else "·"
                text += (
                    f"  {data['dow']} {data['date'][5:]}: "
                    f"`{data['bookings']:>3} bookings`  "
                    f"`{data['guests']:>3} guests`  {bar}\n"
                )

    total_bookings = sum(d["bookings"] for d in tally.values())
    total_guests = sum(d["guests"] for d in tally.values())

    text += (
        f"\n*Totals:* `{total_bookings} bookings` · `{total_guests} guests`\n\n"
        "_Email-sourced only. Check owner.com for walk-ins._"
    )
    await send_message(chat_id, text)


async def viktoriya_expiring(chat_id: int, days: int = 30):
    rows, err = _goj_query("""
        SELECT c.name, c.phone, a.service_end_date, a.status,
               CAST(julianday(a.service_end_date) - julianday('now') AS INTEGER) as days_left
        FROM clients c
        JOIN (
            SELECT client_name, service_end_date, status,
                   ROW_NUMBER() OVER (PARTITION BY client_name ORDER BY last_updated_timestamp DESC) as rn
            FROM authorization
            WHERE status IN ('ACTIVE', 'EXPIRING')
        ) a ON c.name = a.client_name AND a.rn = 1
        WHERE a.service_end_date BETWEEN date('now') AND date('now', '+' || ? || ' days')
        ORDER BY a.service_end_date ASC
    """, (days,))

    if err:
        await send_message(chat_id, f"❌ Error: {err}")
        return

    if not rows:
        await send_message(chat_id, f"✅ No clients expiring within {days} days.")
        return

    text = f"⚠️ *Auth Expiring — {len(rows)} clients within {days} days*\n\n"
    for r in rows:
        emoji = "🔴" if r["days_left"] <= 7 else "🟡" if r["days_left"] <= 14 else "🟢"
        text += (
            f"{emoji} *{r['name']}* — {r['days_left']} days left\n"
            f"   Expires: {r['service_end_date']} | Status: `{r['status']}`\n"
            f"   📞 {r['phone'] or 'N/A'}\n\n"
        )
    await send_message(chat_id, text)


async def viktoriya_checkin(chat_id: int, name: str):
    if not name.strip():
        await send_message(chat_id, "Usage: `/checkin <client name>`")
        return

    # Look up client first
    rows, err = _goj_query(
        "SELECT client_id, name FROM clients WHERE name LIKE ? LIMIT 1",
        (f"%{name}%",)
    )
    if err or not rows:
        await send_message(chat_id, f"Client '*{name}*' not found.")
        return

    client = rows[0]
    today = datetime.now().strftime("%Y-%m-%d")

    # Check if already checked in
    existing, _ = _goj_query(
        "SELECT rowid FROM attendance_log WHERE client_name = ? AND log_date = ?",
        (client["name"], today)
    )
    if existing:
        await send_message(chat_id, f"ℹ️ *{client['name']}* is already checked in today.")
        return

    # Insert attendance record
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.execute(
            "INSERT INTO attendance_log (log_date, client_name, status) VALUES (?, ?, 'present')",
            (today, client["name"])
        )
        conn.commit()
        conn.close()
        await send_message(chat_id, f"✅ *{client['name']}* checked in — {today}")
    except Exception as e:
        await send_message(chat_id, f"❌ Check-in failed: {e}")


async def viktoriya_report(chat_id: int):
    # Attendance
    rows, _ = _goj_query("""
        SELECT COUNT(*) as cnt, SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) as present
        FROM attendance_log WHERE log_date = date('now')
    """)

    # Expiring count
    exp_rows, _ = _goj_query("""
        SELECT COUNT(*) as cnt FROM authorization
        WHERE status IN ('ACTIVE', 'EXPIRING')
          AND service_end_date BETWEEN date('now') AND date('now', '+30 days')
    """)

    # Today's calls
    call_rows, _ = _goj_query("""
        SELECT status, COUNT(*) as cnt FROM victoria_call_log
        WHERE date(created_at) = date('now')
        GROUP BY status
    """)

    today_str = datetime.now().strftime("%A, %B %d, %Y")
    text = f"📊 *Daily Report — {today_str}*\n\n"

    if rows:
        text += f"*Attendance:* {rows[0]['present']} present of {rows[0]['cnt']} logged\n"
    if exp_rows:
        text += f"*Auth expiring (30d):* {exp_rows[0]['cnt']} clients\n"
    if call_rows:
        text += "*Calls today:*\n"
        for r in call_rows:
            text += f"  {r['status']}: {r['cnt']}\n"
    text += f"\n⏰ Generated: {datetime.now().strftime('%I:%M %p')}"
    await send_message(chat_id, text)


async def viktoriya_help(chat_id: int):
    text = (
        "🤖 *Viktoriya — GOJ Front Desk*\n\n"
        "*Commands:*\n"
        "`/attendance` — Today's attendance counts\n"
        "`/client <name>` — Look up a client\n"
        "`/expiring [days]` — Auths expiring soon (default 30 days)\n"
        "`/checkin <name>` — Mark client as present today\n"
        "`/schedule <msg>` — Update schedule: absent, coming, day change\n"
        "`/report` — Daily summary\n"
        "`/calls` — Today's call list\n"
        "`/callreport` — Today's call outcomes\n"
        "`/callhistory` — Last 7 days of calls\n"
        "`/callscript <type>` — Show call script\n"
        "`/brain <query>` — Search GOJ procedures\n"
        "`/loop` — 8-hour check for new info\n\n"
        "*Or ask naturally:*\n"
        "\"how many here today?\" \"who's expiring?\" \"look up Maria\"\n"
        "\"Maria is not coming Thursday\" \"Ivan switched from Monday to Wednesday\""
    )
    await send_message(chat_id, text)


async def viktoriya_loop(chat_id: int):
    """8-hour check for new GOJ info."""
    now = datetime.now().strftime("%I:%M %p — %A, %B %d")
    text = f"🔄 *Viktoriya — 8-Hour Check*  |  {now}\n\n"

    # Attendance snapshot
    rows, err = _goj_query("""
        SELECT COUNT(*) as scheduled,
               SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) as present
        FROM attendance_log WHERE log_date = date('now')
    """)
    if rows and rows[0]:
        text += f"📋 *Today:* {rows[0]['present']} present of {rows[0]['scheduled']} scheduled\n"

    # Expiring count
    rows2, _ = _goj_query("""
        SELECT COUNT(*) as cnt FROM authorization
        WHERE status IN ('ACTIVE','EXPIRING')
          AND service_end_date BETWEEN date('now') AND date('now','+30 days')
    """)
    if rows2:
        text += f"⚠️ *Expiring (30d):* {rows2[0]['cnt']} clients\n"

    # Today's calls
    rows3, _ = _goj_query("""
        SELECT COUNT(*) as cnt FROM victoria_call_log
        WHERE date(created_at) = date('now')
    """)
    if rows3:
        text += f"📞 *Today's calls:* {rows3[0]['cnt']}\n\n"
    else:
        text += "\n"

    # Check bot connectivity
    text += "🔌 *Services:*\n"
    if AUTH_DB.exists():
        text += "  • auth_tracker.db: Connected ✅\n"
    else:
        text += "  • auth_tracker.db: Missing ❌\n"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{REX_BASE}/health")
            text += "  • REX backend: Connected ✅\n" if resp.status_code == 200 else "  • REX backend: Down ❌\n"
    except Exception:
        text += "  • REX backend: Down ❌\n"

    text += f"\n⏰ _Next check in 8 hours_"
    await send_message(chat_id, text)


# ═══════════════════════════════════════════════════════════
# Viktoriya: Schedule Updates (not coming, coming, day change)
# ═══════════════════════════════════════════════════════════

DAY_MAP_REV = {"monday": "M", "tuesday": "T", "wednesday": "W", "thursday": "TH",
               "friday": "F", "saturday": "SA", "sunday": "SU",
               "mon": "M", "tue": "T", "tues": "T", "wed": "W", "thu": "TH",
               "thur": "TH", "thurs": "TH", "fri": "F", "sat": "SA", "sun": "SU",
               "m": "M", "t": "T", "w": "W", "th": "TH", "f": "F", "sa": "SA", "su": "SU"}

async def viktoriya_schedule_update(chat_id: int, text: str):
    """
    LLM-powered schedule change: understands "Maria is not coming tomorrow"
    or "Ivan switched from Monday to Thursday" and updates the DB.
    Updates both clients.day_X_actual AND pending_schedule_changes for audit trail.
    """
    if not text.strip():
        await send_message(chat_id,
            "📝 *Update Schedule*\n\n"
            "Tell me what changed:\n"
            "• \"Petr can't come on Thursday\"\n"
            "• \"Maria is coming Friday\"\n"
            "• \"Ivan switched from Monday to Wednesday\"\n\n"
            "I'll update the sign-in sheets automatically.")
        return

    # If text looks like it was already parsed by keyword match but we need LLM extraction
    if not DEEPSEEK_KEY:
        await send_message(chat_id,
            "⚠️ LLM intelligence not available (no API key). "
            "Use `/client <name>` to look up, then tell me the day and action.")
        return

    await send_message(chat_id, "⏳ One moment, updating the schedule...")

    extraction_prompt = f"""Extract schedule change information from this message. Return ONLY JSON.

User message: "{text}"

Determine:
- client_name: the person's name mentioned
- change_type: one of "absent" (not coming), "present" (is coming), or "day_change" (switching days)
- target_day: the day affected (monday, tuesday, wednesday, thursday, friday, saturday)
- old_day: only for day_change — the day they're switching FROM
- reason: brief reason if mentioned (sick, appointment, etc.) or empty

Return EXACTLY: {{"client_name": "...", "change_type": "...", "target_day": "...", "old_day": "...", "reason": "..."}}
JSON ONLY:"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": extraction_prompt}],
                    "max_tokens": 200,
                    "temperature": 0,
                },
            )
            if resp.status_code != 200:
                await send_message(chat_id, f"❌ LLM error: {resp.status_code}")
                return

            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            import re as _re
            match = _re.search(r'\{[^}]+\}', content)
            if not match:
                await send_message(chat_id,
                    "❌ Could not extract schedule info. Try being more specific:\n"
                    "\"Maria Petrova is not coming on Thursday\"")
                return

            result = json.loads(match.group())
            client_name = result.get("client_name", "").strip()
            change_type = result.get("change_type", "absent")
            target_day_raw = result.get("target_day", "").strip().lower()
            old_day_raw = result.get("old_day", "").strip().lower()
            reason = result.get("reason", "").strip()

    except Exception as e:
        log(f"Schedule LLM error: {e}")
        await send_message(chat_id, f"❌ Could not process: {e}")
        return

    if not client_name:
        await send_message(chat_id, "❌ I didn't catch a name. Who are we talking about?")
        return

    # Map day to DB column
    target_day_code = DAY_MAP_REV.get(target_day_raw, "")
    old_day_code = DAY_MAP_REV.get(old_day_raw, "") if old_day_raw else ""

    if not target_day_code:
        await send_message(chat_id,
            f"❌ I didn't recognize the day \"{target_day_raw}\". "
            f"Use: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday")
        return

    # Look up client in DB
    rows, err = _goj_query(
        "SELECT client_id, name, shift FROM clients WHERE name LIKE ? AND active=1 LIMIT 5",
        (f"%{client_name}%",)
    )
    if err or not rows:
        await send_message(chat_id,
            f"❌ Client \"{client_name}\" not found in GOJ database.")
        return

    # If multiple matches, use first exact match or first partial
    match = next((r for r in rows if r["name"].lower() == client_name.lower()), rows[0])
    client_id = match["client_id"]
    matched_name = match["name"]

    # Build the DB column name
    col = f"day_{target_day_code}_actual"

    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.execute("PRAGMA journal_mode=WAL")

        if change_type == "absent":
            # Set day_X_actual = 0 (not coming)
            conn.execute(f"UPDATE clients SET {col}=0 WHERE client_id=?", (client_id,))
            reason_str = f" — {reason}" if reason else ""
            action_msg = f"❌ *{matched_name}* marked as NOT coming on {target_day_raw.title()}{reason_str}"

        elif change_type == "present":
            # Set day_X_actual = 1 (is coming)
            conn.execute(f"UPDATE clients SET {col}=1 WHERE client_id=?", (client_id,))
            reason_str = f" — {reason}" if reason else ""
            action_msg = f"✅ *{matched_name}* added to {target_day_raw.title()}{reason_str}"

        elif change_type == "day_change":
            # Set old day to 0, new day to 1
            old_col = f"day_{old_day_code}_actual"
            conn.execute(f"UPDATE clients SET {old_col}=0, {col}=1 WHERE client_id=?", (client_id,))
            action_msg = f"🔄 *{matched_name}* moved from {old_day_raw.title()} → {target_day_raw.title()}"

        else:
            conn.close()
            await send_message(chat_id,
                f"❌ Unknown change type \"{change_type}\". Use absent/present/day_change.")
            return

        # Insert audit entry into pending_schedule_changes
        today_str = datetime.now().strftime("%Y-%m-%d")
        reason_note = reason if reason else ""
        source_note = f"Source: {text[:150]}"
        note_full = f"{reason_note} | {source_note}" if reason_note else source_note
        conn.execute("""
            INSERT INTO pending_schedule_changes
            (client_id, client_name, change_type, field_changed, old_value, new_value,
             changed_by, confirmed, note, created_at, day_key)
            VALUES (?, ?, ?, ?, ?, ?, 'Viktoriya (LLM)', 0, ?, ?, ?)
        """, (
            client_id, matched_name, change_type,
            "attendance_schedule",
            f"{old_day_code}:present" if change_type == "day_change" else f"{target_day_code}:{change_type}",
            f"{target_day_code}:{'absent' if change_type == 'absent' else 'present'}",
            note_full,
            datetime.now().isoformat(),
            target_day_code
        ))

        conn.commit()
        conn.close()

        # Confirm to user
        day_label = {"M": "Monday", "T": "Tuesday", "W": "Wednesday",
                     "TH": "Thursday", "F": "Friday", "SA": "Saturday", "SU": "Sunday"}
        next_sheet = f"\n\n📋 Sign-in sheet for {day_label.get(target_day_code, target_day_raw)} will reflect this change."
        await send_message(chat_id, action_msg + next_sheet)

    except Exception as e:
        log(f"Schedule update DB error: {e}")
        await send_message(chat_id, f"❌ Database error: {e}")


# ═══════════════════════════════════════════════════════════
# Viktoriya: Intent Detection
# ═══════════════════════════════════════════════════════════

VIKTORIYA_INTENTS = {
    "attendance": ["here today", "attendance", "count", "how many", "present", "today"],
    "client": ["who is", "look up", "find", "search", "client", "status of", "phone"],
    "expiring": ["expiring", "expire", "renewal", "renew", "due"],
    "calls": ["call list", "call today", "who to call", "calls", "call"],
    "report": ["report", "summary", "daily", "morning", "overview"],
    "checkin": ["check in", "arrived", "here", "came in", "present"],
    "brain": ["process", "procedure", "policy", "how do i", "how does", "rule", "protocol", "what is the", "explain"],
    "schedule": ["not coming", "can't come", "won't be in", "sick", "absent", "changing day", "switch day",
                 "no longer coming", "skipping", "will come", "can come", "is coming",
                 "change day", "different day", "instead of", "moved to"],
}


def detect_viktoriya_intent(text: str) -> tuple:
    t = text.lower()
    for intent, keywords in VIKTORIYA_INTENTS.items():
        if any(kw in t for kw in keywords):
            return (intent, text)
    return ("unknown", text)


async def route_viktoriya_intent(chat_id: int, intent: str, query: str):
    if intent == "attendance":
        await viktoriya_attendance(chat_id)
    elif intent == "client":
        name = query.lower()
        for word in ["who is", "look up", "find", "search", "client", "status of", "phone"]:
            name = name.replace(word, "")
        await viktoriya_client(chat_id, name.strip())
    elif intent == "expiring":
        await viktoriya_expiring(chat_id)
    elif intent == "calls":
        await viktoriya_calls(chat_id)
    elif intent == "report":
        await viktoriya_report(chat_id)
    elif intent == "checkin":
        name = query.replace("check in", "").replace("arrived", "").replace("here", "").strip()
        await viktoriya_checkin(chat_id, name)
    elif intent == "brain":
        await viktoriya_brain(chat_id, query)
    elif intent in ("schedule", "schedule_update"):
        await viktoriya_schedule_update(chat_id, query)
    else:
        # Keyword didn't match — try LLM intent routing
        llm_intent = await llm_understand(chat_id, query, "viktoriya")
        if llm_intent and llm_intent != "unknown":
            await route_viktoriya_intent(chat_id, llm_intent, _last_llm.get(chat_id, query))
        else:
            # Intent routing failed — use MiniMax reasoning
            answer = await minimax_reason(chat_id, query, "viktoriya")
            if answer:
                await send_message(chat_id, answer)
            else:
                await send_message(chat_id, "I didn't catch that. Try `/help` to see what I can do!")


# ═══════════════════════════════════════════════════════════
# Voice-agent triggers (Victoria=GOJ, Masha=BBG) — GATED
# Frozen configs untouched: Victoria = agent_8a326510567e7dc3e2dc5221df (11labs-Kate),
# Masha = agent_305ba9fdc34276c523766cd096 (11labs-victoria). This code only *invokes*
# the existing callers — it never edits agent/voice config.
# Preview (dry-run) by default; a LIVE call requires the word "confirm".
# ═══════════════════════════════════════════════════════════
CALLER_PYTHON   = str(Path.home() / "Desktop/REX/.venv-ocr/bin/python")
VICTORIA_CALLER = str(Path.home() / "Desktop/REX/goj_victoria_caller.py")
MASHA_CALLER    = str(Path.home() / "Desktop/REX/bbg_masha_caller.py")
VOICE_DB        = Path.home() / "Documents/goj files/proprietary/goj_proprietary.db"


def _voice_parse_confirm(args: str):
    """If the first token is 'confirm', return (True, rest); else (False, args)."""
    toks = args.strip().split(maxsplit=1)
    if toks and toks[0].lower() == "confirm":
        return True, (toks[1].strip() if len(toks) > 1 else "")
    return False, args.strip()


def _voice_valid_phone(s: str) -> bool:
    digits = s.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    core = digits[1:] if digits.startswith("+") else digits
    return core.isdigit() and 10 <= len(core) <= 15


def _voice_redact(s: str) -> str:
    """Strip token-like strings before echoing subprocess output back to Telegram."""
    import re
    s = re.sub(r"key_[A-Za-z0-9]{8,}", "key_***", s)
    s = re.sub(r"\d{6,}:[A-Za-z0-9_-]{20,}", "***:***", s)  # Telegram bot tokens
    return s


async def _voice_spawn(argv, timeout=120):
    """Run a caller subprocess; return (rc, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (proc.returncode,
                out.decode(errors="replace").strip(),
                err.decode(errors="replace").strip())
    except asyncio.TimeoutError:
        return -1, "", "timed out (the call/batch may still be running in the background)"
    except Exception as e:
        return -1, "", f"{type(e).__name__}: {e}"


async def _voice_single(chat_id, args, *, caller_script, extra_args, voice_label):
    confirmed, rest = _voice_parse_confirm(args)
    parts = rest.split(maxsplit=1)
    if not parts or not _voice_valid_phone(parts[0]):
        await send_message(chat_id,
            f"📞 *{voice_label} — single voice call*\n\n"
            f"Usage: `/voicecall +1XXXXXXXXXX <name>`  (preview only)\n"
            f"LIVE call: `/voicecall confirm +1XXXXXXXXXX <name>`")
        return
    phone = parts[0]
    name = parts[1].strip() if len(parts) > 1 else "Client"
    if not confirmed:
        await send_message(chat_id,
            f"🔍 *Dry-run — nothing placed.*\n\n"
            f"Would call *{name}* at `{phone}` using {voice_label}.\n\n"
            f"To place the LIVE call, reply:\n`/voicecall confirm {phone} {name}`")
        return
    await send_message(chat_id, f"📞 Placing {voice_label} call to *{name}* at `{phone}`…")
    argv = [CALLER_PYTHON, caller_script, "--to", phone, "--name", name] + extra_args
    rc, out, err = await _voice_spawn(argv)
    if rc == 0:
        detail = out.splitlines()[-1] if out else "placed"
        await send_message(chat_id, f"✅ {voice_label} call placed to *{name}*.\n`{_voice_redact(detail)[:300]}`")
    else:
        await send_message(chat_id, f"⚠️ {voice_label} call failed (rc={rc}).\n`{_voice_redact(err or out)[:300]}`")


async def viktoriya_voicecall(chat_id: int, args: str):
    await _voice_single(chat_id, args, caller_script=VICTORIA_CALLER,
                        extra_args=[], voice_label="Victoria (GOJ)")


async def masha_voicecall(chat_id: int, args: str):
    await _voice_single(chat_id, args, caller_script=MASHA_CALLER,
                        extra_args=["--type", "followup"], voice_label="Masha (BBG)")


async def _voicebatch_bg(chat_id, argv):
    rc, out, err = await _voice_spawn(argv, timeout=1800)
    src = out or err
    tail = src.splitlines()[-1] if src else f"rc={rc}"
    await send_message(chat_id, f"📞 Victoria attendance run finished (rc={rc}).\n`{_voice_redact(tail)[:300]}`")


async def viktoriya_voicebatch(chat_id: int, args: str):
    confirmed, _ = _voice_parse_confirm(args)
    if not confirmed:
        await send_message(chat_id,
            "🔁 *Victoria — full automated attendance run*\n\n"
            "Calls *every* scheduled client for tomorrow via the Retell voice agent "
            "(wave-based, TOS-safe). Preview only — nothing placed.\n\n"
            "LIVE batch → reply: `/voicebatch confirm`")
        return
    await send_message(chat_id, "📞 Starting Victoria automated attendance calls in the background…")
    asyncio.create_task(_voicebatch_bg(chat_id, [CALLER_PYTHON, VICTORIA_CALLER]))


async def viktoriya_voiceresults(chat_id: int, args: str):
    """Recent Victoria call outcomes from the victoria_calls table (read-only)."""
    try:
        conn = sqlite3.connect(str(VOICE_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT client_name, phone, call_date, call_time, status "
            "FROM victoria_calls ORDER BY call_date DESC, call_time DESC LIMIT 15").fetchall()
        conn.close()
    except Exception as e:
        await send_message(chat_id, f"⚠️ Couldn't read call results: `{e}`")
        return
    if not rows:
        await send_message(chat_id, "No Victoria calls logged yet.")
        return
    text = "☎️ *Recent Victoria call results*\n\n"
    for r in rows:
        text += f"• *{r['client_name']}* — {r['status']}  _{r['call_date']} {r['call_time']}_\n"
    await send_message(chat_id, text)


async def route_viktoriya_command(chat_id: int, cmd: str, args: str):
    handlers = {
        "/attendance": lambda: viktoriya_attendance(chat_id),
        "/client": lambda: viktoriya_client(chat_id, args.strip()),
        "/expiring": lambda: viktoriya_expiring(chat_id, int(args.strip()) if args.strip().isdigit() else 30),
        "/checkin": lambda: viktoriya_checkin(chat_id, args.strip()),
        "/schedule": lambda: viktoriya_schedule_update(chat_id, args.strip()),
        "/report": lambda: viktoriya_report(chat_id),
        "/calls": lambda: viktoriya_calls(chat_id),
        "/callreport": lambda: viktoriya_callreport(chat_id),
        "/callhistory": lambda: viktoriya_callhistory(chat_id),
        "/callscript": lambda: viktoriya_callscript(chat_id, args.strip()),
        "/voicecall": lambda: viktoriya_voicecall(chat_id, args),
        "/voicebatch": lambda: viktoriya_voicebatch(chat_id, args),
        "/voiceresults": lambda: viktoriya_voiceresults(chat_id, args),
        "/brain": lambda: viktoriya_brain(chat_id, args.strip()),
        "/ask": lambda: handle_ask(chat_id, args.strip(), "viktoriya"),
        "/loop": lambda: viktoriya_loop(chat_id),
        "/help": lambda: viktoriya_help(chat_id),
        "/start": lambda: viktoriya_help(chat_id),
    }
    handler = handlers.get(cmd)
    if handler:
        await handler()
    else:
        await send_message(chat_id, f"Unknown command: `{cmd}`. Try `/help`.")

# ═══════════════════════════════════════════════════════════
# Viktoriya: Call System
# ═══════════════════════════════════════════════════════════

def generate_call_list() -> list:
    """Query auth_tracker.db for today's prioritized call list."""
    if not AUTH_DB.exists():
        return []

    conn = sqlite3.connect(str(AUTH_DB))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    calls = []

    # TIER 1: Auth EXPIRED >30 days
    c.execute("""
        SELECT c.client_id, c.name, c.phone,
               a.service_end_date,
               CAST(julianday('now') - julianday(a.service_end_date) AS INTEGER) as days_expired
        FROM clients c
        JOIN (
            SELECT client_name, service_end_date, status,
                   ROW_NUMBER() OVER (PARTITION BY client_name ORDER BY last_updated_timestamp DESC) as rn
            FROM authorization
        ) a ON c.name = a.client_name AND a.rn = 1
        WHERE a.status = 'EXPIRED'
          AND a.service_end_date IS NOT NULL
          AND julianday('now') - julianday(a.service_end_date) > 30
        ORDER BY days_expired DESC
    """)
    for row in c.fetchall():
        calls.append({
            "client_id": row["client_id"], "name": row["name"], "phone": row["phone"],
            "call_type": "auth_expired_urgent", "priority": "🔴",
            "reason": f"Auth EXPIRED {row['days_expired']} days ago",
            "script_args": {"name": row["name"]},
        })

    # TIER 2: Auth expiring within 14 days
    c.execute("""
        SELECT c.client_id, c.name, c.phone, a.service_end_date
        FROM clients c
        JOIN (
            SELECT client_name, service_end_date,
                   ROW_NUMBER() OVER (PARTITION BY client_name ORDER BY last_updated_timestamp DESC) as rn
            FROM authorization WHERE status IN ('ACTIVE', 'EXPIRING')
        ) a ON c.name = a.client_name AND a.rn = 1
        WHERE a.service_end_date BETWEEN date('now') AND date('now', '+14 days')
        ORDER BY a.service_end_date ASC
    """)
    for row in c.fetchall():
        if not any(c["client_id"] == row["client_id"] for c in calls):
            calls.append({
                "client_id": row["client_id"], "name": row["name"], "phone": row["phone"],
                "call_type": "auth_expiring_soon", "priority": "🟡",
                "reason": f"Auth expires {row['service_end_date']}",
                "script_args": {"name": row["name"], "expiry_date": row["service_end_date"]},
            })

    # TIER 3: Absent yesterday (no call-out logged)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    c.execute("""
        SELECT c.client_id, c.name, c.phone
        FROM clients c
        WHERE c.active = 1
          AND c.name NOT IN (
              SELECT client_name FROM attendance_log WHERE log_date = ?
          )
          AND c.name IN (
              SELECT client_name FROM attendance_log WHERE log_date >= date('now', '-14 days')
              GROUP BY client_name HAVING COUNT(*) >= 3
          )
        LIMIT 10
    """, (yesterday,))
    for row in c.fetchall():
        if not any(c["client_id"] == row["client_id"] for c in calls):
            calls.append({
                "client_id": row["client_id"], "name": row["name"], "phone": row["phone"],
                "call_type": "absent_yesterday", "priority": "🟢",
                "reason": "Absent yesterday — welfare check",
                "script_args": {"name": row["name"]},
            })

    conn.close()
    return calls


def log_call(client_id: int, call_type: str, phone: str, status: str, notes: str = ""):
    """Write call outcome to victoria_call_log."""
    if not AUTH_DB.exists():
        return
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.execute("""
            INSERT INTO victoria_call_log (client_id, call_type, phone_number, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (client_id, call_type, phone or "", status, notes))
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Call log error: {e}")


async def viktoriya_calls(chat_id: int):
    calls = generate_call_list()

    if not calls:
        await send_message(chat_id, "✅ No calls needed today!")
        return

    _active_call_lists[chat_id] = calls

    text = f"☎️ *Today's Call List — {len(calls)} clients*\n\n"
    for i, call in enumerate(calls[:15]):
        text += (
            f"{call['priority']} *{i+1}. {call['name']}*\n"
            f"   _{call['reason']}_\n"
            f"   📞 `{call['phone'] or 'No phone'}`\n\n"
        )

    if len(calls) > 15:
        text += f"_...and {len(calls) - 15} more_\n\n"

    text += "Tap a button after each call:"

    keyboard_rows = []
    for i, call in enumerate(calls[:15]):
        client_id = call["client_id"]
        keyboard_rows.append([
            {"text": f"✅ #{i+1}", "callback_data": f"vcdone|{client_id}"},
            {"text": "📵", "callback_data": f"vcno|{client_id}"},
            {"text": "🔄", "callback_data": f"vclater|{client_id}"},
        ])

    await send_message(chat_id, text, reply_markup={"inline_keyboard": keyboard_rows})


async def viktoriya_callscript(chat_id: int, call_type: str):
    if not call_type:
        await send_message(chat_id,
            f"Call script types: `{', '.join(CALL_SCRIPTS.keys())}`\n\n"
            "Usage: `/callscript auth_expiring_soon`")
        return

    script = CALL_SCRIPTS.get(call_type)
    if not script:
        await send_message(chat_id,
            f"Unknown script type: `{call_type}`\n"
            f"Available: `{', '.join(CALL_SCRIPTS.keys())}`")
        return

    await send_message(chat_id, f"📋 *Call Script: {call_type}*\n\n_{script}_")


async def viktoriya_callreport(chat_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    rows, err = _goj_query("""
        SELECT vcl.status, COUNT(*) as cnt
        FROM victoria_call_log vcl
        WHERE date(vcl.created_at) = ?
        GROUP BY vcl.status
    """, (today,))

    detail_rows, _ = _goj_query("""
        SELECT c.name, vcl.status, vcl.notes
        FROM victoria_call_log vcl
        JOIN clients c ON vcl.client_id = c.client_id
        WHERE date(vcl.created_at) = ?
        ORDER BY vcl.created_at DESC
        LIMIT 30
    """, (today,))

    if err:
        await send_message(chat_id, f"❌ Error: {err}")
        return

    counts = {r["status"]: r["cnt"] for r in (rows or [])}
    done = counts.get("completed", 0)
    noans = counts.get("no_answer", 0)
    later = counts.get("will_call_later", 0)

    text = f"📊 *Daily Call Report — {today}*\n\n"
    text += f"Completed: *{done}* ✅\n"
    text += f"No answer: *{noans}* 📵\n"
    text += f"Call later: *{later}* 🔄\n"
    text += f"Total attempted: *{done + noans + later}*\n\n"

    if detail_rows:
        text += "*Details:*\n"
        for r in detail_rows:
            emoji = {"completed": "✅", "no_answer": "📵", "will_call_later": "🔄"}.get(r["status"], "❓")
            text += f"{emoji} *{r['name']}*"
            if r["notes"]:
                text += f" — _{r['notes']}_"
            text += "\n"

    await send_message(chat_id, text)


async def viktoriya_callhistory(chat_id: int):
    rows, _ = _goj_query("""
        SELECT date(created_at) as day,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done,
               SUM(CASE WHEN status='no_answer' THEN 1 ELSE 0 END) as noans,
               SUM(CASE WHEN status='will_call_later' THEN 1 ELSE 0 END) as later,
               COUNT(*) as total
        FROM victoria_call_log
        WHERE created_at >= date('now', '-7 days')
        GROUP BY day
        ORDER BY day DESC
    """)

    if not rows:
        await send_message(chat_id, "No call history in the last 7 days.")
        return

    text = "📞 *Call History — Last 7 Days*\n\n"
    for r in rows:
        text += f"*{r['day']}*: {r['done']}✅ {r['noans']}📵 {r['later']}🔄 ({r['total']} total)\n"

    await send_message(chat_id, text)


async def viktoriya_brain(chat_id: int, query: str = ""):
    """Search Obsidian & static knowledge for GOJ procedures."""
    if not query.strip():
        await send_message(chat_id,
            "🧠 *GOJ Knowledge Search*\n\n"
            "I know GOJ procedures. Ask me:\n"
            "• \"How do I check in a client?\"\n"
            "• \"What do I do if auth is expired?\"\n"
            "• \"How does the attendance system work?\"\n"
            "• \"What's the daily schedule?\"")
        return

    q = query.lower()
    text = f"🧠 *GOJ Knowledge: \"{query[:60]}\"*\n\n"

    if any(w in q for w in ["check in", "checkin", "mark present", "arrived"]):
        text += (
            "*How to Check In a Client:*\n"
            "1. Client arrives at GOJ\n"
            "2. Use `/checkin <client name>` — marks them as present\n"
            "3. This writes to `attendance_log` with status='present'\n"
            "4. Full name or partial name works\n"
            "5. Can also call `/client <name>` first to verify auth status\n\n"
            "*If client is not on today's schedule:* Flag to Kato.\n"
        )

    if any(w in q for w in ["auth", "expir", "renewal", "status"]):
        text += (
            "*Authorization (Auth) Statuses:*\n"
            "• `ACTIVE` — Client may attend (✅)\n"
            "• `EXPIRING` — Auth ending soon, needs renewal (⚠️)\n"
            "• `EXPIRED` — Auth finished, do NOT schedule (❌)\n"
            "• `PENDING RENEWAL` — Paperwork submitted, may continue (🟡)\n\n"
            "*EXPIRED >30 days with no PENDING RENEWAL:*\n"
            "→ Escalate immediately to Kato\n"
            "→ Do NOT remove from schedule without Kato's approval\n\n"
            "*Use `/expiring` to see who needs renewal soon.*\n"
        )

    if any(w in q for w in ["attendance", "count", "daily"]):
        text += (
            "*Attendance System:*\n"
            "• Clients are scheduled by day (Mon–Sat)\n"
            "• Present clients are counted via check-in\n"
            "• Daily reports show present vs scheduled\n"
            "• `/attendance` — today's counts\n"
            "• `/report` — full daily summary\n\n"
            "• Morning report: 7:30 AM daily\n"
            "• Kitchen+distribution PDFs: 10:30 AM\n"
            "• Sign-in+driver sheets: 3:15 PM\n"
            "• Missing menus check: 8:30 PM Fridays\n"
        )

    if any(w in q for w in ["call", "phone", "outbound"]):
        text += (
            "*Client Call System:*\n"
            "• `/calls` — generates today's call list\n"
            "• Calls are prioritized: 🔴 urgent > 🟡 high > 🟢 medium\n"
            "• Each call has a Russian script\n"
            "• Tap ✅ after each call to log it\n"
            "• `/callreport` — end-of-day summary\n\n"
            "*Call types:*\n"
            "• Auth expired (>30 days) — urgent renewal\n"
            "• Auth expiring soon (14 days) — renewal reminder\n"
            "• Absent yesterday — welfare check\n"
            "• Schedule change — notify client\n"
        )

    if any(w in q for w in ["schedule", "shift", "day", "route"]):
        text += (
            "*Client Scheduling:*\n"
            "• GOJ operates Mon–Sat (closed Sundays)\n"
            "• 425 total clients, ~80-120 attend daily\n"
            "• Two shifts: morning and afternoon\n"
            "• Schedule changes cascade across 7 systems:\n"
            "  Calendar → Attendance → Driver → Kitchen →\n"
            "  Distribution → Sign-in → Client Menu\n"
            "• Use `/client <name>` to see a client's schedule\n"
        )

    if text == f"🧠 *GOJ Knowledge: \"{query[:60]}\"*\n\n":
        text += "_Nothing specific found. Try these topics:_\n"
        text += "• Check-in / Attendance\n"
        text += "• Authorization / Expiring\n"
        text += "• Calls / Phone scripts\n"
        text += "• Schedule / Shifts\n"
        text += "• Daily procedures"

    await send_message(chat_id, text)


# ═══════════════════════════════════════════════════════════
# Admin: Kato Commands
# ═══════════════════════════════════════════════════════════

async def admin_addstaff(chat_id: int, args: str):
    if str(chat_id) != "5587703834":
        await send_message(chat_id, "❌ Admin only.")
        return

    parts = args.strip().split()
    if len(parts) != 2:
        await send_message(chat_id, "Usage: `/addstaff <role> <telegram_id>`")
        return

    role, tg_id = parts
    if role not in ("masha", "viktoriya", "admin"):
        await send_message(chat_id, f"Invalid role: {role}. Use 'masha' or 'viktoriya'.")
        return

    STAFF[tg_id] = {"name": role.title(), "role": role, "added": datetime.now().isoformat()}
    CONFIG["staff"] = STAFF
    CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))
    await send_message(chat_id, f"✅ Added *{role.title()}* (ID: `{tg_id}`)")


async def admin_removestaff(chat_id: int, args: str):
    if str(chat_id) != "5587703834":
        return
    tg_id = args.strip()
    if tg_id in STAFF:
        name = STAFF[tg_id]["name"]
        del STAFF[tg_id]
        CONFIG["staff"] = STAFF
        CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))
        await send_message(chat_id, f"✅ Removed *{name}* (ID: `{tg_id}`)")
    else:
        await send_message(chat_id, f"Staff ID `{tg_id}` not found.")


async def admin_liststaff(chat_id: int):
    if str(chat_id) != "5587703834":
        return
    text = "👥 *Registered Staff*\n\n"
    for tg_id, info in STAFF.items():
        text += f"• *{info['name']}* — `{info['role']}` — ID: `{tg_id}`\n"
    await send_message(chat_id, text)


async def admin_switch(chat_id: int, args: str):
    if str(chat_id) != "5587703834":
        return
    role = args.strip().lower()
    if role in ("reset", "admin"):
        role_overrides.pop(chat_id, None)
        await send_message(chat_id, "🔄 Switched back to *Admin* mode.")
    elif role in ("masha", "viktoriya"):
        role_overrides[chat_id] = role
        await send_message(chat_id, f"🔄 Switched to *{role.title()}* mode. `/switch reset` to go back.")
    else:
        await send_message(chat_id, "Usage: `/switch masha` or `/switch viktoriya` or `/switch reset`")


async def admin_broadcast(chat_id: int, args: str):
    if str(chat_id) != "5587703834":
        return
    if not args.strip():
        await send_message(chat_id, "Usage: `/broadcast <message>`")
        return

    sent = 0
    for tg_id, info in STAFF.items():
        if info["role"] in ("masha", "viktoriya"):
            try:
                if await send_message(int(tg_id), f"📢 *Message from Kato:*\n\n{args.strip()}"):
                    sent += 1
            except Exception:
                pass
    await send_message(chat_id, f"✅ Broadcast sent to {sent} staff members.")


async def admin_memory(chat_id: int, args: str):
    """Show agent memory & knowledge stats."""
    try:
        stats = _ghs_memory.stats()
        kb_by_agent = stats.get("knowledge_by_agent", {})
        kb_by_cat = stats.get("knowledge_by_category", {})
        
        msg = (
            f"🧠 *Agent Memory Stats*\n\n"
            f"💬 Conversations stored: {stats['conversations']}\n"
            f"📚 Knowledge entries: {stats['knowledge_entries']}\n"
            f"💾 DB size: {stats['db_size_mb']} MB\n\n"
            f"*Knowledge by agent:*\n"
        )
        for agent, count in kb_by_agent.items():
            msg += f"  • {agent}: {count}\n"
        
        if kb_by_cat:
            msg += "\n*By category:*\n"
            for cat, count in kb_by_cat.items():
                msg += f"  • {cat}: {count}\n"
        
        # Show recent knowledge
        recent_kb = _ghs_memory.get_all_knowledge(limit=5)
        if recent_kb:
            msg += "\n*Recent knowledge:*\n"
            for k in recent_kb:
                msg += f"  • [{k['agent']}/{k['category']}] {k['content'][:80]}\n"
        
        await send_message(chat_id, msg)
    except Exception as e:
        await send_message(chat_id, f"Memory error: {e}")


async def admin_forget(chat_id: int, args: str):
    """Forget a specific knowledge entry."""
    key = args.strip().lower()
    if not key:
        await send_message(chat_id, "Usage: `/forget <key_text>` — forgets a learned fact.\nUse `/memory` to see what's stored.")
        return
    
    # Search for matching entries
    results = _ghs_memory.search_knowledge("general", key, limit=3)
    if not results:
        results = _ghs_memory.search_knowledge("masha", key, limit=3)
    if not results:
        results = _ghs_memory.search_knowledge("viktoriya", key, limit=3)
    
    if not results:
        await send_message(chat_id, f"❌ No knowledge found matching: `{key}`")
        return
    
    # Delete all matches
    deleted = 0
    for r in results:
        _ghs_memory.delete_knowledge(r['key_text'], r['agent'])
        deleted += 1
    
    await send_message(chat_id, f"✅ Forgot {deleted} knowledge entr{'y' if deleted == 1 else 'ies'} matching `{key}`.")


# ═══════════════════════════════════════════════════════════
# Admin: /scrape — Scrapy Agent (Scrapy vs Crawlee decision)
# ═══════════════════════════════════════════════════════════

async def admin_scrap(chat_id: int, args: str):
    """Analyze a URL and recommend Scrapy vs Crawlee."""
    args = args.strip()

    if not args:
        await send_message(chat_id,
            "🔍 *Scrapy Agent — Usage*\\\n\\\n"
            "`/scrape <url> [signals...]`\\\n\\\n"
            "*Signal flags:*\\\n"
            "`--spa` — JavaScript single-page app\\\n"
            "`--static` — Server-rendered HTML\\\n"
            "`--hybrid` — Mixed rendering\\\n"
            "`--api` — JSON API only\\\n"
            "`--antibot mild|aggressive` — Anti-bot level\\\n"
            "`--screenshots` — Needs screenshots/PDFs\\\n"
            "`--auth` — Complex login/session\\\n"
            "`--pages N` — Estimated page count\\\n\\\n"
            "*Examples:*\\\n"
            "`/scrape https://example.com`\\\n"
            "`/scrape https://spa.io --spa --antibot aggressive --pages 50000`\\\n"
            "`/scrape https://api.io --static --api --pages 1000000`")
        return

    # Parse args: first word is URL, rest are signal flags
    parts = args.split()
    url = parts[0]
    signal_args = " ".join(parts[1:]) if len(parts) > 1 else ""

    # Parse signal flags
    structure = "unknown"
    antibot_level = "none"
    is_api_only = False
    needs_screenshots = False
    needs_auth = False
    estimated_pages = 0

    if "--spa" in signal_args:
        structure = "spa"
    elif "--static" in signal_args:
        structure = "static"
    elif "--hybrid" in signal_args:
        structure = "hybrid"

    if "--antibot aggressive" in signal_args:
        antibot_level = "aggressive"
    elif "--antibot mild" in signal_args:
        antibot_level = "mild"

    if "--api" in signal_args:
        is_api_only = True
    if "--screenshots" in signal_args:
        needs_screenshots = True
    if "--auth" in signal_args:
        needs_auth = True

    # Extract page count: --pages N
    import re
    pages_match = re.search(r"--pages\s+(\d+)", signal_args)
    if pages_match:
        estimated_pages = int(pages_match.group(1))

    # Call Scrapy Agent API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{REX_BASE}/scrapy-agent/analyze",
                json={
                    "url": url,
                    "structure": structure,
                    "antibot_level": antibot_level,
                    "is_api_only": is_api_only,
                    "needs_screenshots": needs_screenshots,
                    "needs_auth": needs_auth,
                    "estimated_pages": estimated_pages,
                },
            )
            if resp.status_code != 200:
                await send_message(chat_id, f"❌ Scrapy Agent error: {resp.text[:300]}")
                return

            data = resp.json()
    except Exception as e:
        await send_message(chat_id, f"❌ Could not reach Scrapy Agent: {e}")
        return

    # Format response
    rec = data["recommendation"].upper()
    scores = data["scores"]
    confidence = data["confidence"]
    reasoning = data["reasoning"]

    # Build signal summary
    signals_used = []
    if structure != "unknown":
        signals_used.append(f"Structure: `{structure}`")
    if antibot_level != "none":
        signals_used.append(f"Anti-bot: `{antibot_level}`")
    if is_api_only:
        signals_used.append("API-only")
    if needs_screenshots:
        signals_used.append("Screenshots needed")
    if needs_auth:
        signals_used.append("Auth required")
    if estimated_pages > 0:
        signals_used.append(f"~{estimated_pages:,} pages")

    signal_line = " • ".join(signals_used) if signals_used else "No signals provided"

    msg = (
        f"🔍 *Scrapy Agent Analysis*\\\n\\\n"
        f"📎 URL: `{url}`\\\n"
        f"📡 {signal_line}\\n\\\n"
        f"*Scores:*\\\n"
        f"🐍 Scrapy: `{scores['scrapy']:+.1f}`\\\n"
        f"🕷️ Crawlee: `{scores['crawlee']:+.1f}`\\\n\\\n"
        f"✅ *Recommendation: {rec}* (confidence: {confidence:.0%})\\n\\\n"
        f"💡 *Why:*"
    )

    # Add reasoning (limit to 5 most relevant lines)
    key_reasons = [r for r in reasoning if "Final:" not in r and "Profile note:" not in r][:5]
    for r in key_reasons:
        msg += f"\\\n• {r[:120]}"

    # Add feedback hint
    msg += (
        "\\\n\\\n"
        "_After scraping, submit feedback with:_\\\n"
        "`/scrape-feedback <url> success|partial|failure [--tool scrapy|crawlee] [notes...]`"
    )

    await send_message(chat_id, msg)


# ═══════════════════════════════════════════════════════════

PROJECT_REGISTER = Path.home() / "goj-shellcore" / "ops" / "PROJECT_REGISTER.md"


async def admin_idea(chat_id: int, args: str):
    """Capture a passing idea into the Project Register's Idea Inbox — so a
    thought gets parked without derailing the current task (anti-drift)."""
    idea = args.strip()
    if not idea:
        await send_message(chat_id,
            "💡 *Capture an idea*\n\nUsage: `/idea <your thought>`\n"
            "It's parked in the Project Register Idea Inbox so you can keep working. "
            "`/ideas` lists what's queued.")
        return
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with PROJECT_REGISTER.open("a") as f:
            f.write(f"- [ ] ({stamp}) {idea}\n")
        await send_message(chat_id, f"💡 Parked in the Idea Inbox:\n_{idea}_\n\n✅ Back to what you were doing. (`/ideas` to review)")
    except Exception as e:
        await send_message(chat_id, f"⚠️ Couldn't save that idea: `{e}`")


async def admin_ideas(chat_id: int, args: str = ""):
    """List the unsorted ideas currently in the Inbox."""
    try:
        lines = PROJECT_REGISTER.read_text().splitlines()
    except Exception as e:
        await send_message(chat_id, f"⚠️ Couldn't read the register: `{e}`")
        return
    in_inbox = False
    ideas = []
    for ln in lines:
        if ln.startswith("## ") and "Idea Inbox" in ln:
            in_inbox = True
            continue
        if in_inbox and ln.startswith("## "):
            break
        if in_inbox and ln.lstrip().startswith("- ["):
            ideas.append(ln.strip())
    if not ideas:
        await send_message(chat_id, "💡 Idea Inbox is empty — nothing queued.")
        return
    text = f"💡 *Idea Inbox — {len(ideas)} queued*\n\n" + "\n".join(ideas[-20:])
    await send_message(chat_id, text)


N8N_DB   = Path.home() / ".n8n" / "database.sqlite"
N8N_BASE = "http://127.0.0.1:5678"


async def admin_n8n(chat_id: int, args: str):
    """Bridge the staff bot to the n8n automation hub. Read-only listing +
    gated webhook trigger. Never touches n8n's stored workflows."""
    a = args.strip()
    # run <path> [confirm] → fire an n8n webhook (gated)
    if a.lower().startswith("run"):
        rest = a[3:].strip()
        confirmed, rest = _voice_parse_confirm(rest)
        path = rest.split()[0] if rest.split() else ""
        if not path:
            await send_message(chat_id, "Usage: `/n8n run <webhook-path>` (preview) → `/n8n run confirm <webhook-path>` (fire)")
            return
        import re as _re
        if not _re.fullmatch(r"[A-Za-z0-9_-]{1,64}", path):
            await send_message(chat_id, "⚠️ Webhook path must be a simple slug (letters, digits, `-`, `_`). No slashes.")
            return
        url = f"{N8N_BASE}/webhook/{path.lstrip('/')}"
        if not confirmed:
            await send_message(chat_id, f"🔍 *Dry-run.* Would POST to n8n webhook:\n`{url}`\n\nFire it: `/n8n run confirm {path}`")
            return
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, json={"source": "ghs-staff-bot", "at": datetime.now().isoformat()})
            await send_message(chat_id, f"✅ Triggered n8n `{path}` — HTTP {r.status_code}.\n`{_voice_redact(r.text)[:250]}`")
        except Exception as e:
            await send_message(chat_id, f"⚠️ n8n trigger failed: `{_voice_redact(str(e))[:250]}`")
        return
    # default / "list" → read-only workflow inventory
    try:
        conn = sqlite3.connect(f"file:{N8N_DB}?mode=ro", uri=True)
        rows = conn.execute("SELECT name, active FROM workflow_entity ORDER BY active DESC, name").fetchall()
        conn.close()
    except Exception as e:
        await send_message(chat_id, f"⚠️ Couldn't read n8n workflows: `{e}`")
        return
    active = [n for n, act in rows if act]
    idle = [n for n, act in rows if not act]
    text = f"⚙️ *n8n automation hub* — {len(active)} active / {len(rows)} total\n\n*Active:*\n"
    text += "\n".join(f"  🟢 {n}" for n in active) or "  (none)"
    if idle:
        text += "\n\n*Idle:*\n" + "\n".join(f"  ⚪ {n}" for n in idle)
    text += "\n\n_Trigger a webhook flow:_ `/n8n run <path>`"
    await send_message(chat_id, text)


async def route_admin_command(chat_id: int, cmd: str, args: str):
    handlers = {
        "/idea": lambda: admin_idea(chat_id, args),
        "/ideas": lambda: admin_ideas(chat_id, args),
        "/n8n": lambda: admin_n8n(chat_id, args),
        "/addstaff": lambda: admin_addstaff(chat_id, args),
        "/removestaff": lambda: admin_removestaff(chat_id, args),
        "/liststaff": lambda: admin_liststaff(chat_id),
        "/switch": lambda: admin_switch(chat_id, args),
        "/masha": lambda: admin_switch(chat_id, "masha"),
        "/viki": lambda: admin_switch(chat_id, "viktoriya"),
        "/viktoriya": lambda: admin_switch(chat_id, "viktoriya"),
        "/broadcast": lambda: admin_broadcast(chat_id, args),
        "/memory": lambda: admin_memory(chat_id, args),
        "/forget": lambda: admin_forget(chat_id, args),
        "/scrape": lambda: admin_scrap(chat_id, args),
        "/start": lambda: send_message(chat_id,
            "🤖 *GHS Staff Bot — Admin Mode*\n\n"
            "You're Kato. Quick shortcuts:\n\n"
            "`/masha` — see Masha's BBG view\n"
            "`/viki` — see Viktoriya's GOJ view\n\n"
            "*All commands:*\n"
            "`/switch masha|viktoriya|reset` — switch role\n"
            "`/liststaff` — see registered staff\n"
            "`/addstaff <role> <id>` — register staff\n"
            "`/removestaff <id>` — remove staff\n"
            "`/broadcast <msg>` — message all staff\n"
            "`/memory` — view agent memory stats\n"
            "`/forget <key>` — forget a learned fact\n"
            "`/scrape <url>` — analyze URL for Scrapy vs Crawlee\n\n"
            "_Staff register: `/register masha BBG2026` or `/register viktoriya GOJ2026`_"),
        "/help": lambda: send_message(chat_id,
            "*Admin Commands:*\n"
            "`/masha` — Masha's BBG view\n"
            "`/viki` — Viktoriya's GOJ view\n"
            "`/switch <role>` — Switch role\n"
            "`/addstaff <role> <id>` — Register staff\n"
            "`/removestaff <id>` — Remove staff\n"
            "`/liststaff` — Show all staff\n"
            "`/broadcast <msg>` — Message all staff\n"
            "`/memory` — Agent memory & knowledge stats\n"
            "`/forget <key>` — Remove learned knowledge\n"
            "`/scrape <url>` — Scrapy vs Crawlee analysis\n"
            "`/idea <thought>` — Park an idea (anti-drift) → Project Register\n"
            "`/ideas` — Review queued ideas\n"
            "`/n8n` — List automation workflows · `/n8n run <path>` — trigger one"),
    }
    handler = handlers.get(cmd)
    if handler:
        await handler()
    else:
        await send_message(chat_id, f"Unknown command: `{cmd}`. Try `/help`.")

# ═══════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════

async def handle_register(chat_id: int, args: str):
    parts = args.strip().split(maxsplit=1)
    role = parts[0].lower() if parts else ""
    code = parts[1].strip() if len(parts) > 1 else ""

    if role not in ("masha", "viktoriya"):
        await send_message(chat_id,
            "Usage: `/register masha CODE` or `/register viktoriya CODE`\n\n"
            "You need an access code from Kato.")
        return

    expected = CONFIG.get("access_codes", {}).get(role, "")
    if code != expected:
        await send_message(chat_id, "❌ Invalid access code. Contact Kato for your code.")
        return

    STAFF[str(chat_id)] = {"name": role.title(), "role": role, "registered": datetime.now().isoformat()}
    CONFIG["staff"] = STAFF
    CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))

    if role == "masha":
        await masha_help(chat_id)
    else:
        await viktoriya_help(chat_id)

    # Notify Kato
    await send_message(5587703834, f"✅ *{role.title()}* registered! (ID: `{chat_id}`)")


# ═══════════════════════════════════════════════════════════
# Message Router
# ═══════════════════════════════════════════════════════════

async def process_message(msg: dict):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text:
        return
    
    # Store incoming message in persistent memory
    _store_incoming(chat_id, text)

    role = get_staff_role(chat_id)

    # Unknown user → registration prompt
    if role == "unknown":
        await send_message(chat_id,
            "👋 *Welcome to GHS Staff Bot!*\n\n"
            "You're not registered yet.\n\n"
            "Send `/register masha CODE` or `/register viktoriya CODE`\n"
            "_Contact Kato for your access code._")
        return

    # Slash commands
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""

        # Registration works for unknown users too — handle first
        if cmd == "/register":
            await handle_register(chat_id, args)
            return

        if role == "masha":
            await route_masha_command(chat_id, cmd, args)
        elif role == "viktoriya":
            await route_viktoriya_command(chat_id, cmd, args)
        elif role == "admin":
            await route_admin_command(chat_id, cmd, args)
        return

    # Natural language
    if role == "masha":
        intent, query = detect_masha_intent(text)
        await route_masha_intent(chat_id, intent, query)
        # Poll for any relay responses from Kato
        await masha_relay_poll_responses(chat_id)
    elif role == "viktoriya":
        intent, query = detect_viktoriya_intent(text)
        await route_viktoriya_intent(chat_id, intent, query)
    elif role == "admin":
        # Smart admin natural language: auto-detect who they're talking about
        t = text.lower()

        # Detect who by context keywords
        is_masha = any(w in t for w in ["masha", "bbg", "menu", "drink", "burger", "beer", "hours", "faq", "post",
                                         "crm", "social", "instagram", "retell", "voice agent", "pipeline"])
        is_viki = any(w in t for w in ["viki", "viktoriya", "goj", "client", "attendance", "call", "expiring",
                                        "checkin", "auth", "schedule", "not coming", "can't come",
                                        "changing day", "switching", "instead of"])

        # If clearly one role
        if is_masha and not is_viki:
            role_overrides[chat_id] = "masha"
            intent, query = detect_masha_intent(text)
            if intent == "unknown":
                await masha_help(chat_id)
            else:
                await route_masha_intent(chat_id, intent, query)
            del role_overrides[chat_id]

        elif is_viki and not is_masha:
            role_overrides[chat_id] = "viktoriya"
            intent, query = detect_viktoriya_intent(text)
            if intent == "unknown":
                await viktoriya_help(chat_id)
            else:
                await route_viktoriya_intent(chat_id, intent, query)
            del role_overrides[chat_id]

        # If both mentioned or completely ambiguous — try both, report whichever has a match
        elif is_masha and is_viki:
            # Try Masha first
            role_overrides[chat_id] = "masha"
            m_intent, m_query = detect_masha_intent(text)
            del role_overrides[chat_id]

            role_overrides[chat_id] = "viktoriya"
            v_intent, v_query = detect_viktoriya_intent(text)
            del role_overrides[chat_id]

            if m_intent != "unknown":
                role_overrides[chat_id] = "masha"
                await route_masha_intent(chat_id, m_intent, m_query)
                del role_overrides[chat_id]
            elif v_intent != "unknown":
                role_overrides[chat_id] = "viktoriya"
                await route_viktoriya_intent(chat_id, v_intent, v_query)
                del role_overrides[chat_id]
            else:
                # Both keyword failed — try LLM
                llm_intent = await llm_understand(chat_id, text, "both")
                if llm_intent and llm_intent != "unknown":
                    # Route by LLM intent
                    if llm_intent in ("menu", "drinks", "hours", "specials", "events", "faq", "policy", "post", "flag", "brain"):
                        role_overrides[chat_id] = "masha"
                        await route_masha_intent(chat_id, llm_intent, _last_llm.get(chat_id, text))
                        del role_overrides[chat_id]
                    else:
                        role_overrides[chat_id] = "viktoriya"
                        await route_viktoriya_intent(chat_id, llm_intent, _last_llm.get(chat_id, text))
                        del role_overrides[chat_id]
                else:
                    await masha_help(chat_id)
                    await viktoriya_help(chat_id)

        # Completely ambiguous — try both intent detectors, show whichever has a match
        else:
            m_intent, m_query = detect_masha_intent(text)
            v_intent, v_query = detect_viktoriya_intent(text)

            if m_intent != "unknown":
                role_overrides[chat_id] = "masha"
                await route_masha_intent(chat_id, m_intent, m_query)
                del role_overrides[chat_id]
            elif v_intent != "unknown":
                role_overrides[chat_id] = "viktoriya"
                await route_viktoriya_intent(chat_id, v_intent, v_query)
                del role_overrides[chat_id]
            else:
                # Keywords failed — try LLM
                llm_intent = await llm_understand(chat_id, text, "both")
                if llm_intent and llm_intent != "unknown" and llm_intent != "direct":
                    if llm_intent in ("menu", "drinks", "hours", "specials", "events", "faq", "policy", "post", "flag", "brain"):
                        role_overrides[chat_id] = "masha"
                        await route_masha_intent(chat_id, llm_intent, _last_llm.get(chat_id, text))
                        del role_overrides[chat_id]
                    else:
                        role_overrides[chat_id] = "viktoriya"
                        await route_viktoriya_intent(chat_id, llm_intent, _last_llm.get(chat_id, text))
                        del role_overrides[chat_id]
                elif llm_intent != "direct":
                    await send_message(chat_id,
                        "I'm listening. What do you need?\n\n"
                        "• *BBG* — menu, hours, promos, social posts, CRM\n"
                        "• *GOJ* — attendance, clients, calls, auths\n\n"
                        "_Just talk to me — I'll figure out who you're asking about._")


# ═══════════════════════════════════════════════════════════
# Callback Handler (call tracking buttons)
# ═══════════════════════════════════════════════════════════

async def process_callback(callback: dict):
    callback_id = callback["id"]
    data = callback.get("data", "")
    msg = callback.get("message", {})
    chat_id = msg.get("chat", {}).get("id", 0)

    # Call tracking: vcdone|<client_id>, vcno|<client_id>, vclater|<client_id>
    if data.startswith("vcdone|"):
        client_id = int(data.split("|")[1])
        calls = _active_call_lists.get(chat_id, [])
        call = next((c for c in calls if c["client_id"] == client_id), None)
        if call:
            log_call(client_id, call["call_type"], call["phone"] or "", "completed")
            await answer_callback(callback_id, f"✅ {call['name']} — completed")

            # Ask outcome
            await send_message(chat_id,
                f"✅ *{call['name']}* — Outcome?\n"
                f"[✅ Will come] [❌ Not coming] [📝 Add note]",
                reply_markup={"inline_keyboard": [[
                    {"text": "✅ Will come", "callback_data": f"vcwill|{client_id}"},
                    {"text": "❌ Not coming", "callback_data": f"vcnot|{client_id}"},
                    {"text": "📝 Note", "callback_data": f"vcnote|{client_id}"},
                ]]})

    elif data.startswith("vcno|"):
        client_id = int(data.split("|")[1])
        calls = _active_call_lists.get(chat_id, [])
        call = next((c for c in calls if c["client_id"] == client_id), None)
        if call:
            log_call(client_id, call["call_type"], call["phone"] or "", "no_answer", "No answer")
            await answer_callback(callback_id, f"📵 {call['name']} — No answer logged")

    elif data.startswith("vclater|"):
        client_id = int(data.split("|")[1])
        calls = _active_call_lists.get(chat_id, [])
        call = next((c for c in calls if c["client_id"] == client_id), None)
        if call:
            log_call(client_id, call["call_type"], call["phone"] or "", "will_call_later")
            await answer_callback(callback_id, f"🔄 {call['name']} — Will call later")

    # Outcome follow-ups
    elif data.startswith("vcwill|"):
        client_id = int(data.split("|")[1])
        notes = f"Client confirmed they will come — {datetime.now().strftime('%I:%M %p')}"
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            conn.execute("UPDATE victoria_call_log SET notes = ? WHERE client_id = ? AND date(created_at) = date('now') ORDER BY rowid DESC LIMIT 1",
                        (notes, client_id))
            conn.commit()
            conn.close()
        except Exception:
            pass
        await answer_callback(callback_id, "✅ Noted — will come")

    elif data.startswith("vcnot|"):
        client_id = int(data.split("|")[1])
        notes = f"Client said they will NOT come — {datetime.now().strftime('%I:%M %p')}"
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            conn.execute("UPDATE victoria_call_log SET notes = ? WHERE client_id = ? AND date(created_at) = date('now') ORDER BY rowid DESC LIMIT 1",
                        (notes, client_id))
            conn.commit()
            conn.close()
        except Exception:
            pass
        # Alert Kato
        await send_message(5587703834, f"⚠️ Viktoriya called client {client_id} — they said NOT coming")
        await answer_callback(callback_id, "❌ Noted — will not come (Kato alerted)")

    elif data.startswith("vcnote|"):
        await answer_callback(callback_id, "Use /callreport to add notes")


# ═══════════════════════════════════════════════════════════
# Polling Loop
# ═══════════════════════════════════════════════════════════

async def poll_loop():
    state = load_state()
    offset = 0
    processed = set(state.get("processed_updates", []))

    log(f"=== GHS Staff Bot starting — {BOT_USERNAME} ===")

    while True:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{TELEGRAM_API}/bot{BOT_TOKEN}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 25,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )

                if resp.status_code != 200:
                    log(f"Poll error {resp.status_code}: {resp.text[:200]}")
                    await asyncio.sleep(5)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    log(f"API error: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    update_id = update["update_id"]
                    offset = update_id + 1

                    if update_id in processed:
                        continue

                    callback = update.get("callback_query")
                    if callback:
                        log(f"Callback: {callback.get('data', '')[:50]}")
                        await process_callback(callback)
                        processed.add(update_id)
                        continue

                    msg = update.get("message")
                    if msg and "text" in msg:
                        user = msg.get("from", {}).get("first_name", "?")
                        chat_id = msg["chat"]["id"]
                        log(f"Msg from {user} ({chat_id}): {msg['text'][:80]}")
                        await process_message(msg)

                    processed.add(update_id)
                    if len(processed) > 1000:
                        processed = set(list(processed)[-500:])

                state["processed_updates"] = list(processed)
                save_state(state)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log(f"Poll loop error: {traceback.format_exc()}")
            await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(poll_loop())
    except KeyboardInterrupt:
        log("Bot stopped.")
