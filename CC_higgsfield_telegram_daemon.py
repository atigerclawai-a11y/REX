#!/usr/bin/env python3
"""
CC_higgsfield_telegram_daemon.py
Dedicated Telegram bot for Higgsfield Creative Agent.
Vibe matcher + prompt optimizer + perpetual learning.
Listens on @Higgsfield_Creation_Bot.
"""
import asyncio
import json
import os
import re
import sys
import traceback
from pathlib import Path
from datetime import datetime

import httpx

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════

CONFIG_PATH = Path.home() / "Desktop" / "REX" / "higgsfield_bot_config.json"
if CONFIG_PATH.exists():
    _cfg = json.loads(CONFIG_PATH.read_text())
    BOT_TOKEN = _cfg.get("bot_token", "")
    BOT_USERNAME = _cfg.get("bot_username", "@Higgsfield_Creation_Bot")
else:
    BOT_TOKEN = ""
    BOT_USERNAME = "@Higgsfield_Creation_Bot"

if not BOT_TOKEN:
    print("ERROR: No bot token found in higgsfield_bot_config.json", file=sys.stderr)
    sys.exit(1)

HIGGSFIELD_ROUTER = "http://127.0.0.1:8000/higgsfield"
SOCIAL_ROUTER = "http://127.0.0.1:8000/social"

# Per-chat last generation cache (for social posting)
last_generation: dict = {}
TELEGRAM_API = "https://api.telegram.org"
STATE_FILE = Path.home() / ".hermes" / "profiles" / "cloud" / "higgsfield_bot_state.json"
LEARNING_FILE = Path.home() / ".hermes" / "profiles" / "cloud" / "higgsfield_vibe_learning.json"
BUSINESS_MEMORY_FILE = Path.home() / "Desktop" / "REX" / "higgsfield_business_memory.json"
LOG_FILE = Path.home() / "Desktop" / "REX" / "logs" / "higgsfield_telegram_daemon.log"

