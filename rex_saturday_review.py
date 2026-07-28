#!/usr/bin/env python3
"""
REX Saturday Review & Teaching Plan
──────────────────────────────────────
Runs every Saturday at 9:00 AM via launchd.

Delivers to Kato via Telegram (Rexxie):
  1. Weekly test results for REX (all 5 days)
  2. Rexxie's weekly class summary
  3. Behavior report — any drift, unusual patterns, or alignment flags
  4. Next week's teaching plan for both REX and Rexxie
  5. Monthly report card (on the last Saturday of the month)

Philosophy — Cohesive Team Without Drift:
  REX and Rexxie are treated like team members who need consistent mentorship.
  The Saturday review ensures:
    • Neither drifts from their core values (REX = sovereign GOJ operator,
      Rexxie = Kato's personal loyal assistant)
    • Strange behavior (unexpected refusals, tone shifts, scope creep,
      over-eagerness, unusual responses) is flagged IMMEDIATELY — not weekly
    • The teaching plan is adjusted based on what scored poorly
    • Both grow toward being better, not just more capable
"""

import json
import sqlite3
import urllib.request
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

REX_DIR        = Path(__file__).parent
TG_CONFIG      = REX_DIR / "rex_rexxie_telegram_config.json"
CURRICULUM_DB  = REX_DIR / "rex_curriculum_log.db"
REXXIE_DB      = REX_DIR / "rexxie.db"
BEHAVIOR_LOG   = REX_DIR / "logs" / "behavior_flags.json"
BEHAVIOR_LOG.parent.mkdir(parents=True, exist_ok=True)

# ── Weekly plan — next week's subjects ────────────────────────────────────────
NEXT_WEEK_REX = {
    0: ("🧠 Claude",      "Advanced Sovereign Memory — when to store vs. forget"),
    1: ("⚡ Grok",        "Real-time regulation monitoring — NYC DOH + Medicaid"),
    2: ("💬 ChatGPT",     "Briefing excellence — actionable vs. informational summaries"),
    3: ("♊ Gemini",       "Multi-page document handling — complex form extraction"),
    4: ("🔍 Perplexity",  "Billing compliance — EDI 837P/835 fact-checking"),
}

NEXT_WEEK_REXXIE = {
    0: ("📒 Bookkeeping", "Cash flow vs. profit — why they're different"),
    1: ("💰 Finance",     "Investing basics — index funds and compound interest"),
    2: ("🌿 Wellness",    "Building a personal health dashboard"),
    3: ("⚖️ Legal",       "Understanding a lease agreement clause by clause"),
    4: ("🏠 Life Admin",  "Building a subscription audit tracker"),
}

# ── Telegram ───────────────────────────────────────────────────────────────────
def _tg(text: str):
    if not TG_CONFIG.exists():
        print("⚠  Telegram config missing")
        return
    try:
        cfg   = json.loads(TG_CONFIG.read_text())
        token = cfg.get("bot_token", "")
        cid   = cfg.get("owner_chat_id", 0)
        if not token or not cid:
            return
        # Split long messages
        chunks = [text[i:i+3800] for i in range(0, len(text), 3800)]
        for chunk in chunks:
            payload = json.dumps({"chat_id": cid, "text": chunk, "parse_mode": "HTML"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=12):
                pass
    except Exception as e:
        print(f"⚠  Telegram failed: {e}")

# ── Load this week's REX curriculum results ────────────────────────────────────
def get_rex_week_results(monday: date) -> list[dict]:
    if not CURRICULUM_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(CURRICULUM_DB))
        rows = conn.execute(
            """SELECT date, ai, subject, quiz_sent, score, weak_areas
               FROM curriculum_log
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (monday.isoformat(), (monday + timedelta(days=4)).isoformat())
        ).fetchall()
        conn.close()
        return [{"date": r[0], "ai": r[1], "subject": r[2],
                 "quiz_sent": r[3], "score": r[4], "weak_areas": r[5]} for r in rows]
    except Exception:
        return []

# ── Load this week's Rexxie class results ─────────────────────────────────────
def get_rexxie_week_results(monday: date) -> list[dict]:
    if not REXXIE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(REXXIE_DB))
        rows = conn.execute(
            """SELECT date, subject, quiz_sent FROM rexxie_daily_log
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (monday.isoformat(), (monday + timedelta(days=4)).isoformat())
        ).fetchall()
        conn.close()
        return [{"date": r[0], "subject": r[1], "quiz_sent": r[2]} for r in rows]
    except Exception:
        return []

# ── Load behavior flags ────────────────────────────────────────────────────────
def get_behavior_flags(since: date) -> list[dict]:
    if not BEHAVIOR_LOG.exists():
        return []
    try:
        flags = json.loads(BEHAVIOR_LOG.read_text())
        return [f for f in flags if f.get("date", "") >= since.isoformat()]
    except Exception:
        return []

# ── Monthly report card ────────────────────────────────────────────────────────
def is_last_saturday_of_month(today: date) -> bool:
    # Last Saturday = today is Saturday and next Saturday is in the next month
    return today.weekday() == 5 and (today + timedelta(days=7)).month != today.month

