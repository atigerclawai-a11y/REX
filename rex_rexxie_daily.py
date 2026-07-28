#!/usr/bin/env python3
"""
Rexxie Daily Class Scheduler
──────────────────────────────
Runs every weekday at 8:15 AM (15 min after REX's class) via launchd.

Rexxie's classes are COMPLETELY SEPARATE from REX:
  • Different subjects — personal, life, and assistant skills
  • Stored in rexxie.db (triple-encrypted), invisible to GOJ staff
  • Never cross-contaminated with REX's GOJ operations knowledge
  • Think of REX and Rexxie as two students in different programs

Weekly Rexxie Schedule:
  Monday    → Bookkeeping & Financial Tracking
  Tuesday   → Personal Finance & Wealth Awareness
  Wednesday → Health, Wellness & Care Coordination
  Thursday  → Legal Literacy & Document Understanding
  Friday    → Life Admin, Organization & Household Management
"""

import json
import sqlite3
import urllib.request
from datetime import date, datetime
from pathlib import Path

REX_DIR   = Path(__file__).parent
TG_CONFIG = REX_DIR / "rex_rexxie_telegram_config.json"
REXXIE_DB = REX_DIR / "rexxie.db"
LOG_DIR   = REX_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Rexxie weekly curriculum ───────────────────────────────────────────────────
REXXIE_CURRICULUM = {
    0: {  # Monday
        "subject":    "Bookkeeping & Financial Tracking",
        "emoji":      "📒",
        "lesson":     (
            "Today Rexxie studies bookkeeping fundamentals: recording income and expenses, "
            "reconciling accounts, understanding debits vs. credits, and reading a basic P&L statement. "
            "Focus on one real-world example — like tracking household income and expenses in a spreadsheet "
            "or understanding a simple bank statement."
        ),
        "quiz": [
            "What is the difference between a debit and a credit in bookkeeping?",
            "What does 'reconciling an account' mean?",
            "Name the three sections of a basic Profit & Loss statement.",
            "If you earn $3,500/month and spend $2,800, what is your monthly surplus?",
            "What is accounts payable? Give a household example.",
            "What is the difference between cash-basis and accrual accounting?",
            "What does 'double-entry bookkeeping' mean and why does it matter?",
            "If a business has $50,000 in assets and $32,000 in liabilities, what is its equity?",
            "Name two common bookkeeping mistakes people make when managing small business finances.",
            "What is a balance sheet and how does it differ from a P&L statement?",
        ],
    },
    1: {  # Tuesday
        "subject":    "Personal Finance & Wealth Awareness",
        "emoji":      "💰",
        "lesson":     (
            "Today Rexxie studies personal finance: budgeting methods (50/30/20 rule), "
            "understanding net worth, emergency funds, basic investing concepts (index funds, "
            "compound interest), and credit scores. Focus on one actionable step that could "
            "improve financial health this month."
        ),
        "quiz": [
            "What is the 50/30/20 budget rule?",
            "How is net worth calculated?",
            "Why is an emergency fund important, and how much should you have?",
            "What is compound interest? Give a simple example.",
            "What factors affect a credit score?",
            "What is the difference between a Roth IRA and a Traditional IRA?",
            "What does 'diversifying investments' mean and why is it important?",
            "If you invest $200/month at 7% annual return for 30 years, roughly how much will you have?",
            "What is a credit utilization ratio and what percentage is considered healthy?",
            "Name two expenses most people overlook when building a monthly budget.",
        ],
    },
    2: {  # Wednesday
        "subject":    "Health, Wellness & Care Coordination",
        "emoji":      "🌿",
        "lesson":     (
            "Today Rexxie studies health and wellness tracking: organizing medical records, "
            "tracking medications and appointments, understanding health insurance basics (deductible, "
            "copay, out-of-pocket max), and building healthy daily habits. Focus on one practical "
            "system for keeping health records organized."
        ),
        "quiz": [
            "What is the difference between a deductible and a copay?",
            "Name three things that should be in an organized personal health file.",
            "What is an 'out-of-pocket maximum' in health insurance?",
            "Why is it important to keep a list of current medications?",
            "Name two health habits that have the highest impact on long-term wellbeing.",
            "What is the difference between an HMO and a PPO health plan?",
            "What information should you bring to a new doctor's appointment?",
            "Why is preventive care important, and what does insurance typically cover for free?",
            "What is a Health Savings Account (HSA) and who qualifies for one?",
            "Name three warning signs that someone may be experiencing caregiver burnout.",
        ],
    },
    3: {  # Thursday
        "subject":    "Legal Literacy & Document Understanding",
        "emoji":      "⚖️",
        "lesson":     (
            "Today Rexxie studies legal literacy: understanding common contracts (leases, service agreements), "
            "knowing your rights as a consumer and tenant, recognizing red flags in documents, "
            "understanding when to consult a lawyer vs. handling something yourself. "
            "Focus on one type of contract Rexxie is likely to encounter."
        ),
        "quiz": [
            "What should you always check before signing any contract?",
            "What is the difference between a void and a voidable contract?",
            "Name two red flags in a service agreement that should make you pause.",
            "When should you consult a lawyer rather than signing on your own?",
            "What rights does a tenant typically have if a landlord fails to make repairs?",
            "What is a power of attorney and when would you need one?",
            "What is the difference between a will and a living will?",
            "What does 'indemnification' mean in a contract?",
            "What is small claims court and what types of disputes is it used for?",
            "Name two consumer rights you have when a product is defective.",
        ],
    },
    4: {  # Friday
        "subject":    "Life Admin, Organization & Household Management",
        "emoji":      "🏠",
        "lesson":     (
            "Today Rexxie studies life admin: building a household management system "
            "(tracking warranties, subscriptions, important documents, renewals), setting up "
            "a master contacts list, managing utilities, and creating a home maintenance calendar. "
            "Focus on one system that reduces stress and saves time."
        ),
        "quiz": [
            "Name five categories of important documents every household should have organized.",
            "What is a subscription audit and why should you do one annually?",
            "How would you set up a home maintenance calendar?",
            "What should a master emergency contacts list include?",
            "Name two ways to reduce household expenses without major lifestyle changes.",
            "What household tasks should be done monthly vs. annually?",
            "What is the best way to track warranties and product manuals?",
            "How would you create a simple system to never miss a bill due date?",
            "What documents should always be kept in physical form, not just digital?",
            "Name three things to do within the first week of moving into a new home.",
        ],
    },
}