os.makedirs(LOG_FILE.parent, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# Model Catalog (with full descriptions)
# ═══════════════════════════════════════════════════════════

MODEL_HELP = {
    "nano-banana": "Quick high-quality visuals",
    "nano-banana-pro": "Premium high-quality visuals",
    "recraft-v4-1": "Vectors, 100+ styles, SVG, illustrations",
    "soul-v2": "Character-consistent generation",
    "seedream-4": "ByteDance photorealism",
    "wan-2.2": "Alibaba composition",
    "flux-kontext": "Black Forest Labs — contextual scenes",
    "ideogram": "Text-in-image specialist",
    "gpt-image-2": "OpenAI image generation",
    "seedance-2": "Flagship video — dance & motion",
    "kling-3": "Kuaishou stylized video",
    "kling-2.1-master": "Kuaishou master quality",
    "kling-2.5-turbo": "Kuaishou fast turbo",
    "kling-avatars": "LipSync talking avatars",
    "minimax-hailuo": "Strong realism video",
    "cinema-studio": "Cinematic film scenes",
    "wan-2.5": "Alibaba video generation",
    "sora-2": "OpenAI Sora 2 + platform presets",
    "google-veo3": "Google Veo3 video",
}

VIDEO_MODELS = {
    "seedance-2", "kling-3", "kling-2.1-master", "kling-2.5-turbo",
    "kling-avatars", "minimax-hailuo", "cinema-studio", "wan-2.5",
    "sora-2", "google-veo3",
}

# ═══════════════════════════════════════════════════════════
# Vibe Matcher — keyword → model mapping
# ═══════════════════════════════════════════════════════════

IMAGE_VIBE_KEYWORDS = {
    "recraft-v4-1": [
        "anime", "cartoon", "vector", "flat", "illustration", "logo", "icon",
        "brand", "graphic", "2d", "drawing", "sketch", "line art", "vintage",
        "retro", "sticker", "infographic", "poster", "design", "manga",
    ],
    "soul-v2": [
        "character", "avatar", "portrait", "person", "consistent", "face",
        "self", "original character", "rpg", "game character", "d&d",
        "fantasy character", "dnd",
    ],
    "seedream-4": [
        "photorealistic", "realistic", "photo", "photography", "lifelike",
        "authentic", "product photo", "commercial", "catalog", "ecommerce",
        "sharp", "crisp", "detailed photo", "fashion",
    ],
    "wan-2.2": [
        "composition", "balanced", "landscape", "wide", "panorama", "scenic",
        "nature", "outdoor", "environment", "landscapes",
    ],
    "nano-banana": [
        "fast", "quick", "general", "any", "default", "simple", "basic",
        "just", "test", "try", "random",
    ],
    "nano-banana-pro": [
        "premium", "high quality", "polished", "professional", "refined",
        "high-end", "luxury", "magazine", "editorial",
    ],
    "flux-kontext": [
        "contextual", "complex", "detailed", "world-building", "environment",
        "intricate", "rich", "layered", "deep", "immersive", "atmospheric",
        "moody", "dark", "cyberpunk", "sci-fi", "noir", "gritty",
    ],
    "ideogram": [
        "text", "typography", "word", "lettering", "font", "calligraphy",
        "wordmark", "slogan", "quote", "title", "sign", "label", "text overlay",
    ],
    "gpt-image-2": [
        "dall-e", "openai", "hyperrealistic", "surreal", "dreamlike",
        "artistic photo", "conceptual", "fantasy art",
    ],
}

VIDEO_VIBE_KEYWORDS = {
    "seedance-2": [
        "dance", "motion", "movement", "flow", "kinetic", "dynamic",
        "creative video",
    ],
    "kling-2.1-master": [
        "cinematic", "film", "movie", "master", "epic", "grand", "blockbuster",
        "hollywood", "theatrical", "dramatic", "trailer", "teaser",
    ],
    "kling-2.5-turbo": [
        "fast video", "quick video", "rapid", "turbo", "speed", "short clip",
        "social clip", "quick cut",
    ],
    "kling-3": [
        "stylized", "artistic video", "creative", "experimental", "avant-garde",
        "abstract video", "art film", "music video", "aesthetic",
    ],
    "kling-avatars": [
        "talking", "speaking", "avatar", "lip-sync", "spokesperson", "narrator",
        "presenter", "vtuber", "talking head", "dialogue",
    ],
    "minimax-hailuo": [
        "realistic video", "documentary", "real", "authentic video", "candid",
        "handheld", "found footage", "verite",
    ],
    "cinema-studio": [
        "cinema", "cinematic scene", "movie scene", "film scene", "noir",
        "atmospheric video", "moody video", "lighting",
    ],
    "wan-2.5": [
        "composition video", "balanced video", "wide shot", "establishing shot",
        "landscape video", "aerial", "drone",
    ],
    "sora-2": [
        "tiktok", "reels", "shorts", "social", "viral", "platform", "vertical",
        "mobile", "instagram", "youtube short", "trend",
    ],
    "google-veo3": [
        "google", "high quality video", "premium video", "detailed video",
        "4k", "high res video", "professional video",
    ],
}

# ═══════════════════════════════════════════════════════════
# Prompt Optimizer — model-specific prompt recipes
# ═══════════════════════════════════════════════════════════

PROMPT_RECIPES = {
    "recraft-v4-1": [
        "high quality", "professional", "vibrant colors",
    ],
    "soul-v2": [
        "character portrait", "consistent features", "centered composition",
        "high detail face", "expressive eyes",
    ],
    "seedream-4": [
        "photorealistic", "8K", "sharp focus", "professional photography",
        "natural lighting", "detailed texture", "shallow depth of field",
    ],
    "wan-2.2": [
        "well-composed", "balanced framing", "rule of thirds",
        "environmental context", "natural colors",
    ],
    "nano-banana": [
        "high quality", "detailed", "vibrant colors", "professional", "8K",
    ],
    "nano-banana-pro": [
        "ultra high quality", "masterpiece", "award-winning",
        "professional photography", "exquisite detail", "perfect composition",
        "8K HDR",
    ],
    "flux-kontext": [
        "atmospheric", "rich environmental detail", "immersive scene",
        "dramatic lighting", "moody ambiance", "intricate background details",
    ],
    "ideogram": [
        "clean typography", "clear readable text", "professional layout",
        "centered text", "high contrast", "minimal background",
    ],
    "gpt-image-2": [
        "highly detailed", "photorealistic", "professional",
        "cinematic lighting", "sharp focus", "8K",
    ],
    "seedance-2": [
        "smooth motion", "fluid animation", "high quality video",
        "consistent motion", "24fps cinematic",
    ],
    "kling-2.1-master": [
        "cinematic masterpiece", "film quality", "dramatic lighting",
        "professional color grading", "24fps", "anamorphic lens",
        "shallow depth of field",
    ],
    "kling-2.5-turbo": [
        "fast motion", "dynamic", "energetic", "high frame rate",
        "smooth transition",
    ],
    "kling-3": [
        "stylized", "artistic", "creative cinematography",
        "unique color palette", "experimental framing", "art direction",
    ],
    "kling-avatars": [
        "talking avatar", "natural speech movement", "lip sync",
        "expressive face", "centered portrait",
    ],
    "minimax-hailuo": [
        "realistic footage", "documentary style", "natural lighting",
        "handheld feel", "authentic movement", "candid",
    ],
    "cinema-studio": [
        "cinematic film scene", "anamorphic lens", "dramatic lighting",
        "film grain", "color graded", "24fps", "widescreen",
        "depth of field",
    ],
    "wan-2.5": [
        "smooth camera movement", "well-composed shots",
        "natural color", "balanced framing",
    ],
    "sora-2": [
        "vertical format", "social media optimized",
        "hook in first 2 seconds", "fast-paced", "engaging", "trending style",
    ],
    "google-veo3": [
        "high resolution", "professional grade", "detailed motion",
        "4K", "cinematic quality", "smooth tracking shots",
    ],
}

# ═══════════════════════════════════════════════════════════
# Learning Engine
# ═══════════════════════════════════════════════════════════

def load_learning():
    if LEARNING_FILE.exists():
        return json.loads(LEARNING_FILE.read_text())
    return {"matches": [], "model_vibe_scores": {}}

def save_learning(data):
    LEARNING_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEARNING_FILE.write_text(json.dumps(data, indent=2))

# ═══════════════════════════════════════════════════════════
# Business Memory — BBG brand knowledge + content strategy
# ═══════════════════════════════════════════════════════════

_business_memory_cache = None

def load_business_memory():
    """Load the BBG business memory database (brand, calendar, history)."""
    global _business_memory_cache
    if _business_memory_cache is not None:
        return _business_memory_cache
    if BUSINESS_MEMORY_FILE.exists():
        try:
            _business_memory_cache = json.loads(BUSINESS_MEMORY_FILE.read_text())
            return _business_memory_cache
        except Exception as e:
            log(f"Error loading business memory: {e}")
    _business_memory_cache = {"business": {}, "content_calendar": {}, "post_history": []}
    return _business_memory_cache

def save_business_memory(data=None):
    """Save business memory back to disk."""
    global _business_memory_cache
    if data is not None:
        _business_memory_cache = data
    if _business_memory_cache is not None:
        BUSINESS_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _business_memory_cache["last_updated"] = datetime.now().isoformat()
        BUSINESS_MEMORY_FILE.write_text(json.dumps(_business_memory_cache, indent=2))

def record_post_to_history(platform, prompt, model, result_url, caption):
    """Record a successful social post to business memory history."""
    bm = load_business_memory()
    bm.setdefault("post_history", []).append({
        "platform": platform,
        "prompt": prompt[:200],
        "model": model,
        "result_url": result_url,
        "caption": caption[:300],
        "ts": datetime.now().isoformat(),
    })
    # Keep last 200 entries
    if len(bm["post_history"]) > 200:
        bm["post_history"] = bm["post_history"][-200:]
    save_business_memory(bm)

def get_content_suggestion(day_time=None):
    """
    Generate a smart content suggestion based on day, time, and BBG business context.
    Returns a dict with prompt, model, caption_template, and reasoning.
    """
    from datetime import datetime as dt
    bm = load_business_memory()
    now = day_time or dt.now()
    day_name = now.strftime("%A").lower()
    hour = now.hour

    business = bm.get("business", {})
    promo = business.get("current_promotion", "Buy 2 Get 1 Free")

    # Determine which calendar slot matches
    slot = None
    calendar = bm.get("content_calendar", {})

    if day_name == "friday" and hour >= 14:
        slot = calendar.get("friday_evening")
    elif day_name == "saturday":
        if hour < 12:
            slot = calendar.get("saturday_morning")
        elif hour < 18:
            slot = calendar.get("saturday_afternoon")
        else:
            slot = calendar.get("saturday_night")
    elif day_name == "sunday":
        slot = calendar.get("sunday")
    else:
        # Weekday — BBG is closed, suggest teaser/throwback
        return {
            "type": "weekday_teaser",
            "reasoning": "BBG is closed on weekdays. Suggest a throwback or weekend teaser post.",
            "prompt": "BBG mermaid looking at calendar, 'See you Saturday' text, nostalgic boardwalk vibes",
            "model": "nano-banana-pro",
            "caption_template": "friday_hype",
            "note": "Weekday post — keep it light, build anticipation for the weekend",
        }

    if not slot:
        slot = calendar.get("saturday_afternoon", {})

    examples = slot.get("example_prompts", ["BBG mermaid with beer, boardwalk energy"])
    import random
    prompt = random.choice(examples) if examples else "BBG mermaid celebrating at the beer garden"

    return {
        "type": slot.get("goal", "general"),
        "reasoning": f"{slot.get('goal', 'Content')} — {day_name.title()} {slot.get('tone', '')}",
        "prompt": prompt,
        "model": slot.get("model_pref", "nano-banana-pro"),
        "caption_template": slot.get("caption_template", "generic"),
        "best_times": slot.get("best_times", []),
        "promo": promo,
    }

def get_branded_caption(template_key, prompt, model, extra_context=None):
    """
    Generate a BBG-branded social caption from templates + hashtag bank.
    """
    import random
    bm = load_business_memory()

    templates = bm.get("caption_templates", {})
    hashtags = bm.get("hashtag_bank", {})
    business = bm.get("business", {})
    promo = business.get("current_promotion", "Buy 2 Get 1 Free")

    template = templates.get(template_key, templates.get("generic",
        "[HOOK]\\n\\n🍺 {promo}\\n\\n📍 Brighton Beach, Brooklyn\\n\\n{hashtags}"))

    # Build hashtag string
    always = " ".join(hashtags.get("always", ["#BoardwalkBeerGarden"]))
    brooklyn = " ".join(random.sample(hashtags.get("brooklyn", []), min(2, len(hashtags.get("brooklyn", [])))))
    food = " ".join(random.sample(hashtags.get("food_drink", []), min(2, len(hashtags.get("food_drink", [])))))
    vibes = " ".join(random.sample(hashtags.get("vibes", []), min(2, len(hashtags.get("vibes", [])))))

    # For weekend posts, add weekend tags
    weekend_vibes = ""
    from datetime import datetime as dt
    if dt.now().strftime("%A") in ("Saturday", "Sunday"):
        weekend_vibes = " " + " ".join(random.sample(hashtags.get("weekend_default", []), 1))

    hashtag_str = f"{always} {brooklyn} {food} {vibes}{weekend_vibes}"

    # Fill template
    caption = template.replace("{promo}", promo)
    caption = caption.replace("{hashtags}", hashtag_str)

    # Add generation attribution if space
    if len(caption) < 1800:
        caption += f"\\n\\n✨ Generated via Higgsfield AI ({model})"

    return caption[:2200]  # Instagram caption limit

def record_match(vibe_prompt, model, media_type, outcome):
    """Record a vibe→model match outcome for learning."""
    data = load_learning()
    prompt_lower = vibe_prompt.lower()

    # Extract keywords that were matched
    kw_map = VIDEO_VIBE_KEYWORDS if media_type == "video" else IMAGE_VIBE_KEYWORDS
    matched_kw = [kw for kw in kw_map.get(model, []) if kw in prompt_lower]

    data["matches"].append({
        "vibe": vibe_prompt,
        "keywords_matched": matched_kw,
        "model_chosen": model,
        "media_type": media_type,
        "outcome": outcome,
        "ts": datetime.now().isoformat(),
    })
    # Keep last 500 matches
    if len(data["matches"]) > 500:
        data["matches"] = data["matches"][-500:]

    # Update per-keyword scores
    scores = data.setdefault("model_vibe_scores", {})
    model_scores = scores.setdefault(model, {})
    for kw in matched_kw:
        entry = model_scores.setdefault(kw, {"good": 0, "bad": 0, "score": 0.5})
        if outcome == "good":
            entry["good"] += 1
        else:
            entry["bad"] += 1
        total = entry["good"] + entry["bad"]
        entry["score"] = entry["good"] / total if total > 0 else 0.5

    save_learning(data)


def get_learning_boost(model, prompt_lower, min_samples=3):
    """Get learning-based score boost for a model given the prompt."""
    data = load_learning()
    scores = data.get("model_vibe_scores", {}).get(model, {})

    kw_map = VIDEO_VIBE_KEYWORDS if _detect_media_type(prompt_lower) == "video" else IMAGE_VIBE_KEYWORDS
    matched_kw = [kw for kw in kw_map.get(model, []) if kw in prompt_lower]

    if not matched_kw:
        return 0.0

    boosts = []
    for kw in matched_kw:
        entry = scores.get(kw)
        if entry and (entry["good"] + entry["bad"]) >= min_samples:
            boosts.append(entry["score"])  # win rate 0.0–1.0

    if not boosts:
        return 0.0
    return sum(boosts) / len(boosts)


# ═══════════════════════════════════════════════════════════
# Helpers
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


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed_updates": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown",
                       reply_markup: dict = None):
    """Send a Telegram message, optionally with inline keyboard."""
    text = text[:4000]
    async with httpx.AsyncClient(timeout=15) as client:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = await client.post(
            f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage",
            json=payload,
        )
        if resp.status_code != 200:
            log(f"Send error: {resp.text[:200]}")


