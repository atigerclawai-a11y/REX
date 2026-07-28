"""
REX — Weekly AI Training Schedule
====================================
Monday through Friday, each day has a designated AI trainer and topic.
Claude always anchors Monday and Friday synthesis.

DEFAULT WEEKLY SCHEDULE:
  Monday    → Claude       (GOJ reasoning, security, adversarial review)
  Tuesday   → Grok         (animation, visual content, real-time knowledge)
  Wednesday → ChatGPT      (structured output, code, APIs, templates)
  Thursday  → Gemini       (document analysis, multimodal, long context)
  Friday    → Perplexity + Synthesis (research + REX creates hybrid lessons)

This schedule rotates topics every 4 weeks within each AI's domain.
You can override any day by editing the WEEKLY_PLAN below or via chat.

Usage:
  python rex_weekly_schedule.py --show         Show this week's schedule
  python rex_weekly_schedule.py --today        Show today's training
  python rex_weekly_schedule.py --next-week    Preview next week
  python rex_weekly_schedule.py --set-topic "tuesday" "grok" "document animation"
"""

import sys
import json
from datetime import datetime, date, timedelta
from pathlib import Path

REX_DIR = Path(__file__).parent
SCHEDULE_FILE = REX_DIR / "rex_training_schedule.json"

# ── Domain rotation pools — 4 topics per AI, rotates weekly ───────────────────

DOMAIN_ROTATIONS = {
    "claude": [
        "GOJ Operations & Scheduling Logic",
        "Security, HIPAA Compliance & Privacy",
        "Reasoning Chains & Problem Decomposition",
        "REX Architecture & Parameter Mastery",
    ],
    "grok": [
        "Animated Banner & GIF Generation",
        "Static Visual Content for GOJ",
        "Real-Time Knowledge & Current Events Integration",
        "Image Consistency & Brand Standards",
    ],
    "chatgpt": [
        "Structured JSON & Route Export Templates",
        "Python Scripting & REX Backend Extensions",
        "API Design & Dashboard Integration",
        "Billing Report Automation",
    ],
    "gemini": [
        "Medicaid Document Analysis & Extraction",
        "Multi-Page Policy PDF Comprehension",
        "Handwritten & Scanned Document OCR",
        "Long-Context Client File Review",
    ],
    "perplexity": [
        "Medicaid Regulatory Update Research",
        "Billing Code Verification & Compliance",
        "GOJ Industry Trends & Best Practices",
        "Weekly Synthesis — Hybrid Lesson Creation",
    ],
}

# ── Default weekly structure ───────────────────────────────────────────────────
DEFAULT_WEEK = {
    0: {"day": "Monday",    "trainer": "claude",      "emoji": "🧠"},
    1: {"day": "Tuesday",   "trainer": "grok",        "emoji": "⚡"},
    2: {"day": "Wednesday", "trainer": "chatgpt",     "emoji": "💬"},
    3: {"day": "Thursday",  "trainer": "gemini",      "emoji": "♊"},
    4: {"day": "Friday",    "trainer": "perplexity",  "emoji": "🔍"},
}


def _load_schedule() -> dict:
    if SCHEDULE_FILE.exists():
        try:
            return json.loads(SCHEDULE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_schedule(schedule: dict):
    SCHEDULE_FILE.write_text(json.dumps(schedule, indent=2))


def get_week_number() -> int:
    """Return current ISO week number for topic rotation."""
    return date.today().isocalendar()[1]


def get_topic_for_trainer(trainer: str, week_override: int = None) -> str:
    """Get this week's topic for a given trainer via rotation."""
    week = week_override or get_week_number()
    pool = DOMAIN_ROTATIONS.get(trainer, ["General training"])
    return pool[week % len(pool)]


def get_today_session() -> dict:
    """Return today's training session info."""
    today = date.today()
    weekday = today.weekday()  # 0=Mon, 4=Fri
    if weekday > 4:  # Weekend
        return {"day": "Weekend", "trainer": None, "topic": "Rest day — no training scheduled"}

    schedule = _load_schedule()
    override_key = today.isoformat()

    if override_key in schedule:
        entry = schedule[override_key]
        trainer = entry.get("trainer")
        topic   = entry.get("topic") or get_topic_for_trainer(trainer)
    else:
        day_info = DEFAULT_WEEK.get(weekday, {})
        trainer = day_info.get("trainer")
        topic   = get_topic_for_trainer(trainer)

    day_info = DEFAULT_WEEK.get(weekday, {"day": "Today", "emoji": "📅"})
    return {
        "date":    today.isoformat(),
        "day":     day_info["day"],
        "trainer": trainer,
        "topic":   topic,
        "emoji":   day_info.get("emoji", "📅"),
        "is_synthesis": weekday == 4,  # Friday is synthesis day
    }


def get_week_schedule(week_offset: int = 0) -> list:
    """Return the full Mon-Fri schedule for this week (or +offset weeks)."""
    today = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    schedule = _load_schedule()
    week_num = monday.isocalendar()[1]

    sessions = []
    for i in range(5):  # Mon-Fri
        day_date = monday + timedelta(days=i)
        day_info = DEFAULT_WEEK[i]
        override_key = day_date.isoformat()

        if override_key in schedule:
            entry = schedule[override_key]
            trainer = entry.get("trainer", day_info["trainer"])
            topic   = entry.get("topic") or get_topic_for_trainer(trainer, week_num)
        else:
            trainer = day_info["trainer"]
            topic   = get_topic_for_trainer(trainer, week_num)

        sessions.append({
            "date":    day_date.isoformat(),
            "weekday": day_info["day"],
            "trainer": trainer,
            "topic":   topic,
            "emoji":   day_info["emoji"],
            "is_today": day_date == today,
            "is_synthesis": i == 4,
        })
    return sessions


def set_day_override(day_name: str, trainer: str, topic: str):
    """Override a specific day's trainer and topic."""
    # Find the next occurrence of that day
    today = date.today()
    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4}
    target_weekday = day_map.get(day_name.lower())
    if target_weekday is None:
        print(f"Unknown day: {day_name}")
        return
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    target_date = (today + timedelta(days=days_ahead)).isoformat()
    schedule = _load_schedule()
    schedule[target_date] = {"trainer": trainer, "topic": topic}
    _save_schedule(schedule)
    print(f"✅ {day_name.title()} ({target_date}): {trainer} → {topic}")


