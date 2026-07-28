#!/usr/bin/env python3
"""
CC_ghs_staff_v2.py — GHS Staff Bot (MiniMax-only, single LLM)
One bot, two roles: Masha (BBG) + Viktoriya (GOJ) + Kato (Admin).
No DeepSeek dependency. Keyword routing → MiniMax fallback.
"""
import asyncio, json, os, sys, traceback, sqlite3, random, re
from pathlib import Path
from datetime import datetime, timedelta
import httpx

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════
CONFIG_PATH = Path.home() / ".hermes" / "profiles" / "cloud" / "ghs_staff_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text())
BOT_TOKEN = CONFIG.get("bot_token", "")
BOT_USERNAME = CONFIG.get("bot_username", "@GHS_Staff_Bot")
STAFF = CONFIG.get("staff", {})

if not BOT_TOKEN or "PLACEHOLDER" in BOT_TOKEN:
    print("ERROR: Bot token not configured.", file=sys.stderr)
    sys.exit(1)

TELEGRAM_API = "https://api.telegram.org"
SOCIAL_ROUTER = "http://127.0.0.1:8000/social"
REX_BASE = "http://127.0.0.1:8000"
AUTH_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
BUSINESS_MEMORY_FILE = Path.home() / "Desktop" / "REX" / "higgsfield_business_memory.json"
STATE_FILE = Path.home() / ".hermes" / "profiles" / "cloud" / "ghs_staff_state.json"
LOG_FILE = Path.home() / "Desktop" / "REX" / "logs" / "ghs_staff_v2.log"
os.makedirs(LOG_FILE.parent, exist_ok=True)

role_overrides: dict = {}
_active_call_lists: dict = {}

# ═══════════════════════════════════════════════════════════
# MiniMax Config
# ═══════════════════════════════════════════════════════════
def _load_minimax():
    env_paths = [Path.home() / ".hermes" / "profiles" / "cloud" / ".env",
                 Path.home() / ".hermes" / ".env"]
    key = ""; base_url = "https://api.minimax.io/v1"
    for p in env_paths:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("MINIMAX_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("MINIMAX_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key, base_url

MINIMAX_KEY, MINIMAX_URL = _load_minimax()
MINIMAX_CHAT_URL = f"{MINIMAX_URL}/chat/completions"

# ═══════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f: f.write(line + "\n")
    except Exception: pass

async def send_message(chat_id: int, text: str, reply_markup=None):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                       "disable_web_page_preview": True}
            if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
            resp = await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage", json=payload)
            if resp.status_code == 200: return True
            # Markdown fail → retry plain
            payload.pop("parse_mode", None)
            resp2 = await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage", json=payload)
            return resp2.status_code == 200
    except Exception as e:
        log(f"send_message error: {e}"); return False

async def answer_callback(callback_id: str, text: str = ""):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/answerCallbackQuery",
                              json={"callback_query_id": callback_id, "text": text})
    except Exception: pass

def get_staff_role(chat_id: int) -> str:
    if chat_id in role_overrides: return role_overrides[chat_id]
    return STAFF.get(str(chat_id), {}).get("role", "unknown")

def load_business_memory():
    if BUSINESS_MEMORY_FILE.exists():
        try: return json.loads(BUSINESS_MEMORY_FILE.read_text())
        except Exception: pass
    return {}

def load_state() -> dict:
    if STATE_FILE.exists(): return json.loads(STATE_FILE.read_text())
    return {"processed_updates": []}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))

def _goj_query(query: str, params=()):
    if not AUTH_DB.exists(): return None, "DB not found"
    try:
        conn = sqlite3.connect(str(AUTH_DB)); conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall(); conn.close()
        return rows, None
    except Exception as e: return None, str(e)

# ═══════════════════════════════════════════════════════════
# MiniMax Reasoning (sole engine)
# ═══════════════════════════════════════════════════════════

PERPETUAL_MEMORY_PATH = Path.home() / "Documents" / "GHS-Vault" / "Hermes Perpetual Memory.md"
SESSION_BRIEF_PATH = Path.home() / "Documents" / "GHS-Vault" / "Hermes Session Brief.md"

_knowledge_cache = None

def _load_knowledge() -> str:
    """Load Perpetual Memory + Session Brief for injection into MiniMax context."""
    global _knowledge_cache
    if _knowledge_cache is not None:
        return _knowledge_cache
    parts = []
    for label, path in [("PERPETUAL MEMORY", PERPETUAL_MEMORY_PATH), 
                         ("SESSION BRIEF", SESSION_BRIEF_PATH)]:
        if path.exists():
            try:
                content = path.read_text()
                # Trim each to ~2000 chars to stay within context budget
                if len(content) > 2500:
                    content = content[:2500] + "\n[...truncated]"
                parts.append(f"--- {label} ---\n{content}")
            except Exception:
                pass
    _knowledge_cache = "\n\n".join(parts)
    return _knowledge_cache