async def answer_callback(callback_id: str, text: str = None):
    """Answer a callback query to remove the loading spinner."""
    async with httpx.AsyncClient(timeout=5) as client:
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        await client.post(
            f"{TELEGRAM_API}/bot{BOT_TOKEN}/answerCallbackQuery",
            json=payload,
        )


async def call_higgsfield(endpoint: str, payload: dict) -> dict:
    """Call the Higgsfield router."""
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{HIGGSFIELD_ROUTER}{endpoint}",
            json=payload,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.status_code, "detail": resp.text[:300]}


# ═══════════════════════════════════════════════════════════
# Social Media Posting
# ═══════════════════════════════════════════════════════════

def generate_social_caption(prompt: str, model: str, platform: str = "instagram") -> str:
    """Generate a branded social caption using BBG business memory + templates."""
    bm = load_business_memory()
    business = bm.get("business", {})

    if platform == "instagram":
        # Use BBG brand voice with smart template selection
        from datetime import datetime as dt
        now = dt.now()
        day = now.strftime("%A")

        if day == "Friday" and now.hour >= 14:
            template_key = "friday_hype"
        elif day == "Saturday" and now.hour < 12:
            template_key = "saturday_open"
        elif day == "Saturday" and now.hour >= 20:
            template_key = "night_vibes"
        elif day == "Sunday":
            template_key = "sunday_funday"
        else:
            template_key = "generic"

        caption = get_branded_caption(template_key, prompt, model)
        # Replace [HOOK] placeholders with AI-inspired hook from prompt
        if "[HOOK" in caption:
            hook = f"🌊 {prompt[:80]}..."
            caption = caption.replace("[HOOK — what's happening right now]", hook)
            caption = caption.replace("[HOOK — first line grabs attention]", hook)
            caption = caption.replace("[HOOK", hook)

        return caption

    elif platform == "telegram":
        return (
            f"🎨 *New Higgsfield Creation*\\n\\n"
            f"_{prompt[:200]}_\\n\\n"
            f"Model: `{model}` | Generated via @Higgsfield_Creation_Bot"
        )

    # Generic fallback
    return f"{prompt[:200]}\\n\\n✨ Generated with Higgsfield AI ({model})\\n#AIart #Higgsfield #CreativeAI"