# ── Telegram ───────────────────────────────────────────────────────────────────
def _tg(text: str):
    if not TG_CONFIG.exists():
        return
    try:
        cfg   = json.loads(TG_CONFIG.read_text())
        token = cfg.get("bot_token", "")
        cid   = cfg.get("owner_chat_id", 0)
        if not token or not cid:
            return
        payload = json.dumps({"chat_id": cid, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=12):
            pass
    except Exception as e:
        print(f"⚠  Telegram failed: {e}")

# ── Log lesson to rexxie.db ────────────────────────────────────────────────────
def _log_lesson(today: date, lesson: dict):
    try:
        conn = sqlite3.connect(str(REXXIE_DB))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rexxie_daily_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT NOT NULL,
                subject  TEXT NOT NULL,
                lesson   TEXT NOT NULL,
                quiz_sent INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO rexxie_daily_log (date, subject, lesson, quiz_sent) VALUES (?, ?, ?, 1)",
            (today.isoformat(), lesson["subject"], lesson["lesson"][:500])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠  Rexxie log failed: {e}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    today   = date.today()
    weekday = today.weekday()

    if weekday >= 5:
        print(f"ℹ  {today.strftime('%A')} — no Rexxie class today")
        return

    lesson = REXXIE_CURRICULUM.get(weekday)
    if not lesson:
        return

    print(f"\n{'='*55}")
    print(f"  REXXIE DAILY CLASS — {today.strftime('%A %B %d, %Y')}")
    print(f"  Subject: {lesson['emoji']} {lesson['subject']}")
    print(f"{'='*55}\n")

    # Build lesson message
    lesson_lines = [
        f"📚 <b>Rexxie's Class — {lesson['emoji']} {lesson['subject']}</b>",
        f"📅 {today.strftime('%A, %B %d, %Y')}",
        f"",
        f"<b>Today's Lesson:</b>",
        lesson["lesson"],
        f"",
        f"─────────────────────────",
        f"<b>Today's 10 Questions:</b>",
        f"(Answer when ready — say <b>'rexxie quiz'</b> to start)",
        f"",
        f"🔒 <i>Class content is always generic — Rexxie never uses your personal details in lessons or questions.</i>",
        f"",
    ]
    for i, q in enumerate(lesson["quiz"], 1):
        lesson_lines.append(f"<b>{i}.</b> {q}")

    _tg("\n".join(lesson_lines))
    _log_lesson(today, lesson)

    print(f"✅  Rexxie class sent: {lesson['subject']}")

if __name__ == "__main__":
    main()
