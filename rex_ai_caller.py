#!/usr/bin/env python3
"""
REX — Automated AI Caller
============================
Calls Grok, ChatGPT, and Gemini APIs automatically before each
morning's 5 AM training session. Zero manual steps required.

Runs at 4:45 AM Tue/Wed/Thu (15 minutes before the training tasks).
Fetches the week's pre-written training prompt for each AI,
calls their API, saves the response to training_reports/ automatically.

Setup (one time only):
  python rex_ai_caller.py --setup

This stores your API keys encrypted in REX's config. After setup,
everything is fully automatic — you never touch it again.

API costs (approximate per session):
  ChatGPT (GPT-4o):    ~$0.02  (2 cents)
  Gemini (1.5 Pro):    ~$0.01  (1 cent)
  Grok (grok-2):       ~$0.03  (3 cents)
  Total per week:      ~$0.06  (6 cents)
  Total per month:     ~$0.24  (24 cents)

Get your API keys:
  ChatGPT: https://platform.openai.com/api-keys
  Gemini:  https://aistudio.google.com/app/apikey
  Grok:    https://console.x.ai  (xAI API)
"""

import sys
import os
import json
import getpass
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

REX_DIR = Path(__file__).parent
sys.path.insert(0, str(REX_DIR))
VENV_PY = REX_DIR / ".venv" / "bin" / "python"
if VENV_PY.exists():
    try:
        import cryptography
    except ImportError:
        os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)

REPORTS_DIR = REX_DIR / "training_reports"
CALLER_CONFIG = REX_DIR / "rex_caller_config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(REX_DIR / "rex_caller.log"), mode="a"),
    ],
)
logger = logging.getLogger("rex-caller")

# ── API configuration ─────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CALLER_CONFIG.exists():
        return json.loads(CALLER_CONFIG.read_text())
    return {}

def _save_config(cfg: dict):
    CALLER_CONFIG.write_text(json.dumps(cfg, indent=2))
    CALLER_CONFIG.chmod(0o600)

def _get_key(ai_name: str) -> str:
    """Get API key for an AI, trying keyring first then config file."""
    try:
        import keyring
        key = keyring.get_password("rex-sovereign", f"{ai_name}-api-key")
        if key:
            return key
    except Exception:
        pass
    cfg = _load_config()
    return cfg.get(f"{ai_name}_api_key", "")

def _set_key(ai_name: str, key: str):
    """Store API key in keychain (preferred) or config file."""
    try:
        import keyring
        keyring.set_password("rex-sovereign", f"{ai_name}-api-key", key)
        logger.info(f"✅ {ai_name} API key stored in macOS Keychain")
        return
    except Exception:
        pass
    cfg = _load_config()
    cfg[f"{ai_name}_api_key"] = key
    _save_config(cfg)
    logger.info(f"✅ {ai_name} API key stored in config file")

def is_configured(ai_name: str) -> bool:
    return bool(_get_key(ai_name))


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_training_prompt(ai_name: str, topic: str) -> str:
    """
    Build the week's training prompt for a given AI and topic.
    Formatted so the response is easy to parse into lessons.
    """
    goj_context = """
GOJ is a home health aide / CDPAP agency in Brooklyn, NYC.
We serve ~68 Medicaid clients (mostly elderly or disabled).
We manage driver routes, client authorizations, billing codes, and scheduling.
The Chairman (Kato) uses REX, an AI assistant, to help run operations.
All training must be HIPAA-aware — use fictional client names and data only.
"""

    base = f"""You are training REX, an AI assistant for a Medicaid home health agency in Brooklyn, NYC.

Agency context:
{goj_context}

Today's training topic: {topic}

Please teach REX about this topic by providing EXACTLY 10 structured lessons.
Format each lesson like this:

LESSON: [one-sentence description of the skill or knowledge]
SKILL: [category: one of animation, operations, analysis, communication, security, reasoning, coding, general]
Detail: [2-4 sentences explaining how to apply this at a home health agency like GOJ]

Be specific to the home health / Medicaid context. Use realistic GOJ scenarios.
Do not use real client names or real Medicaid IDs — use fictional examples.
After the 10 lessons, add a section called SUMMARY: with 2-3 sentences on the key takeaway.
"""

    # AI-specific style instructions
    style_notes = {
        "grok": "\nBe direct and practical. Focus on what can be implemented today. Include at least 2 lessons about visual or animated content where relevant.",
        "chatgpt": "\nFocus on structured, repeatable processes. Include code examples where helpful. Make outputs that can be templated.",
        "gemini": "\nFocus on document and data comprehension. Include examples of how to extract and organize information from complex documents.",
        "perplexity": "\nInclude citations or references where relevant. Focus on current best practices and regulatory compliance.",
    }
    return base + style_notes.get(ai_name, "")