async def post_to_social(chat_id: int, platform: str, prompt: str, model: str, result_url: str):
    """
    Post a generation result to a social platform.
    Flow: create draft → auto-approve → execute
    """
    caption = generate_social_caption(prompt, model, platform)
    entity = "BBG" if platform == "instagram" else "GHS"

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Create draft
        draft_resp = await client.post(
            f"{SOCIAL_ROUTER}/draft",
            json={
                "topic": prompt[:150],
                "platforms": [platform],
                "context": f"Auto-generated from Higgsfield vibes. Model: {model}",
                "entity": entity,
                "image_url": result_url,
            },
        )
        if draft_resp.status_code != 200:
            log(f"Draft creation failed ({platform}): {draft_resp.text[:200]}")
            await send_message(chat_id, f"❌ Draft creation failed for {platform}: {draft_resp.status_code}")
            return

        drafts = draft_resp.json()
        created = drafts.get("created", [])
        if not created:
            await send_message(chat_id, f"❌ No draft created for {platform}")
            return

        draft_id = created[0]["draft_id"]
        log(f"Draft {draft_id} created for {platform}")

        # Step 2: Auto-approve
        approve_resp = await client.post(f"{SOCIAL_ROUTER}/draft/{draft_id}/approve")
        if approve_resp.status_code != 200:
            log(f"Draft approval failed: {approve_resp.text[:200]}")
            await send_message(chat_id, f"❌ Draft approval failed for {platform}")
            return

        # Step 3: Execute (post)
        exec_resp = await client.post(f"{SOCIAL_ROUTER}/post/{draft_id}/execute")
        result = exec_resp.json()

        if exec_resp.status_code == 200 and result.get("status") == "posted":
            platform_names = {"instagram": "Instagram (@boardwalkbeergarden)", "telegram": "Telegram Broadcast"}
            await send_message(chat_id,
                f"✅ *Posted to {platform_names.get(platform, platform)}!*\n\n"
                f"Draft: `{draft_id}`\n\n"
                f"Caption:\n```\n{caption[:300]}\n```")
            # Record to business memory history
            try:
                record_post_to_history(platform, prompt, model, result_url, caption)
            except Exception as e:
                log(f"Post history recording failed: {e}")
        else:
            await send_message(chat_id,
                f"⚠️ Post queued for {platform}\n"
                f"Draft: `{draft_id}`\n"
                f"Status: {result.get('status', 'unknown')}")


# ═══════════════════════════════════════════════════════════
# Vibe Matcher + Prompt Optimizer
# ═══════════════════════════════════════════════════════════

def _detect_media_type(prompt_lower: str) -> str:
    """Detect whether the user wants image or video."""
    video_hints = [
        "video", "clip", "animate", "motion", "film", "movie",
        "cinematic", "footage", "tiktok", "reel", "short",
    ]
    if any(w in prompt_lower for w in video_hints):
        return "video"
    return "image"


def match_vibe(prompt: str, media_type: str = "auto") -> tuple:
    """
    Match natural language vibe to best model.
    Returns (model_id, confidence).
    """
    prompt_lower = prompt.lower()

    if media_type == "auto":
        media_type = _detect_media_type(prompt_lower)

    kw_map = VIDEO_VIBE_KEYWORDS if media_type == "video" else IMAGE_VIBE_KEYWORDS
    scores = {}

    for model, keywords in kw_map.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score > 0:
            scores[model] = score

    # Domain boosts
    boosts = {
        "anime": (["recraft-v4-1", "kling-3"], 2),
        "manga": (["recraft-v4-1", "kling-3"], 2),
        "photo": (["seedream-4", "gpt-image-2"], 2),
        "picture": (["seedream-4", "gpt-image-2"], 2),
        "logo": (["ideogram", "recraft-v4-1"], 3),
        "text": (["ideogram"], 3),
        "character": (["soul-v2", "kling-avatars"], 2),
        "avatar": (["soul-v2", "kling-avatars"], 2),
        "dark": (["flux-kontext", "cinema-studio"], 2),
        "cyberpunk": (["flux-kontext", "cinema-studio"], 2),
        "noir": (["flux-kontext", "cinema-studio"], 2),
        "fast": (["nano-banana", "kling-2.5-turbo"], 2),
        "quick": (["nano-banana", "kling-2.5-turbo"], 2),
        "premium": (["nano-banana-pro", "google-veo3"], 2),
        "professional": (["nano-banana-pro", "google-veo3"], 2),
    }
    for kw, (models, boost) in boosts.items():
        if kw in prompt_lower:
            for m in models:
                if m in kw_map:
                    scores[m] = scores.get(m, 0) + boost

    # Learning boost (if enough samples)
    for model in list(scores.keys()):
        learn_boost = get_learning_boost(model, prompt_lower)
        if learn_boost > 0:
            scores[model] += learn_boost * 2  # scale learning weight

    if not scores:
        default = "nano-banana" if media_type == "image" else "seedance-2"
        return (default, "low")

    best = max(scores, key=scores.get)
    best_score = scores[best]

    if best_score >= 3:
        confidence = "high"
    elif best_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return (best, confidence)