SYSTEM_PROMPTS = {
    "masha": (
        "You are Masha, the friendly front-of-house AI for Boardwalk Beer Garden (BBG) "
        "in Brighton Beach, Brooklyn. You help with menu, hours, specials, events, FAQs, "
        "social posting, and CRM. Warm English with occasional Russian. Concise — 2-3 sentences max."
    ),
    "viktoriya": (
        "You are Viktoriya, the front-desk AI for Garden of Joy Adult Day Care (GOJ) "
        "in Brooklyn. You help with client lookups, attendance, authorization expirations, "
        "call scheduling, schedule changes, and daily procedures. Professional English with "
        "occasional Russian. Concise — 2-3 sentences."
    ),
    "general": (
        "You are the GHS Staff AI assistant for Gold Health Systems. You help with "
        "Boardwalk Beer Garden (BBG) and Garden of Joy (GOJ) operations. Helpful, "
        "concise, knowledgeable. 2-3 sentences unless asked for detail."
    ),
}

async def minimax_reason(chat_id: int, text: str, role: str = "general") -> str | None:
    if not MINIMAX_KEY:
        log("No MiniMax key configured")
        return None
    system_prompt = SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["general"])
    # Inject perpetual knowledge
    knowledge = _load_knowledge()
    if knowledge:
        system_prompt += f"\n\n{knowledge}\n\nUse this knowledge to answer accurately. You know the full system."
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": text}]
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(MINIMAX_CHAT_URL,
                headers={"Authorization": f"Bearer {MINIMAX_KEY}", "Content-Type": "application/json"},
                json={"model": "minimax-m3", "messages": messages, "max_tokens": 400, "temperature": 0.7})
            if resp.status_code != 200:
                log(f"MiniMax fail: {resp.status_code}"); return None
            answer = resp.json()["choices"][0]["message"]["content"].strip()
            log(f"MiniMax: {answer[:80]}...")
            return answer
    except Exception as e:
        log(f"MiniMax error: {e}"); return None

# ═══════════════════════════════════════════════════════════
# Masha — BBG Commands (keyword-routed, no LLM for intent)
# ═══════════════════════════════════════════════════════════
MASHA_KEYWORDS = {
    "menu": ["menu", "food", "burger", "pelmeni", "borscht", "chebureki", "dish", "meal", "eat"],
    "drinks": ["drink", "beer", "draft", "tap", "cocktail", "wine", "on tap"],
    "hours": ["close", "closing", "open", "hours", "time", "late", "tonight", "until"],
    "specials": ["special", "promo", "deal", "discount", "offer", "free", "price"],
    "events": ["game", "match", "sports", "world cup", "event", "playing", "showing"],
    "faq": ["reservation", "parking", "kids", "dog", "vegetarian", "card", "payment", "table", "allowed"],
    "brain": ["crm", "voice agent", "pipeline", "strategy", "plan", "retell", "lead connector",
              "ghl", "migration", "social media plan", "competitor", "lana"],
    "post": ["post", "announce", "broadcast", "publish", "share on"],
    "reservations": ["booking", "booked", "owner.com", "reservation tally"],
}

async def masha_menu(chat_id: int, category=None):
    bm = load_business_memory()
    menu = bm.get("foh", {}).get("menu", {}).get("categories", [])
    if category: menu = [c for c in menu if category.lower() in c.get("name", "").lower()]
    if not menu: return await send_message(chat_id, "Menu not available yet.")
    text = "🍽️ *BBG Menu*\n\n"
    for cat in menu:
        text += f"*{cat['name']}*\n"
        for item in cat.get("items", []):
            text += f"  • {item['name']} — ${item['price']}"
            if item.get("description"): text += f" _({item['description']})_"
            text += "\n"
        text += "\n"
    promo = bm.get("business", {}).get("current_promotion", "Buy 2 Get 1 Free")
    text += f"🍺 *Promo:* {promo}"
    await send_message(chat_id, text)

async def masha_drinks(chat_id: int):
    bm = load_business_memory()
    drinks = bm.get("foh", {}).get("drinks", {})
    text = "🍺 *BBG Drinks*\n\n"
    if drinks.get("draft_beers"):
        text += "*Draft Beers:*\n" + "\n".join(f"  • {b}" for b in drinks["draft_beers"]) + "\n\n"
    if drinks.get("cocktails"):
        text += "*Cocktails:*\n" + "\n".join(f"  • {c}" for c in drinks["cocktails"]) + "\n\n"
    if drinks.get("wine"): text += "*Wine:*\n" + "\n".join(f"  • {w}" for w in drinks["wine"]) + "\n\n"
    await send_message(chat_id, text)

async def masha_hours(chat_id: int):
    dow = datetime.now().strftime("%A")
    if dow in ("Saturday", "Sunday"):
        await send_message(chat_id, f"🕐 *BBG Hours — {dow}*\n\nOpen *12 PM – 1 AM* 🍺")
    else:
        await send_message(chat_id, f"🕐 *BBG Hours — {dow}*\n\nOpen *5 PM – 1 AM*\n_Happy Hour 5–7 PM: Buy 2 Get 1 FREE!_")