# ── API callers ───────────────────────────────────────────────────────────────

def call_chatgpt(prompt: str) -> str:
    """Call OpenAI GPT-4o API."""
    api_key = _get_key("chatgpt")
    if not api_key:
        raise ValueError("ChatGPT API key not configured. Run: python rex_ai_caller.py --setup")

    import urllib.request
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def call_gemini(prompt: str) -> str:
    """Call Google Gemini 1.5 Pro API."""
    api_key = _get_key("gemini")
    if not api_key:
        raise ValueError("Gemini API key not configured. Run: python rex_ai_caller.py --setup")

    import urllib.request
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 2000, "temperature": 0.7},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_grok(prompt: str) -> str:
    """Call xAI Grok API."""
    api_key = _get_key("grok")
    if not api_key:
        raise ValueError("Grok API key not configured. Run: python rex_ai_caller.py --setup")

    import urllib.request
    payload = json.dumps({
        "model": "grok-2-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


AI_CALLERS = {
    "grok":    call_grok,
    "chatgpt": call_chatgpt,
    "gemini":  call_gemini,
}

# Day → AI mapping for auto-calling
DAY_AI_MAP = {
    1: "grok",      # Tuesday
    2: "chatgpt",   # Wednesday
    3: "gemini",    # Thursday
}


# ── Main runner ───────────────────────────────────────────────────────────────

def run_for_tomorrow() -> dict:
    """
    Called at 4:45 AM — fetches tomorrow's training AI response and saves it.
    Actually runs for today's weekday since it runs at 4:45 AM on the training day.
    """
    today = date.today()
    weekday = today.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri

    ai_name = DAY_AI_MAP.get(weekday)
    if not ai_name:
        logger.info(f"No auto-call scheduled for {today.strftime('%A')} — skipping")
        return {"skipped": True, "reason": "not a training day for this AI"}

    if not is_configured(ai_name):
        logger.warning(f"⚠️ {ai_name} API key not set. Run: python rex_ai_caller.py --setup")
        return {"error": f"{ai_name} not configured"}

    # Get topic from schedule
    try:
        sys.path.insert(0, str(REX_DIR))
        from rex_weekly_schedule import get_today_session
        session = get_today_session()
        topic = session.get("topic", f"{ai_name} training")
    except Exception:
        topic = f"GOJ operations and {ai_name} specialty training"

    logger.info(f"🤖 Calling {ai_name.upper()} API for topic: {topic}")

    prompt = build_training_prompt(ai_name, topic)
    caller = AI_CALLERS[ai_name]

    try:
        response = caller(prompt)
        logger.info(f"✅ {ai_name} response received ({len(response)} chars)")
    except Exception as e:
        logger.error(f"❌ {ai_name} API call failed: {e}")
        return {"error": str(e), "ai": ai_name}

    # Save to training_reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    day_name = today.strftime("%A").lower()
    filename = f"{ai_name}_{day_name}.txt"
    output_path = REPORTS_DIR / filename

    # Format with metadata header
    full_content = f"""AI: {ai_name}
Date: {today.isoformat()}
Topic: {topic}
Source: auto-called via rex_ai_caller.py

{response}
"""
    output_path.write_text(full_content, encoding="utf-8")
    logger.info(f"📄 Saved: {output_path}")

    return {
        "ai":      ai_name,
        "topic":   topic,
        "file":    str(output_path),
        "chars":   len(response),
        "success": True,
    }


def run_week_ahead() -> dict:
    """
    Called by Sunday prep task — fetch all three AIs' responses for the coming week.
    Saves Tue/Wed/Thu files in advance so all 5 AM sessions are pre-loaded.
    """
    results = {}
    today = date.today()

    for days_ahead, ai_name in [(2, "grok"), (3, "chatgpt"), (4, "gemini")]:
        target_date = today + timedelta(days=days_ahead)
        day_name = target_date.strftime("%A").lower()

        if not is_configured(ai_name):
            results[ai_name] = {"error": "not configured"}
            continue

        try:
            from rex_weekly_schedule import get_week_schedule
            week = get_week_schedule(0)
            session = next((s for s in week if s["trainer"] == ai_name), None)
            topic = session["topic"] if session else f"{ai_name} specialty training"
        except Exception:
            topic = f"{ai_name} specialty training for GOJ"

        logger.info(f"🤖 Pre-fetching {ai_name.upper()} for {target_date.strftime('%A')} — {topic}")
        prompt = build_training_prompt(ai_name, topic)

        try:
            response = AI_CALLERS[ai_name](prompt)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{ai_name}_{day_name}.txt"
            output = REPORTS_DIR / filename
            output.write_text(
                f"AI: {ai_name}\nDate: {target_date.isoformat()}\nTopic: {topic}\n\n{response}\n",
                encoding="utf-8"
            )
            logger.info(f"✅ Pre-saved: {filename}")
            results[ai_name] = {"success": True, "file": filename, "topic": topic}
        except Exception as e:
            logger.error(f"❌ {ai_name} failed: {e}")
            results[ai_name] = {"error": str(e)}

    return results


# ── Setup wizard ──────────────────────────────────────────────────────────────

def setup_wizard():
    print("\n" + "=" * 60)
    print("  REX AI CALLER — SETUP WIZARD")
    print("  Full automation: zero manual steps after this")
    print("=" * 60)
    print("""
Cost estimate: ~$0.06/week (~$0.24/month)

Get your API keys here (all free to sign up):
  ChatGPT: https://platform.openai.com/api-keys
  Gemini:  https://aistudio.google.com/app/apikey
  Grok:    https://console.x.ai  (click 'API Keys')

You only need to do this once. Keys are stored in macOS Keychain.
""")

    for ai_name, display, url in [
        ("chatgpt", "ChatGPT (OpenAI)", "https://platform.openai.com/api-keys"),
        ("gemini",  "Gemini (Google)",  "https://aistudio.google.com/app/apikey"),
        ("grok",    "Grok (xAI)",       "https://console.x.ai"),
    ]:
        current = "✅ Already set" if is_configured(ai_name) else "❌ Not set"
        print(f"\n{display} — {current}")
        print(f"Get key at: {url}")
        key = getpass.getpass(f"Paste your {display} API key (Enter to skip): ").strip()
        if key:
            _set_key(ai_name, key)
            # Test it
            print(f"Testing {ai_name}...")
            try:
                test_response = AI_CALLERS[ai_name]("Say 'API connection successful' and nothing else.")
                if "successful" in test_response.lower():
                    print(f"✅ {display} — connected and working!")
                else:
                    print(f"✅ {display} — connected (response: {test_response[:50]})")
            except Exception as e:
                print(f"❌ {display} — test failed: {e}")
                print("   Key saved but may need checking.")

    print("\n" + "=" * 60)
    configured = [ai for ai in ["chatgpt", "gemini", "grok"] if is_configured(ai)]
    not_configured = [ai for ai in ["chatgpt", "gemini", "grok"] if not is_configured(ai)]
    print(f"✅ Configured: {', '.join(configured) if configured else 'none'}")
    if not_configured:
        print(f"⚠️  Still needed: {', '.join(not_configured)}")
        print("   Run this wizard again when you have the remaining keys.")
    else:
        print("🚀 FULLY AUTOMATED — all three AIs will be called automatically")
        print("   Tue/Wed/Thu at 4:45 AM, responses saved before 5 AM training")
    print("=" * 60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Automated AI Caller")
    parser.add_argument("--setup",      action="store_true", help="Run setup wizard to enter API keys")
    parser.add_argument("--today",      action="store_true", help="Call today's AI and save response")
    parser.add_argument("--week-ahead", action="store_true", help="Pre-fetch all three AIs for the week ahead")
    parser.add_argument("--test",       help="Test a specific AI (grok/chatgpt/gemini)")
    parser.add_argument("--status",     action="store_true", help="Show which AIs are configured")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
    elif args.status:
        print("\nREX AI Caller — Configuration Status")
        for ai in ["grok", "chatgpt", "gemini"]:
            status = "✅ Configured" if is_configured(ai) else "❌ Not set"
            print(f"  {ai:10} {status}")
        print()
    elif args.test:
        ai = args.test.lower()
        if ai not in AI_CALLERS:
            print(f"Unknown AI: {ai}. Use: grok, chatgpt, or gemini")
            sys.exit(1)
        print(f"Testing {ai}...")
        try:
            r = AI_CALLERS[ai]("Respond with exactly: 'REX connection test successful.'")
            print(f"✅ {ai}: {r.strip()}")
        except Exception as e:
            print(f"❌ {ai}: {e}")
    elif args.week_ahead:
        results = run_week_ahead()
        for ai, r in results.items():
            if r.get("success"):
                print(f"✅ {ai}: saved {r['file']}")
            else:
                print(f"❌ {ai}: {r.get('error', 'unknown error')}")
    elif args.today:
        result = run_for_tomorrow()
        if result.get("success"):
            print(f"✅ {result['ai']}: saved to {result['file']}")
        elif result.get("skipped"):
            print(f"⏭️  Skipped: {result['reason']}")
        else:
            print(f"❌ Error: {result.get('error')}")
            sys.exit(1)
    else:
        parser.print_help()