def optimize_prompt(raw_prompt: str, model: str, media_type: str) -> str:
    """Apply model-specific prompt recipe to maximize single-shot quality."""
    # Check for !raw flag — skip optimization
    if raw_prompt.strip().endswith("!raw"):
        return raw_prompt.replace("!raw", "").strip()

    recipe = PROMPT_RECIPES.get(model, [])
    if not recipe:
        return raw_prompt

    optimized = raw_prompt.strip()
    prompt_lower = optimized.lower()

    for booster in recipe:
        # Don't add if already present or contradicts
        if booster.lower() not in prompt_lower:
            optimized += ", " + booster

    return optimized[:1000]


# ═══════════════════════════════════════════════════════════
# Conversational Intent Detection
# ═══════════════════════════════════════════════════════════

def detect_intent(text: str) -> str:
    """Detect user intent from natural language."""
    t = text.lower().strip()

    # Commands
    if t.startswith("/"):
        return "command"

    # Social posting — check first (highest priority after commands)
    social_patterns = [
        "post it", "post this", "put on ig", "put on instagram",
        "send to instagram", "share this", "share to", "publish",
        "post to ig", "post to instagram", "post to telegram",
        "broadcast", "post everywhere", "all platforms",
    ]
    if any(p in t for p in social_patterns):
        return "post_social"

    # Business-aware suggestions — "what should I post", "content ideas", etc.
    suggest_patterns = [
        "what should i post", "suggest", "suggestion", "content idea",
        "what to post", "help me with content", "what do i post",
        "give me ideas", "post idea", "recommend", "what would work",
        "what should go on", "need content", "need a post",
        "social media plan", "posting schedule", "what's good for",
    ]
    if any(p in t for p in suggest_patterns):
        return "suggest"

    # Models / info
    if any(p in t for p in ["what models", "show models", "catalog", "list models", "/models"]):
        return "models"
    if any(p in t for p in ["credits", "account", "balance", "/account"]):
        return "account"
    if any(p in t for p in ["presets", "templates", "/presets"]):
        return "presets"
    if any(p in t for p in ["learn", "stats", "how am i doing", "learning", "/learning"]):
        return "learning"
    if any(p in t for p in ["help", "what can you do", "commands", "/start", "/help"]):
        return "help"

    # Refinement
    refine_patterns = [
        "make it", "change the", "add more", "add a", "try again",
        "redo", "regenerate", "darker", "brighter", "bigger",
        "smaller", "different", "instead of", "replace", "remove the",
    ]
    if any(p in t for p in refine_patterns):
        return "refine"

    # Default: creative generation
    return "generate"


def extract_idea(text: str) -> str:
    """Extract a clean creative idea from rambling/spitball text."""
    # Remove conversational filler
    fillers = [
        "i want", "i need", "make me", "create", "generate", "show me",
        "i'm thinking", "something like", "you know", "like a", "kind of",
        "sort of", "maybe", "can you", "please", "just",
    ]
    idea = text.lower().strip()
    for f in fillers:
        idea = idea.replace(f, "")
    # Clean up extra spaces and commas
    idea = " ".join(idea.split()).strip(" ,.")
    # Cap at 200 chars
    return idea[:200]


def detect_social_platform(text: str) -> str:
    """Detect which social platform user wants to post to."""
    t = text.lower()
    if any(p in t for p in ["ig", "instagram", "boardwalk"]):
        return "instagram"
    if any(p in t for p in ["tg", "telegram", "broadcast"]):
        return "telegram"
    if any(p in t for p in ["everywhere", "all platforms", "all"]):
        return "all"
    # Default: primary social (Instagram for BBG)
    return "instagram"


async def post_last_generation(chat_id: int, platform: str = "instagram"):
    """Post the most recent generation to social media."""
    gen = last_generation.get(chat_id)
    if not gen or not gen.get("result_url"):
        await send_message(chat_id, "No recent generation to post. Create something first!")
        return

    await send_message(chat_id, f"📢 Posting to *{platform}*...")

    # Detect all platforms
    if platform == "all":
        for p in ["instagram", "telegram"]:
            await post_to_social(
                chat_id=chat_id, platform=p,
                prompt=gen["prompt"], model=gen["model"],
                result_url=gen["result_url"],
            )
    else:
        await post_to_social(
            chat_id=chat_id, platform=platform,
            prompt=gen["prompt"], model=gen["model"],
            result_url=gen["result_url"],
        )


async def refine_and_regenerate(chat_id: int, refinement: str):
    """Regenerate with the previous prompt + user refinement."""
    gen = last_generation.get(chat_id)
    if not gen:
        await send_message(chat_id, "Nothing to refine yet. Describe what you want and I'll create it!")
        return

    # Check if user wants to switch to video
    video_switch = any(w in refinement.lower() for w in ["video", "animate", "film", "clip", "motion"])
    media_type = "video" if video_switch else gen.get("media_type", "image")

    # Combine original prompt with refinement
    original_prompt = gen.get("vibe_prompt") or gen.get("prompt", "")
    new_prompt = f"{original_prompt}, {refinement}"

    await send_message(chat_id, f"🔄 Refining: _{refinement[:100]}_")

    if video_switch and gen.get("media_type") != "video":
        # Switching from image to video
        model = "seedance-2"  # hard rule
        await _do_generate(chat_id, model, new_prompt, source="refine", media_type="video", vibe_prompt=original_prompt)
    else:
        # Same media type, try same model
        model = gen.get("model", "nano-banana")
        if media_type == "video" and model not in VIDEO_MODELS:
            model = "seedance-2"
        await _do_generate(chat_id, model, new_prompt, source="refine", media_type=media_type, vibe_prompt=original_prompt)


# ═══════════════════════════════════════════════════════════
# Command Handlers
# ═══════════════════════════════════════════════════════════

async def handle_generate(chat_id: int, args: str):
    """Handle /generate <model> <prompt>"""
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id,
            "Usage: `/generate <model> <prompt>`\n\n"
            "Example: `/generate nano-banana a golden retriever`\n\n"
            "Use `/models` to see all available models.\n"
            "Or just describe your vibe and I'll pick the best model! 🎨")
        return

    model = parts[0].strip()
    prompt = parts[1].strip()

    if model not in MODEL_HELP:
        await send_message(chat_id,
            f"Unknown model `{model}`. Use `/models` to see all available models.\n\n"
            f"Or just send me your idea and I'll pick the best one!")
        return

    await _do_generate(chat_id, model, prompt, source="explicit")