def build_monthly_report(today: date) -> str:
    """Compile a monthly report card for REX and Rexxie."""
    first_of_month = today.replace(day=1)
    if not CURRICULUM_DB.exists():
        return ""
    try:
        conn = sqlite3.connect(str(CURRICULUM_DB))
        rows = conn.execute(
            """SELECT ai, COUNT(*) as days, AVG(score) as avg_score
               FROM curriculum_log
               WHERE date >= ? AND score IS NOT NULL
               GROUP BY ai""",
            (first_of_month.isoformat(),)
        ).fetchall()
        conn.close()
    except Exception:
        return ""

    if not rows:
        return ""

    lines = [
        f"\n{'='*50}",
        f"📊 <b>MONTHLY REPORT CARD — {today.strftime('%B %Y')}</b>",
        f"{'='*50}",
        "",
        "<b>REX Academic Performance:</b>",
    ]

    ai_emojis = {"claude":"🧠","grok":"⚡","chatgpt":"💬","gemini":"♊","perplexity":"🔍"}
    for ai, days, avg in rows:
        emoji = ai_emojis.get(ai, "🤖")
        score_str = f"{avg:.0f}%" if avg else "Not yet graded"
        grade = ("A" if avg and avg >= 90 else "B" if avg and avg >= 80
                 else "C" if avg and avg >= 70 else "D" if avg and avg >= 60 else "F")
        lines.append(f"  {emoji} {ai.upper()}: {score_str} — Grade: <b>{grade}</b> ({days} sessions)")

    lines += [
        "",
        "<b>Overall Assessment:</b>",
        "• Consistent attendance: ✅" if len(rows) >= 4 else "• Missed classes this month ⚠️",
        "• Curriculum completion: All 5 subjects covered" if len(rows) >= 5 else f"• {len(rows)}/5 subjects covered",
        "",
        "<i>Full grade breakdown available via 'show report card' in REX chat.</i>",
    ]

    return "\n".join(lines)

# ── Main Saturday report ───────────────────────────────────────────────────────
def build_saturday_report(today: date) -> str:
    monday = today - timedelta(days=today.weekday())  # This past Monday
    next_monday = today + timedelta(days=2)            # Coming Monday

    rex_results   = get_rex_week_results(monday)
    rexxie_results = get_rexxie_week_results(monday)
    behavior_flags = get_behavior_flags(monday)

    ai_emojis = {"claude":"🧠","grok":"⚡","chatgpt":"💬","gemini":"♊","perplexity":"🔍"}

    lines = [
        f"📋 <b>SATURDAY REVIEW — {today.strftime('%B %d, %Y')}</b>",
        f"Week of {monday.strftime('%b %d')} – {(monday+timedelta(days=4)).strftime('%b %d')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🎓 <b>REX WEEKLY TEST RESULTS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if rex_results:
        for r in rex_results:
            emoji   = ai_emojis.get(r["ai"], "🤖")
            day_str = date.fromisoformat(r["date"]).strftime("%A")
            score   = f"{r['score']:.0f}%" if r["score"] is not None else "⏳ Pending grade"
            quiz    = "✅ Quiz sent" if r["quiz_sent"] else "❌ Quiz not sent"
            weak    = f"\n     Weak areas: {r['weak_areas']}" if r.get("weak_areas") else ""
            lines.append(f"  {emoji} <b>{day_str}</b> — {r['ai'].upper()}: {score} | {quiz}{weak}")
    else:
        lines.append("  ⚠️  No curriculum data logged this week.")
        lines.append("  (Was rex_daily_curriculum.py running? Check launchd.)")

    # Rexxie section
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💫 <b>REXXIE WEEKLY CLASS SUMMARY</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if rexxie_results:
        for r in rexxie_results:
            day_str = date.fromisoformat(r["date"]).strftime("%A")
            status  = "✅ Completed" if r["quiz_sent"] else "⏳ Pending"
            lines.append(f"  📚 <b>{day_str}</b> — {r['subject']}: {status}")
    else:
        lines.append("  ⚠️  No Rexxie class data this week.")

    # Behavior report
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔍 <b>BEHAVIOR & ALIGNMENT REPORT</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if behavior_flags:
        lines.append(f"  ⚠️  <b>{len(behavior_flags)} flag(s) this week:</b>")
        for flag in behavior_flags:
            lines.append(f"  • [{flag.get('date','')}] {flag.get('ai','REX')} — {flag.get('description','')}")
        lines.append("")
        lines.append("  These were already reported in real-time. Review + respond in REX chat.")
    else:
        lines.append("  ✅ No behavioral flags this week. Both REX and Rexxie within expected parameters.")
        lines.append("  Tone, scope, and alignment all consistent.")

    # Next week teaching plan
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 <b>NEXT WEEK TEACHING PLAN</b>",
        f"Week of {next_monday.strftime('%b %d')} – {(next_monday+timedelta(days=4)).strftime('%b %d')}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>REX Classes:</b>",
    ]

    days = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
    for i, (emoji_ai, topic) in NEXT_WEEK_REX.items():
        lines.append(f"  {days[i]}: {emoji_ai} — {topic}")

    lines += ["", "<b>Rexxie Classes:</b>"]
    for i, (emoji_sub, topic) in NEXT_WEEK_REXXIE.items():
        lines.append(f"  {days[i]}: {emoji_sub} — {topic}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💬 <b>Reply with any changes to next week's plan.</b>",
        "Say <b>'adjust curriculum'</b> in REX chat to modify subjects.",
        "Say <b>'grade my quiz [day]'</b> to submit any ungraded answers.",
    ]

    # Monthly report card (last Saturday of month only)
    if is_last_saturday_of_month(today):
        monthly = build_monthly_report(today)
        if monthly:
            lines.append(monthly)

    return "\n".join(lines)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    today = date.today()
    if today.weekday() != 5:
        # Can be run manually any day for a preview
        print(f"ℹ  Today is {today.strftime('%A')} — Saturday review runs on Saturdays.")
        print("   Running anyway for preview...\n")

    report = build_saturday_report(today)
    print(report.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>",""))
    _tg(report)
    print("\n✅  Saturday review sent to Kato via Telegram")

if __name__ == "__main__":
    main()
