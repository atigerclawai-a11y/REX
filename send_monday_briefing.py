#!/usr/bin/env python3
"""
Monday topic briefing — one-shot Telegram sender.
Run from: ~/Desktop/REX/
Usage: python send_monday_briefing.py
"""
import json
import urllib.request
from pathlib import Path

config_path = Path(__file__).parent / "rex_rexxie_telegram_config.json"
cfg = json.loads(config_path.read_text())

token   = cfg["bot_token"]
chat_id = cfg.get("owner_chat_id") or cfg.get("chairman_chat_id")

message = """📋 Good morning Kato — Monday topic briefing:

🧠 THIS WEEK'S SPECIAL TOPIC: Teaching REX autonomous Cowork ability — reading a task, breaking it down, executing steps, reporting results. Claude handles the reasoning architecture today (Monday 5 AM already ran). ChatGPT Wednesday handles the implementation code patterns.

📧 TOMORROW'S DISCUSSION: Email assistant capability — using Perplexity (research the person/company) + Claude (write the message) + REX (remember all context and follow-ups). Ready to map this out whenever you want.

📅 SCHEDULE CHANGE WINDOW: If you want to swap any AI or topic this week, reply here or open REX chat. After 9 AM today the week is locked.

🔑 ACTION NEEDED: Run python rex_ai_caller.py --setup on your Mac to enable full automation (takes 5 minutes, costs ~$0.06/week)."""

url     = f"https://api.telegram.org/bot{token}/sendMessage"
payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
req     = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=10) as resp:
    result = json.loads(resp.read())
    if result.get("ok"):
        print("✅ Telegram message sent successfully.")
    else:
        print(f"❌ Telegram error: {result}")