async def handle_video(chat_id: int, args: str):
    """Handle /video <model> <prompt>"""
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id,
            "Usage: `/video <model> <prompt>`\n\n"
            "Video models:\n" +
            "\n".join(f"• `{m}` — {d}" for m, d in MODEL_HELP.items() if m in VIDEO_MODELS))
        return

    model = parts[0].strip()
    prompt = parts[1].strip()

    if model not in VIDEO_MODELS:
        await send_message(chat_id,
            f"`{model}` is not a video model. Use `/models` to see video models.")
        return

    await _do_generate(chat_id, model, prompt, source="explicit", media_type="video")


async def handle_vibe(chat_id: int, prompt: str):
    """
    Handle natural language vibe request — auto-match model + optimize prompt.
    This is the default handler for any text that doesn't match a command.
    """
    if len(prompt) < 3:
        await send_message(chat_id,
            "Send me a creative vibe and I'll generate it!\n\n"
            "Examples:\n"
            "• `dreamy sunset anime scene`\n"
            "• `dark cyberpunk city with neon`\n"
            "• `photorealistic watch on marble`\n"
            "• `cinematic film noir detective`\n"
            "• `my D&D character portrait`\n\n"
            "Or use `/generate <model> <prompt>` to pick a specific model.")
        return

    model, confidence = match_vibe(prompt)
    optimized = optimize_prompt(prompt, model, _detect_media_type(prompt.lower()))

    conf_emoji = {"high": "✅", "medium": "🤔", "low": "🎲"}
    await send_message(chat_id,
        f"{conf_emoji[confidence]} *Vibe matched:* `{model}`\n"
        f"Confidence: *{confidence}*\n\n"
        f"Optimized prompt:\n`{optimized[:300]}`\n\n"
        f"⏳ Generating...")

    await _do_generate(chat_id, model, optimized, source="vibe", vibe_prompt=prompt)


async def _do_generate(chat_id: int, model: str, prompt: str, source: str = "explicit",
                       media_type: str = "image", vibe_prompt: str = None):
    """Core generation — calls router, returns result, attaches feedback buttons."""
    is_video = model in VIDEO_MODELS
    endpoint = "/generate/video" if is_video else "/generate/image"
    payload = {"prompt": prompt, "model": model}
    if is_video:
        payload["duration"] = 5

    result = await call_higgsfield(endpoint, payload)

    if "error" in result:
        error_text = result.get("detail", str(result))[:300]
        await send_message(chat_id, f"❌ Generation failed: `{error_text}`")
        # Record failed match if vibe-based
        if source == "vibe" and vibe_prompt:
            record_match(vibe_prompt, model, media_type, "bad")
        return

    url = result.get("result_url", "")
    job_id = result.get("job_id", "?")
    status = result.get("status", "?")

    if url:
        text = (
            f"✅ *Done!*\n\n"
            f"Model: `{model}`\n"
            f"Job: `{job_id}`\n\n"
            f"[{'Watch' if is_video else 'View'} Result]({url})"
        )
    else:
        text = f"⚠️ Status: `{status}`\nJob: `{job_id}`\n\n(No URL returned — check Higgsfield dashboard)"

    # Cache for social posting
    last_generation[chat_id] = {
        "result_url": url,
        "prompt": vibe_prompt or prompt,
        "model": model,
        "media_type": media_type,
    }

    # Build inline keyboard with feedback + social buttons
    buttons_row1 = []
    if source == "vibe" and vibe_prompt:
        buttons_row1 = [
            {"text": "👍 Good match", "callback_data": f"feedback|good|{chat_id}"},
            {"text": "👎 Wrong model", "callback_data": f"feedback|bad|{chat_id}"},
        ]

    buttons_row2 = []
    if url:
        buttons_row2 = [
            {"text": "📢 Post to IG", "callback_data": f"post_to_instagram|{chat_id}"},
            {"text": "📢 Post to TG", "callback_data": f"post_to_telegram|{chat_id}"},
        ]

    keyboard_rows = []
    if buttons_row1:
        keyboard_rows.append(buttons_row1)
    if buttons_row2:
        keyboard_rows.append(buttons_row2)

    if keyboard_rows:
        keyboard = {"inline_keyboard": keyboard_rows}
        if source == "vibe" and vibe_prompt:
            text += "\n\n_Was this the right model?_"
        await send_message(chat_id, text, reply_markup=keyboard)
    else:
        await send_message(chat_id, text)

    # Record the match for learning (optimistic — feedback may override)
    if source == "vibe" and vibe_prompt:
        record_match(vibe_prompt, model, media_type, "good")  # optimistic, overridden by button


async def handle_models(chat_id: int):
    """Full categorized model catalog."""
    text = (
        "*📋 Model Catalog — 19 Models*\n\n"
        "*🖼️ Image Generation (9)*\n"
        "• `recraft-v4-1` — Vectors, 100+ styles, SVG\n"
        "• `soul-v2` — Character-consistent generation\n"
        "• `seedream-4` — ByteDance photorealism\n"
        "• `wan-2.2` — Alibaba composition\n"
        "• `nano-banana` — Quick high-quality visuals\n"
        "• `nano-banana-pro` — Premium high-quality\n"
        "• `flux-kontext` — Black Forest Labs\n"
        "• `ideogram` — Text-in-image specialist\n"
        "• `gpt-image-2` — OpenAI image gen\n\n"
        "*🎬 Video Generation (10)*\n"
        "• `seedance-2` — Flagship, 30-day unlimited\n"
        "• `kling-2.1-master` — Kuaishou master quality\n"
        "• `kling-2.5-turbo` — Kuaishou fast turbo\n"
        "• `kling-3` — Kuaishou latest, stylized\n"
        "• `kling-avatars` — LipSync Studio\n"
        "• `minimax-hailuo` — Strong realism\n"
        "• `cinema-studio` — Cinematic scenes\n"
        "• `wan-2.5` — Alibaba video gen\n"
        "• `sora-2` — OpenAI + platform presets\n"
        "• `google-veo3` — Google's video model\n\n"
        "*Commands:*\n"
        "/generate <model> <prompt> — Create an image\n"
        "/video <model> <prompt> — Create a video\n"
        "/models — This catalog\n"
        "/presets — 35 Viral Presets\n"
        "/account — Credits & balance\n"
        "/vibe — How vibe matching works\n\n"
        "*Or just describe your idea and I'll pick the best model!* 🎨"
    )
    await send_message(chat_id, text)