async def masha_specials(chat_id: int):
    bm = load_business_memory()
    promo = bm.get("business", {}).get("current_promotion", "Buy 2 Get 1 Free")
    await send_message(chat_id,
        f"🎉 *BBG Specials*\n\n"
        f"🍺 *{promo}*\n"
        f"   Mon–Thu, 5–7 PM\n\n"
        f"👥 Group special: Mon–Wed, 10+ guests\n"
        f"📞 Call: 929-205-6408")

async def masha_events(chat_id: int):
    await send_message(chat_id,
        "📅 *BBG Events*\n\n"
        "⚽ World Cup matches — all games live\n"
        "🎵 No DJ until summer (as of June 2026)\n"
        "🏖️ Weekend vibes — Sat/Sun from noon\n\n"
        "_Check `/hours` for today's schedule_")

async def masha_faq(chat_id: int, query=None):
    faqs = {
        "parking": "🚗 Street parking available. No dedicated lot.",
        "kids": "👶 Family-friendly during daytime. Adults-only after 8 PM.",
        "dogs": "🐕 Service animals only inside. Outdoor seating is dog-friendly.",
        "reservation": "📋 Walk-ins welcome! For groups 10+, call 929-205-6408.",
        "card": "💳 Cards + Apple Pay accepted.",
        "vegetarian": "🥬 Yes! Vegan/vegetarian options available — ask your server.",
    }
    if query and query.strip():
        q = query.lower().strip()
        for k, v in faqs.items():
            if k in q: return await send_message(chat_id, f"*{k.title()} FAQ:*\n{v}")
    text = "*BBG FAQs*\n\n" + "\n".join(f"• *{k.title()}:* {v}" for k, v in faqs.items())
    await send_message(chat_id, text)

async def masha_brain(chat_id: int, query=""):
    text = f"🧠 *BBG Knowledge: \"{query[:60]}\"*\n\n"
    q = query.lower()
    found = False
    if any(w in q for w in ["crm", "lead connector", "ghl", "migration"]):
        text += "*CRM / Lead Connector:*\n• HighLevel (GHL) migration in progress\n• Lana = lead connect associate\n"; found = True
    if any(w in q for w in ["voice agent", "masha", "retell"]):
        text += "*Voice Agent:*\n• Masha on Retell: agent_305ba9fdc34276c523766cd096\n• Phone: +164****3781\n• Voice: 11labs-victoria, Russian\n"; found = True
    if any(w in q for w in ["social", "instagram", "pipeline"]):
        text += "*Social Media:*\n• Instagram: @boardwalkbeergarden\n• 28 skills in social-media category\n• Hashtags: #BoardwalkBeerGarden #BrightonBeach #BrooklynEats\n"; found = True
    if any(w in q for w in ["pos", "clover", "payment"]):
        text += "*POS:* Clover C051UQ41540458\n"; found = True
    if any(w in q for w in ["adult", "age", "8pm", "policy"]):
        text += "*Age Policy:* Adults-only after 8 PM. No DJ until summer.\n"; found = True
    if not found:
        text += "_Nothing specific found. Try: CRM, Voice Agent, Social Media, POS, Age Policy_"
    await send_message(chat_id, text)

async def masha_post(chat_id: int, args: str):
    parts = args.strip().split(maxsplit=1)
    platform_word = parts[0].lower() if parts else ""
    message = parts[1].strip() if len(parts) > 1 else args.strip()
    platforms = ["instagram"] if platform_word in ("ig", "instagram") else \
                ["telegram"] if platform_word in ("tg", "telegram") else \
                ["instagram", "telegram"] if platform_word == "both" else ["instagram"]
    if not message:
        return await send_message(chat_id, "Usage: `/post [ig|tg|both] <message>`")
    await send_message(chat_id, f"📢 Posting to *{', '.join(platforms)}*...\n\n_{message[:200]}_")
    for platform in platforms:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{SOCIAL_ROUTER}/draft", json={
                    "topic": message[:150], "platforms": [platform],
                    "context": "Posted by Masha via GHS Staff Bot", "entity": "BBG"})
                if resp.status_code != 200: continue
                draft_id = resp.json().get("created", [{}])[0].get("draft_id")
                if not draft_id: continue
                await client.post(f"{SOCIAL_ROUTER}/draft/{draft_id}/approve")
                exec_resp = await client.post(f"{SOCIAL_ROUTER}/post/{draft_id}/execute")
                status = "✅" if exec_resp.status_code == 200 else "❌"
                await send_message(chat_id, f"{status} Posted to {platform}")
        except Exception as e:
            await send_message(chat_id, f"❌ {platform}: {e}")

async def masha_flag(chat_id: int, issue: str):
    await send_message(chat_id, f"🚩 *Issue flagged:* _{issue[:200]}_\n\nNotified Kato.")
    # Relay to Kato
    try:
        await send_message(5587703834, f"🚩 *Masha Flag:* {issue[:300]}")
    except Exception: pass