def print_week_schedule(week_offset: int = 0):
    """Print a formatted week schedule."""
    sessions = get_week_schedule(week_offset)
    label = "THIS WEEK" if week_offset == 0 else f"NEXT WEEK ({week_offset}+)"
    week_of = sessions[0]["date"]

    print(f"\n{'='*60}")
    print(f"  REX TRAINING SCHEDULE — {label}")
    print(f"  Week of {week_of}")
    print(f"{'='*60}")
    for s in sessions:
        marker = " ◀ TODAY" if s["is_today"] else ""
        synthesis = " [SYNTHESIS DAY]" if s["is_synthesis"] else ""
        print(f"\n  {s['emoji']}  {s['weekday']} {s['date']}{marker}")
        print(f"     Trainer: {s['trainer'].upper()}{synthesis}")
        print(f"     Topic:   {s['topic']}")
    print(f"\n{'='*60}")
    print("  Each session ends with a 20-question quiz emailed to you.")
    print("  Say 'grade my quiz' in REX chat when ready to submit answers.")
    print(f"{'='*60}\n")


def format_schedule_for_email(week_offset: int = 0) -> tuple[str, str]:
    """Format week schedule as email (subject, html_body)."""
    sessions = get_week_schedule(week_offset)
    week_of = sessions[0]["date"]
    subject = f"📅 REX Training Schedule — Week of {week_of}"
    body = f"""
<html><body style="font-family: Arial, sans-serif; max-width: 650px; margin: 0 auto; color: #1a1a2e;">
<div style="background:#1a2f5a; color:white; padding:20px; border-radius:8px 8px 0 0;">
  <h1 style="margin:0; font-size:20px;">📅 REX Training Schedule</h1>
  <p style="margin:5px 0 0; opacity:0.8;">Week of {week_of}</p>
</div>
<div style="padding:15px;">
"""
    for s in sessions:
        bg = "#e8f4ff" if s["is_today"] else "#ffffff"
        border = "2px solid #1a2f5a" if s["is_today"] else "1px solid #dde"
        synthesis_note = "<br><small style='color:#888'>🔀 Synthesis: REX creates hybrid lessons from the week</small>" if s["is_synthesis"] else ""
        body += f"""
  <div style="margin:10px 0; padding:12px; background:{bg}; border:{border}; border-radius:6px;">
    <strong>{s['emoji']} {s['weekday']} {s['date']}{'  ◀ TODAY' if s['is_today'] else ''}</strong><br>
    Trainer: <strong>{s['trainer'].upper()}</strong>{synthesis_note}<br>
    Topic: {s['topic']}
  </div>"""
    body += """
  <p style="color:#888; font-size:13px; margin-top:20px;">
    Each session ends with a 20-question quiz emailed to you.<br>
    Say <code>grade my quiz</code> in REX chat when ready to grade.
  </p>
</div>
</body></html>"""
    return subject, body


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Weekly Training Schedule")
    parser.add_argument("--show",      action="store_true", help="Show this week")
    parser.add_argument("--today",     action="store_true", help="Show today's session")
    parser.add_argument("--next-week", action="store_true", help="Preview next week")
    parser.add_argument("--set-topic", nargs=3, metavar=("DAY", "TRAINER", "TOPIC"),
                        help="Override a day: --set-topic tuesday grok 'animation workflow'")
    args = parser.parse_args()

    if args.set_topic:
        set_day_override(*args.set_topic)
    elif args.today:
        s = get_today_session()
        print(f"\n{s['emoji']} Today ({s['day']} {s['date']})")
        print(f"  Trainer: {s['trainer'].upper() if s['trainer'] else 'None'}")
        print(f"  Topic:   {s['topic']}\n")
    elif args.next_week:
        print_week_schedule(week_offset=1)
    else:
        print_week_schedule()