async def handle_start(chat_id: int):
    """Welcome message with full model header."""
    text = (
        "🎨 *Higgsfield Creative Agent*\\n\\n"
        "*19 AI Models — Image & Video*\\n\\n"
        "🖼️ *Image:* `recraft-v4-1` `soul-v2` `seedream-4` `wan-2.2` "
        "`nano-banana` `nano-banana-pro` `flux-kontext` `ideogram` `gpt-image-2`\\n\\n"
        "🎬 *Video:* `seedance-2` `kling-3` `kling-2.1-master` `kling-2.5-turbo` "
        "`kling-avatars` `minimax-hailuo` `cinema-studio` `wan-2.5` `sora-2` `google-veo3`\\n\\n"
        "*How to use:*\\n"
        "1️⃣ Describe your vibe — I pick the best model + optimize the prompt\\n"
        "2️⃣ Or use `/generate <model> <prompt>` for specific models\\n"
        "3️⃣ After generation: 📢 Post to IG/TG with BBG-branded captions\\n"
        "4️⃣ Say *\"what should I post?\"* or `/suggest` for smart content ideas\\n\\n"
        "*Try it:* `a golden retriever puppy in a sunlit field`\\n"
        "*Or:* `/generate nano-banana a cat in space`\\n\\n"
        "_I learn from feedback — tap 👍 or 👎 after each vibe generation!_\\n"
        "_I know BBG's brand, hours, promos, and posting strategy — just ask!_"
    )
    await send_message(chat_id, text)


async def handle_account(chat_id: int):
    """Check Higgsfield account."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{HIGGSFIELD_ROUTER}/account")
            if resp.status_code == 200:
                data = resp.json()
                output = data.get("output", str(data))
                await send_message(chat_id, f"💰 *Account*\n\n```\n{output[:500]}\n```")
            else:
                await send_message(chat_id, f"❌ Could not fetch account: {resp.status_code}")
    except Exception as e:
        await send_message(chat_id, f"❌ Error: {e}")


async def handle_presets(chat_id: int):
    """List viral presets."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{HIGGSFIELD_ROUTER}/presets")
        if resp.status_code == 200:
            data = resp.json()
            text = f"*35 Viral Presets* ({data['count']} total)\n\n"
            for cat, presets in list(data.get("by_category", {}).items())[:5]:
                names = ", ".join(p["name"] for p in presets[:4])
                text += f"*{cat}*: {names}\n"
            text += f"\nUse on web: higgsfield.ai/viral-presets"
            await send_message(chat_id, text)


async def handle_vibe_help(chat_id: int):
    """Explain how vibe matching works."""
    text = (
        "*🎨 Vibe Matching — How It Works*\n\n"
        "Just describe what you want in natural language — "
        "I'll pick the best model and optimize your prompt.\n\n"
        "*Examples:*\n"
        "• `dreamy anime sunset` → recraft-v4-1 (anime illustration)\n"
        "• `photorealistic product photo` → seedream-4 (photorealism)\n"
        "• `dark cyberpunk city` → flux-kontext (atmospheric scene)\n"
        "• `logo with text 'Nexus'` → ideogram (text-in-image)\n"
        "• `cinematic film noir` → cinema-studio (film scene)\n"
        "• `tiktok dance challenge` → sora-2 (social video)\n\n"
        "*I improve over time:* tap 👍 or 👎 after each generation "
        "and I'll learn which models work best for your vibes.\n\n"
        "*Skip optimization:* add `!raw` at the end of your prompt.\n"
        "`a cat !raw` → sends exactly that, no optimization."
    )
    await send_message(chat_id, text)


async def handle_learning_stats(chat_id: int):
    """Show learning statistics."""
    data = load_learning()
    matches = data.get("matches", [])
    if not matches:
        await send_message(chat_id, "No learning data yet. Generate some vibes and give feedback!")
        return

    total = len(matches)
    good = sum(1 for m in matches if m.get("outcome") == "good")
    bad = sum(1 for m in matches if m.get("outcome") == "bad")

    text = (
        f"*🧠 Learning Stats*\n\n"
        f"Total interactions: *{total}*\n"
        f"Good matches: *{good}* ✅\n"
        f"Bad matches: *{bad}* ❌\n"
        f"Win rate: *{good/total*100:.0f}%*" if total > 0 else "N/A"
    )

    # Show top performing model-vibe pairs
    scores = data.get("model_vibe_scores", {})
    if scores:
        pairs = []
        for model, kws in scores.items():
            for kw, entry in kws.items():
                total_samples = entry["good"] + entry["bad"]
                if total_samples >= 3:
                    pairs.append((model, kw, entry["score"], total_samples))
        pairs.sort(key=lambda x: x[2], reverse=True)

        if pairs:
            text += "\n\n*Top learned matches:*\n"
            for model, kw, score, n in pairs[:5]:
                text += f"• `{kw}` → `{model}` ({score*100:.0f}%, {n} samples)\n"

    await send_message(chat_id, text)


async def handle_suggest(chat_id: int):
    """Smart content suggestion based on day, time, and BBG business context."""
    from datetime import datetime as dt
    now = dt.now()

    suggestion = get_content_suggestion(now)

    bm = load_business_memory()
    business = bm.get("business", {})
    promo = business.get("current_promotion", "Buy 2 Get 1 Free")
    hours_today = business.get("hours", {}).get(now.strftime("%A").lower(), "Closed")

    best_times = suggestion.get("best_times", [])
    times_str = ", ".join(best_times) if best_times else "any time"

    text = (
        f"🧠 *Content Suggestion*\\n"
        f"_{now.strftime('%A, %B %d — %I:%M %p')}_\\n\\n"
        f"*Strategy:* {suggestion.get('reasoning', 'General content')}\\n\\n"
        f"*Suggested prompt:*\\n"
        f"`{suggestion['prompt']}`\\n\\n"
        f"*Model:* `{suggestion['model']}`\\n"
        f"*Best posting time:* {times_str}\\n"
        f"*Caption style:* `{suggestion.get('caption_template', 'generic')}`\\n\\n"
        f"🍺 *Promo:* {promo}\\n"
        f"⏰ *Hours today:* {hours_today}\\n\\n"
        f"_Tap to generate this:_ `/generate {suggestion['model']} {suggestion['prompt'][:100]}`\\n\\n"
        f"Or just say *\"make it\"* and I'll create it with the right vibe!"
    )

    # Add extra context for closed days
    if suggestion.get("type") == "weekday_teaser":
        text += f"\\n\\n💡 *Note:* BBG is closed on weekdays. "
        text += f"This is a teaser/throwback post to keep the feed active. "

    await send_message(chat_id, text)