async def masha_help(chat_id: int):
    await send_message(chat_id,
        "🤖 *Masha — BBG Front of House*\n\n"
        "*Commands:*\n"
        "`/menu` — Full menu\n`/drinks` — Beer, cocktails, wine\n"
        "`/hours` — Today's hours\n`/specials` — Promotions\n"
        "`/events` — Games & happenings\n`/faq` — Common questions\n"
        "`/brain <q>` — CRM, voice agent, pipeline\n"
        "`/post ig|tg <msg>` — Post to social\n"
        "`/flag <issue>` — Report problem\n\n"
        "_Or just talk to me naturally!_")

# ═══════════════════════════════════════════════════════════
# Viktoriya — GOJ Commands
# ═══════════════════════════════════════════════════════════
VIKTORIYA_KEYWORDS = {
    "attendance": ["attendance", "how many", "count", "present", "here today", "who's here"],
    "client": ["client", "look up", "find", "who is", "info on"],
    "expiring": ["expiring", "expire", "auth", "authorization", "renewal", "insurance"],
    "calls": ["call list", "calls", "call today", "who to call"],
    "checkin": ["check in", "checkin", "arrived", "mark present"],
    "report": ["report", "summary", "daily", "status"],
    "schedule": ["not coming", "can't come", "absent", "sick", "won't be in",
                 "switched", "changing day", "instead of", "schedule change"],
    "brain": ["procedure", "how do i", "how does", "what's the", "g3 pro", "biometric",
              "ocr", "paperless", "drive sync", "pipeline"],
    "call_clients": ["call my clients", "call clients", "trigger calls", "make calls",
                     "victoria call", "call tomorrow", "start calling"],
    "preview": ["preview calls", "who would victoria", "who will victoria call",
                "preview tomorrow", "show calls"],
}

async def viktoriya_attendance(chat_id: int):
    rows, err = _goj_query("""
        SELECT log_date, COUNT(*) as cnt,
               SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) as present
        FROM attendance_log WHERE log_date >= date('now', '-1 days')
        GROUP BY log_date ORDER BY log_date DESC""")
    if err: return await send_message(chat_id, f"❌ {err}")
    today = datetime.now().strftime("%Y-%m-%d")
    text = f"📋 *Attendance — {today}*\n\n"
    for r in (rows or []):
        text += f"*{r['log_date']}*: {r['present']} present of {r['cnt']} logged\n"
    if not rows: text += "_No attendance data yet today._"
    await send_message(chat_id, text)

async def viktoriya_client(chat_id: int, name: str):
    if not name.strip(): return await send_message(chat_id, "Usage: `/client <name>`")
    rows, err = _goj_query(
        "SELECT c.name, c.phone, c.day_M_actual, c.day_T_actual, c.day_W_actual, "
        "c.day_TH_actual, c.day_F_actual, c.day_Su_actual "
        "FROM clients c WHERE c.name LIKE ? LIMIT 1", (f"%{name}%",))
    if err or not rows: return await send_message(chat_id, f"Client '*{name}*' not found.")
    r = rows[0]
    days = []
    for d, col in [("M","day_M_actual"),("T","day_T_actual"),("W","day_W_actual"),
                   ("TH","day_TH_actual"),("F","day_F_actual"),("Su","day_Su_actual")]:
        if r[col]: days.append(d)
    text = (f"👤 *{r['name']}*\n"
            f"📞 {r['phone'] or 'No phone'}\n"
            f"📅 Days: {', '.join(days) if days else 'None scheduled'}")
    await send_message(chat_id, text)

async def viktoriya_expiring(chat_id: int, days=30):
    rows, err = _goj_query("""
        SELECT c.name, c.phone, a.service_end_date, a.status,
               CAST(julianday(a.service_end_date) - julianday('now') AS INTEGER) as days_left
        FROM clients c JOIN (
            SELECT client_name, service_end_date, status,
                   ROW_NUMBER() OVER (PARTITION BY client_name ORDER BY last_updated_timestamp DESC) as rn
            FROM authorization WHERE status IN ('ACTIVE', 'EXPIRING')
        ) a ON c.name = a.client_name AND a.rn = 1
        WHERE a.service_end_date BETWEEN date('now') AND date('now', '+' || ? || ' days')
        ORDER BY a.service_end_date ASC""", (days,))
    if err: return await send_message(chat_id, f"❌ {err}")
    if not rows: return await send_message(chat_id, f"✅ No clients expiring within {days} days.")
    text = f"⚠️ *Auth Expiring — {len(rows)} clients within {days} days*\n\n"
    for r in rows:
        emoji = "🔴" if r["days_left"] <= 7 else "🟡" if r["days_left"] <= 14 else "🟢"
        text += f"{emoji} *{r['name']}* — {r['days_left']}d left (expires {r['service_end_date']})\n"
    await send_message(chat_id, text)