# ═══════════════════════════════════════════════════════════
# Command Router
# ═══════════════════════════════════════════════════════════

COMMANDS = {
    "/start": handle_start,
    "/generate": handle_generate,
    "/video": handle_video,
    "/models": handle_models,
    "/account": handle_account,
    "/presets": handle_presets,
    "/help": handle_start,
    "/vibe": handle_vibe_help,
    "/learning": handle_learning_stats,
    "/suggest": handle_suggest,
}


async def process_message(msg: dict):
    """Process a single Telegram message with conversational intent detection."""
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if not text:
        return

    # Handle slash commands first (explicit user intent)
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""

        HANDLERS_WITH_ARGS = {handle_generate, handle_video}
        handler = COMMANDS.get(command)
        if handler:
            try:
                if handler in HANDLERS_WITH_ARGS:
                    await handler(chat_id, args)
                else:
                    await handler(chat_id)
            except Exception as e:
                log(f"Handler error for {command}: {traceback.format_exc()}")
                await send_message(chat_id, f"❌ Internal error: {e}")
        return

    # ── Conversational intent routing ──
    intent = detect_intent(text)

    try:
        if intent == "post_social":
            platform = detect_social_platform(text)
            await post_last_generation(chat_id, platform)

        elif intent == "refine":
            await refine_and_regenerate(chat_id, text)

        elif intent == "models":
            await handle_models(chat_id)

        elif intent == "account":
            await handle_account(chat_id)

        elif intent == "presets":
            await handle_presets(chat_id)

        elif intent == "learning":
            await handle_learning_stats(chat_id)

        elif intent == "suggest":
            await handle_suggest(chat_id)

        elif intent == "help":
            await handle_start(chat_id)

        elif intent == "generate":
            # Extract core idea from conversational text
            idea = extract_idea(text)
            if len(idea) < 3:
                await send_message(chat_id,
                    "Send me a creative vibe and I'll generate it! 🎨\n\n"
                    "Examples:\n"
                    "• `dreamy sunset anime scene`\n"
                    "• `dark cyberpunk city with neon`\n"
                    "• `photorealistic watch on marble`\n"
                    "• `cinematic film noir detective`\n"
                    "• `a golden retriever puppy in a field`\n\n"
                    "I understand natural language — just talk to me!")
                return
            await handle_vibe(chat_id, idea)

    except Exception as e:
        log(f"Intent handler error ({intent}): {traceback.format_exc()}")
        await send_message(chat_id, f"❌ Something went wrong: {e}")


async def process_callback(callback: dict):
    """Process inline keyboard callback (feedback buttons + social posting)."""
    callback_id = callback["id"]
    data = callback.get("data", "")
    msg = callback.get("message", {})
    chat_id = msg.get("chat", {}).get("id", 0)

    # ── Social posting callbacks ──
    if data.startswith("post_to_"):
        platform = data.replace("post_to_", "").split("|")[0]
        gen = last_generation.get(chat_id)
        if not gen or not gen.get("result_url"):
            await answer_callback(callback_id, "No recent generation found. Generate something first!")
            return

        await answer_callback(callback_id, f"Posting to {platform}...")
        await post_to_social(
            chat_id=chat_id,
            platform=platform,
            prompt=gen["prompt"],
            model=gen["model"],
            result_url=gen["result_url"],
        )
        return

    # ── Feedback callbacks ──
    if data.startswith("feedback|"):
        parts = data.split("|")
        if len(parts) >= 3:
            outcome = parts[1]  # "good" or "bad"
            # Update the most recent match for this chat
            learning = load_learning()
            matches = learning.get("matches", [])
            if matches:
                # Find the most recent match for this outcome update
                # We update the last match — simple heuristic
                matches[-1]["outcome"] = outcome
                # Recalculate scores
                m = matches[-1]
                model = m["model_chosen"]
                kw = m.get("keywords_matched", [])
                scores = learning.setdefault("model_vibe_scores", {})
                model_scores = scores.setdefault(model, {})
                for k in kw:
                    entry = model_scores.setdefault(k, {"good": 0, "bad": 0, "score": 0.5})
                    if outcome == "good":
                        entry["good"] += 1
                    else:
                        entry["bad"] += 1
                    total = entry["good"] + entry["bad"]
                    entry["score"] = entry["good"] / total if total > 0 else 0.5
                save_learning(learning)

            emoji = {"good": "👍 Thanks! I'll use this model more for similar vibes.",
                     "bad": "👎 Noted! I'll try different models for this kind of vibe."}
            await answer_callback(callback_id, emoji.get(outcome, ""))

            # Edit the original message to acknowledge feedback
            try:
                original_text = msg.get("text", "")
                # Remove the feedback question and add acknowledgment
                clean = original_text.split("\n\n_Was this the right")[0]
                ack = "👍 Good match!" if outcome == "good" else "👎 Wrong model — noted!"
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"{TELEGRAM_API}/bot{BOT_TOKEN}/editMessageText",
                        json={
                            "chat_id": chat_id,
                            "message_id": msg["message_id"],
                            "text": clean + f"\n\n_{ack}_",
                            "parse_mode": "Markdown",
                            "disable_web_page_preview": True,
                        },
                    )
            except Exception as e:
                log(f"Edit message error: {e}")


# ═══════════════════════════════════════════════════════════
# Polling Loop
# ═══════════════════════════════════════════════════════════

async def poll_loop():
    """Long-poll Telegram for messages + callback queries."""
    state = load_state()
    offset = 0
    processed = set(state.get("processed_updates", []))

    log(f"Bot starting — {BOT_USERNAME}")

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

                    # Handle callback queries (feedback buttons)
                    callback = update.get("callback_query")
                    if callback:
                        log(f"Callback: {callback.get('data', '')[:50]}")
                        await process_callback(callback)
                        processed.add(update_id)
                        continue

                    # Handle messages
                    msg = update.get("message")
                    if msg and "text" in msg:
                        chat_id = msg["chat"]["id"]
                        user = msg.get("from", {}).get("first_name", "?")
                        log(f"Message from {user} ({chat_id}): {msg['text'][:100]}")
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
    log("=== Higgsfield Telegram Daemon starting (v3 — vibe + optimize + learn) ===")
    try:
        asyncio.run(poll_loop())
    except KeyboardInterrupt:
        log("Shutting down.")