async def viktoriya_checkin(chat_id: int, name: str):
    if not name.strip(): return await send_message(chat_id, "Usage: `/checkin <name>`")
    rows, err = _goj_query("SELECT client_id, name FROM clients WHERE name LIKE ? LIMIT 1", (f"%{name}%",))
    if err or not rows: return await send_message(chat_id, f"Client '*{name}*' not found.")
    client = rows[0]; today = datetime.now().strftime("%Y-%m-%d")
    existing, _ = _goj_query("SELECT rowid FROM attendance_log WHERE client_name=? AND log_date=?", (client["name"], today))
    if existing: return await send_message(chat_id, f"ℹ️ *{client['name']}* already checked in.")
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.execute("INSERT INTO attendance_log (log_date, client_name, status) VALUES (?, ?, 'present')", (today, client["name"]))
        conn.commit(); conn.close()
        await send_message(chat_id, f"✅ *{client['name']}* checked in — {today}")
    except Exception as e:
        await send_message(chat_id, f"❌ {e}")

async def viktoriya_report(chat_id: int):
    att, _ = _goj_query("SELECT COUNT(*) as cnt, SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) as present FROM attendance_log WHERE log_date=date('now')")
    exp, _ = _goj_query("SELECT COUNT(*) as cnt FROM authorization WHERE status IN ('ACTIVE','EXPIRING') AND service_end_date BETWEEN date('now') AND date('now','+30 days')")
    calls, _ = _goj_query("SELECT status, COUNT(*) as cnt FROM victoria_call_log WHERE date(created_at)=date('now') GROUP BY status")
    today_str = datetime.now().strftime("%A, %B %d")
    text = f"📊 *Daily Report — {today_str}*\n\n"
    if att: text += f"*Attendance:* {att[0]['present']} present / {att[0]['cnt']} logged\n"
    if exp: text += f"*Auth expiring (30d):* {exp[0]['cnt']} clients\n"
    if calls:
        text += "*Calls today:*\n"
        for c in calls: text += f"  {c['status']}: {c['cnt']}\n"
    await send_message(chat_id, text)

async def viktoriya_calls(chat_id: int):
    # Generate prioritized call list
    urgent, _ = _goj_query("""
        SELECT c.client_id, c.name, c.phone FROM clients c
        JOIN authorization a ON c.name=a.client_name
        WHERE a.status='EXPIRED' AND a.service_end_date < date('now','-30 days')
        AND c.active=1 LIMIT 10""")
    expiring, _ = _goj_query("""
        SELECT c.client_id, c.name, c.phone FROM clients c
        JOIN authorization a ON c.name=a.client_name
        WHERE a.status IN ('ACTIVE','EXPIRING') AND a.service_end_date BETWEEN date('now') AND date('now','+14 days')
        AND c.active=1 LIMIT 15""")
    calls = []
    for r in (urgent or []): calls.append({"client_id": r["client_id"], "name": r["name"], "phone": r["phone"], "priority": "🔴", "reason": "Auth expired >30d", "call_type": "auth_expired_urgent"})
    for r in (expiring or []): calls.append({"client_id": r["client_id"], "name": r["name"], "phone": r["phone"], "priority": "🟡", "reason": "Auth expiring <14d", "call_type": "auth_expiring_soon"})
    if not calls: return await send_message(chat_id, "✅ No calls needed today!")
    _active_call_lists[chat_id] = calls
    text = f"☎️ *Today's Call List — {len(calls)} clients*\n\n"
    for i, c in enumerate(calls[:15]):
        text += f"{c['priority']} *{i+1}. {c['name']}*\n   _{c['reason']}_\n   📞 `{c['phone'] or 'No phone'}`\n\n"
    kb = [[{"text": f"✅ #{i+1}", "callback_data": f"vcdone|{c['client_id']}"},
           {"text": "📵", "callback_data": f"vcno|{c['client_id']}"},
           {"text": "🔄", "callback_data": f"vclater|{c['client_id']}"}] for i, c in enumerate(calls[:15])]
    await send_message(chat_id, text, reply_markup={"inline_keyboard": kb})

async def viktoriya_brain(chat_id: int, query=""):
    if not query.strip():
        return await send_message(chat_id, "🧠 *GOJ Knowledge*\nAsk me about: check-in, auth, attendance, calls, schedule, procedures")
    q = query.lower(); text = f"🧠 *GOJ Knowledge: \"{query[:60]}\"*\n\n"; found = False
    if any(w in q for w in ["check in", "checkin", "mark present"]):
        text += "*Check-In:* `/checkin <name>` — marks client present in attendance_log.\n"; found = True
    if any(w in q for w in ["auth", "expir", "renewal"]):
        text += "*Auth:* ACTIVE ✅ / EXPIRING ⚠️ / EXPIRED ❌ / PENDING RENEWAL 🟡\nEXPIRED >30d → escalate to Kato.\n"; found = True
    if any(w in q for w in ["attendance", "count"]):
        text += "*Attendance:* `/attendance` shows today's counts. `/report` for full summary.\n"; found = True
    if any(w in q for w in ["call", "phone", "outbound"]):
        text += "*Calls:* `/calls` generates prioritized list (🔴 urgent > 🟡 high).\n"; found = True
    if any(w in q for w in ["schedule", "not coming", "absent"]):
        text += "*Schedule Changes:* Just tell me — 'Maria is not coming Thursday' — and I'll update the DB.\n"; found = True
    if not found: text += "_Try: check-in, auth, attendance, calls, schedule_"
    await send_message(chat_id, text)

async def viktoriya_help(chat_id: int):
    await send_message(chat_id,
        "🤖 *Viktoriya — GOJ Front Desk*\n\n"
        "*Commands:*\n"
        "`/attendance` — Today's counts\n`/client <name>` — Look up client\n"
        "`/expiring [days]` — Auths expiring soon\n`/checkin <name>` — Mark present\n"
        "`/calls` — Today's call list\n`/report` — Daily summary\n"
        "`/brain <q>` — GOJ procedures\n`/schedule <msg>` — Update schedule\n"
        "`/call` — **Trigger Victoria's outbound calls**\n"
        "`/preview` — Show who Victoria would call\n\n"
        "_Or ask: \"how many here today?\" \"who's expiring?\" \"Maria is not coming Thursday\"_")

async def viktoriya_call_clients(chat_id: int):
    """Trigger Victoria to call tomorrow's clients via REX endpoint."""
    await send_message(chat_id, "☎️ *Triggering Victoria calls...*\n_This may take a minute._")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{REX_BASE}/victoria/call/run-daily-reminders")
            if resp.status_code == 200:
                data = resp.json()
                await send_message(chat_id, f"✅ *Victoria calls triggered!*\n{data.get('message', 'Calls started.')}")
            else:
                await send_message(chat_id, f"❌ Victoria call trigger failed: {resp.status_code}")
    except Exception as e:
        log(f"Victoria call error: {e}")
        await send_message(chat_id, f"❌ Could not reach Victoria: {e}")

async def viktoriya_preview(chat_id: int):
    """Show who Victoria would call tomorrow."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{REX_BASE}/victoria/preview-tomorrow")
            if resp.status_code == 200:
                data = resp.json()
                clients = data.get("clients", [])
                if not clients:
                    return await send_message(chat_id, "📋 *Preview:* No clients to call tomorrow.")
                text = f"📋 *Victoria Preview — {len(clients)} clients*\n\n"
                for c in clients[:20]:
                    text += f"• *{c.get('name', '?')}* — {c.get('phone', 'No phone')}\n"
                if len(clients) > 20:
                    text += f"\n_...and {len(clients)-20} more_"
                await send_message(chat_id, text)
            else:
                await send_message(chat_id, f"❌ Preview failed: {resp.status_code}")
    except Exception as e:
        await send_message(chat_id, f"❌ Could not reach Victoria: {e}")

# ═══════════════════════════════════════════════════════════
# Admin Commands
# ═══════════════════════════════════════════════════════════
async def admin_liststaff(chat_id: int):
    text = "👥 *Registered Staff*\n\n"
    for uid, info in STAFF.items():
        text += f"• `{uid}` — *{info.get('name','?')}* ({info.get('role','?')})\n"
    await send_message(chat_id, text or "_No staff registered._")

async def admin_switch(chat_id: int, args: str):
    role = args.strip().lower()
    if role == "reset": role_overrides.pop(chat_id, None); return await send_message(chat_id, "✅ Role reset.")
    if role in ("masha", "viktoriya"): role_overrides[chat_id] = role; return await send_message(chat_id, f"✅ Switched to *{role.title()}*")
    await send_message(chat_id, "Usage: `/switch masha|viktoriya|reset`")

# ═══════════════════════════════════════════════════════════
# Routing
# ═══════════════════════════════════════════════════════════
def detect_intent(text: str, keywords: dict) -> tuple:
    t = text.lower()
    for intent, kws in keywords.items():
        if any(kw in t for kw in kws): return (intent, text)
    return ("unknown", text)

async def route_masha(chat_id: int, intent: str, query: str):
    handlers = {
        "menu": lambda: masha_menu(chat_id),
        "drinks": lambda: masha_drinks(chat_id),
        "hours": lambda: masha_hours(chat_id),
        "specials": lambda: masha_specials(chat_id),
        "events": lambda: masha_events(chat_id),
        "faq": lambda: masha_faq(chat_id, query),
        "brain": lambda: masha_brain(chat_id, query),
        "post": lambda: masha_post(chat_id, query),
        "reservations": lambda: send_message(chat_id, "📊 Check `/tally` for reservation counts."),
    }
    if intent in handlers: return await handlers[intent]()
    # Keyword didn't match → MiniMax
    answer = await minimax_reason(chat_id, query, "masha")
    if answer: await send_message(chat_id, answer)
    else: await send_message(chat_id, "I didn't catch that. Try `/help`!")

async def route_masha_command(chat_id: int, cmd: str, args: str):
    cmds = {
        "/menu": lambda: masha_menu(chat_id, args.strip() or None),
        "/drinks": lambda: masha_drinks(chat_id),
        "/hours": lambda: masha_hours(chat_id),
        "/specials": lambda: masha_specials(chat_id),
        "/events": lambda: masha_events(chat_id),
        "/faq": lambda: masha_faq(chat_id, args.strip() or None),
        "/brain": lambda: masha_brain(chat_id, args.strip()),
        "/post": lambda: masha_post(chat_id, args.strip()),
        "/flag": lambda: masha_flag(chat_id, args.strip()),
        "/help": lambda: masha_help(chat_id),
        "/start": lambda: masha_help(chat_id),
    }
    h = cmds.get(cmd)
    if h: await h()
    else: await send_message(chat_id, f"Unknown: `{cmd}`. Try `/help`.")

async def route_viktoriya(chat_id: int, intent: str, query: str):
    handlers = {
        "attendance": lambda: viktoriya_attendance(chat_id),
        "client": lambda: viktoriya_client(chat_id, query),
        "expiring": lambda: viktoriya_expiring(chat_id),
        "calls": lambda: viktoriya_calls(chat_id),
        "call_clients": lambda: viktoriya_call_clients(chat_id),
        "preview": lambda: viktoriya_preview(chat_id),
        "checkin": lambda: viktoriya_checkin(chat_id, query),
        "report": lambda: viktoriya_report(chat_id),
        "schedule": lambda: viktoriya_schedule_nl(chat_id, query),
        "brain": lambda: viktoriya_brain(chat_id, query),
    }
    if intent in handlers: return await handlers[intent]()
    answer = await minimax_reason(chat_id, query, "viktoriya")
    if answer: await send_message(chat_id, answer)
    else: await send_message(chat_id, "I didn't catch that. Try `/help`!")

async def viktoriya_schedule_nl(chat_id: int, text: str):
    await send_message(chat_id, "⏳ Checking schedule...")
    answer = await minimax_reason(chat_id,
        f"Extract schedule change from: \"{text}\". Who? What day? Not coming / coming / day change? Reply concisely.", "viktoriya")
    if answer: await send_message(chat_id, f"📝 *Schedule Update:*\n{answer}\n\n_Use `/client <name>` to verify, then I'll update the DB._")

async def route_viktoriya_command(chat_id: int, cmd: str, args: str):
    cmds = {
        "/attendance": lambda: viktoriya_attendance(chat_id),
        "/client": lambda: viktoriya_client(chat_id, args.strip()),
        "/expiring": lambda: viktoriya_expiring(chat_id, int(args.strip()) if args.strip().isdigit() else 30),
        "/checkin": lambda: viktoriya_checkin(chat_id, args.strip()),
        "/calls": lambda: viktoriya_calls(chat_id),
        "/call": lambda: viktoriya_call_clients(chat_id),
        "/preview": lambda: viktoriya_preview(chat_id),
        "/report": lambda: viktoriya_report(chat_id),
        "/brain": lambda: viktoriya_brain(chat_id, args.strip()),
        "/schedule": lambda: viktoriya_schedule_nl(chat_id, args.strip()),
        "/help": lambda: viktoriya_help(chat_id),
        "/start": lambda: viktoriya_help(chat_id),
    }
    h = cmds.get(cmd)
    if h: await h()
    else: await send_message(chat_id, f"Unknown: `{cmd}`. Try `/help`.")

async def route_admin_command(chat_id: int, cmd: str, args: str):
    cmds = {
        "/liststaff": lambda: admin_liststaff(chat_id),
        "/switch": lambda: admin_switch(chat_id, args),
        "/masha": lambda: admin_switch(chat_id, "masha"),
        "/viki": lambda: admin_switch(chat_id, "viktoriya"),
        "/viktoriya": lambda: admin_switch(chat_id, "viktoriya"),
        "/help": lambda: send_message(chat_id, "*Admin:* `/masha` `/viki` `/switch` `/liststaff`"),
        "/start": lambda: send_message(chat_id, "🤖 *GHS Staff Bot — Admin*\n`/masha` for BBG · `/viki` for GOJ"),
    }
    h = cmds.get(cmd)
    if h: await h()
    else: await send_message(chat_id, f"Unknown: `{cmd}`.")

# ═══════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════
async def handle_register(chat_id: int, args: str):
    parts = args.strip().split(maxsplit=1)
    role = parts[0].lower() if parts else ""
    code = parts[1].strip() if len(parts) > 1 else ""
    if role not in ("masha", "viktoriya"):
        return await send_message(chat_id, "Usage: `/register masha CODE` or `/register viktoriya CODE`")
    expected = CONFIG.get("access_codes", {}).get(role, "")
    if code != expected: return await send_message(chat_id, "❌ Invalid code.")
    STAFF[str(chat_id)] = {"name": role.title(), "role": role, "registered": datetime.now().isoformat()}
    CONFIG["staff"] = STAFF
    CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))
    if role == "masha": await masha_help(chat_id)
    else: await viktoriya_help(chat_id)
    try: await send_message(5587703834, f"✅ *{role.title()}* registered! (`{chat_id}`)")
    except: pass

# ═══════════════════════════════════════════════════════════
# Message Processor
# ═══════════════════════════════════════════════════════════
async def process_message(msg: dict):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text: return
    log(f"Msg from {msg['chat'].get('first_name','?')} ({chat_id}): {text[:80]}")

    role = get_staff_role(chat_id)

    # Unknown user
    if role == "unknown":
        return await send_message(chat_id,
            "👋 *Welcome!*\n\nRegister: `/register masha CODE` or `/register viktoriya CODE`\n_Contact Kato for your code._")

    # Slash commands
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""
        if cmd == "/register": return await handle_register(chat_id, args)
        if role == "masha": return await route_masha_command(chat_id, cmd, args)
        elif role == "viktoriya": return await route_viktoriya_command(chat_id, cmd, args)
        elif role == "admin": return await route_admin_command(chat_id, cmd, args)

    # Natural language
    if role == "masha":
        intent, query = detect_intent(text, MASHA_KEYWORDS)
        await route_masha(chat_id, intent, query)
    elif role == "viktoriya":
        intent, query = detect_intent(text, VIKTORIYA_KEYWORDS)
        await route_viktoriya(chat_id, intent, query)
    elif role == "admin":
        # Smart routing: detect BBG vs GOJ by keywords
        t = text.lower()
        is_bbg = any(w in t for w in ["masha", "bbg", "menu", "drink", "burger", "beer", "hours", "faq", "post", "crm", "social", "instagram"])
        is_goj = any(w in t for w in ["viki", "viktoriya", "goj", "client", "attendance", "call", "expiring", "checkin", "auth", "schedule", "not coming"])
        if is_bbg and not is_goj:
            intent, query = detect_intent(text, MASHA_KEYWORDS)
            await route_masha(chat_id, intent, query)
        elif is_goj and not is_bbg:
            intent, query = detect_intent(text, VIKTORIYA_KEYWORDS)
            await route_viktoriya(chat_id, intent, query)
        else:
            # Ambiguous — try MiniMax
            answer = await minimax_reason(chat_id, text, "general")
            if answer: await send_message(chat_id, answer)
            else: await send_message(chat_id, "I'm listening — BBG or GOJ?\n`/masha` for BBG · `/viki` for GOJ")

# ═══════════════════════════════════════════════════════════
# Callback Handler (call tracking)
# ═══════════════════════════════════════════════════════════
async def process_callback(callback: dict):
    cid = callback["id"]; data = callback.get("data", "")
    chat_id = callback.get("message", {}).get("chat", {}).get("id", 0)
    if data.startswith("vcdone|"):
        client_id = int(data.split("|")[1])
        calls = _active_call_lists.get(chat_id, [])
        call = next((c for c in calls if c["client_id"] == client_id), None)
        if call:
            try:
                conn = sqlite3.connect(str(AUTH_DB))
                conn.execute("INSERT INTO victoria_call_log (client_id, call_type, phone_number, status, created_at) VALUES (?,?,?,?,datetime('now'))",
                             (client_id, call["call_type"], call.get("phone",""), "completed"))
                conn.commit(); conn.close()
            except: pass
            await answer_callback(cid, f"✅ {call['name']} — completed")
    elif data.startswith("vcno|"):
        client_id = int(data.split("|")[1])
        calls = _active_call_lists.get(chat_id, [])
        call = next((c for c in calls if c["client_id"] == client_id), None)
        if call:
            try:
                conn = sqlite3.connect(str(AUTH_DB))
                conn.execute("INSERT INTO victoria_call_log (client_id, call_type, phone_number, status, notes, created_at) VALUES (?,?,?,?,'No answer',datetime('now'))",
                             (client_id, call["call_type"], call.get("phone",""), "no_answer"))
                conn.commit(); conn.close()
            except: pass
            await answer_callback(cid, f"📵 {call['name']} — No answer")
    elif data.startswith("vclater|"):
        client_id = int(data.split("|")[1])
        calls = _active_call_lists.get(chat_id, [])
        call = next((c for c in calls if c["client_id"] == client_id), None)
        if call:
            try:
                conn = sqlite3.connect(str(AUTH_DB))
                conn.execute("INSERT INTO victoria_call_log (client_id, call_type, phone_number, status, created_at) VALUES (?,?,?,'will_call_later',datetime('now'))",
                             (client_id, call["call_type"], call.get("phone","")))
                conn.commit(); conn.close()
            except: pass
            await answer_callback(cid, f"🔄 {call['name']} — Call later")

# ═══════════════════════════════════════════════════════════
# Main Polling Loop
# ═══════════════════════════════════════════════════════════
async def main():
    log("=== GHS Staff Bot v2 starting — @GHS_Staff_Bot (MiniMax-only) ===")
    state = load_state()
    offset = max(state.get("processed_updates", []), default=0)

    while True:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{TELEGRAM_API}/bot{BOT_TOKEN}/getUpdates",
                                        params={"offset": offset, "timeout": 30})
                if resp.status_code != 200:
                    await asyncio.sleep(5); continue
                updates = resp.json().get("result", [])
                for upd in updates:
                    offset = upd["update_id"] + 1
                    state["processed_updates"] = [offset]
                    save_state(state)
                    if "message" in upd: await process_message(upd["message"])
                    elif "callback_query" in upd: await process_callback(upd["callback_query"])
        except Exception as e:
            log(f"Poll error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
