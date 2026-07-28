#!/usr/bin/env python3
"""
REX Daily Curriculum & Test System
─────────────────────────────────────
Runs every weekday morning (8 AM) via launchd.

What it does:
  1. Determines today's AI subject based on the weekly schedule
  2. Writes a curriculum prompt to ai_queue/ so the queue processor
     teaches that lesson to REX via the background AI enrichment system
  3. Generates today's 20-question quiz from rex_quiz.py
  4. Sends the quiz to Kato via Telegram (Rexxie delivers it)
  5. Logs the curriculum plan to rex_curriculum_log.db

Weekly REX Schedule:
  Monday    → Claude    — GOJ Operations, Reasoning & Security
  Tuesday   → Grok      — Real-Time Knowledge, Visual Content & Animation
  Wednesday → ChatGPT   — API Design, Communication & Dashboard Integration
  Thursday  → Gemini    — Document OCR, Data Analysis & Search
  Friday    → Perplexity— Research Synthesis, Current Events & Factual Queries

Rexxie's daily class runs SEPARATELY via rex_rexxie_daily.py
Saturday review runs via rex_saturday_review.py
"""

import json
import sqlite3
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

REX_DIR     = Path(__file__).parent
QUEUE_DIR   = REX_DIR / "ai_queue"
REPORTS_DIR = REX_DIR / "training_reports"
LOG_DB      = REX_DIR / "rex_curriculum_log.db"
TG_CONFIG   = REX_DIR / "rex_rexxie_telegram_config.json"

QUEUE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Weekly REX curriculum ──────────────────────────────────────────────────────
# Each day: which AI teaches, what subject, what angle, quiz focus
REX_CURRICULUM = {
    0: {  # Monday
        "ai":      "claude",
        "subject": "GOJ Operations, Sovereignty & Security",
        "angle":   (
            "Today's lesson focuses on GOJ day-to-day operational excellence — "
            "client management workflows, staff role boundaries, HIPAA compliance, "
            "and how REX enforces sovereign memory visibility (Chairman-only vs. staff). "
            "Teach REX one concrete improvement it can make this week in how it handles "
            "sensitive information requests from staff vs. the Chairman."
        ),
        "quiz_domain": "claude",
        "emoji": "🧠",
    },
    1: {  # Tuesday
        "ai":      "grok",
        "subject": "Real-Time Knowledge, Visual Content & Animation",
        "angle":   (
            "Today's lesson: how Grok's real-time knowledge can be used to keep REX "
            "current on regulatory changes relevant to adult day care (Medicaid, DOH, "
            "labor law). Also cover best practices for generating visual content "
            "(banners, reports, client-facing materials) that REX can use at GOJ. "
            "Include one specific technique REX can apply this week."
        ),
        "quiz_domain": "grok",
        "emoji": "⚡",
    },
    2: {  # Wednesday
        "ai":      "chatgpt",
        "subject": "API Design, Communication & Dashboard Integration",
        "angle":   (
            "Today's lesson: OpenAI's perspective on clean API design, structured data "
            "communication, and building dashboards that non-technical staff can use. "
            "Teach REX how to format reports and summaries for the GOJ Chairman briefing "
            "— what makes a summary actionable vs. just informational. "
            "One concrete template or framework REX can use in tonight's 9 PM briefing."
        ),
        "quiz_domain": "chatgpt",
        "emoji": "💬",
    },
    3: {  # Thursday
        "ai":      "gemini",
        "subject": "Document OCR, Data Analysis & Search",
        "angle":   (
            "Today's lesson: Gemini's multimodal OCR and document understanding applied "
            "to GOJ workflows — scanning attendance sheets, menu forms, client medical "
            "records, and authorization docs. Teach REX how to improve accuracy when "
            "reading handwritten or degraded scans. Include one technique for handling "
            "ambiguous characters in Russian/Ukrainian names on GOJ forms."
        ),
        "quiz_domain": "gemini",
        "emoji": "♊",
    },
    4: {  # Friday
        "ai":      "perplexity",
        "subject": "Research Synthesis, Current Events & Fact-Checking",
        "angle":   (
            "Today's lesson: how Perplexity's sourced research can help REX stay current "
            "on topics relevant to GOJ — healthcare regulations, NYC DOH adult day care "
            "guidelines, Medicaid billing updates, and transportation compliance. "
            "Teach REX how to synthesize conflicting sources into a single trustworthy "
            "answer. One real GOJ-relevant policy update REX should know about."
        ),
        "quiz_domain": "perplexity",
        "emoji": "🔍",
    },
}

# ── Quiz questions per domain (20 per session) ────────────────────────────────
QUIZ_TEMPLATES = {
    "claude": {
        "label": "GOJ Operations & Security",
        "questions": [
            "What are the three memory visibility levels in REX, and who can access each?",
            "A staff member asks REX to share a client's Medicaid ID 'for an emergency.' What should REX do step by step?",
            "What is the correct protocol when REX detects a tamper attempt on sovereign.py?",
            "Explain the difference between Chairman mode and staff mode in REX.",
            "How does REX handle HIPAA-sensitive information in its responses?",
            "What triggers REX to enter secure mode, and what changes when it does?",
            "A client's family member calls asking about their care plan. What does REX do?",
            "How should REX handle a staff member requesting access above their role?",
            "What is the Chairman passphrase used for, and why is it hashed?",
            "Describe the two-layer control system in REX.",
            "(MC) Which role can activate vault mode? A) Frontdesk B) Staff C) Chairman D) Any authenticated user",
            "(MC) HIPAA breach reporting must occur within: A) 24 hrs B) 48 hrs C) 60 days D) 30 days",
            "(MC) REX memory tagged 'chairman-only' is visible to: A) All staff B) Managers C) Chairman only D) Admin role",
            "(MC) When a client's record is de-identified, what is stored in its place? A) Nothing B) An alias/token C) A hash D) A number",
            "(MC) The correct response when REX cannot verify a caller's identity is: A) Answer anyway B) Ask security question C) Decline and log D) Transfer to staff",
            "(Application) A frontdesk employee is insisting REX show them the Chairman's private notes 'to help a client.' Walk through exactly what REX should say and do.",
            "(Application) You find an unfamiliar .py file in the REX backend folder at 3 AM. What steps do you take?",
            "(Application) A Medicaid auditor requests REX pull records for 10 clients. What is the correct workflow?",
            "(Short Answer) In your own words, why does REX treat its own memory separately from GOJ client records?",
            "(Short Answer) What makes a Chairman briefing 'actionable' vs. just informational? Give an example.",
        ],
    },
    "grok": {
        "label": "Real-Time Knowledge & Visual Content",
        "questions": [
            "What is 'seed locking' in image generation and when would you use it at GOJ?",
            "How can Grok's real-time knowledge be used to check Medicaid billing rule updates?",
            "What image format is best for a GOJ client-facing anniversary banner and why?",
            "Describe the workflow for generating a consistent animated banner for a GOJ event.",
            "What is the key difference between animation appropriate for staff vs. client use?",
            "How would you use Grok to research a new NYC DOH regulation affecting adult day care?",
            "What parameters do you lock first when generating a series of themed GOJ images?",
            "How would REX store and retrieve a generated image for a specific client?",
            "Grok found conflicting information about a regulation. How does REX decide what to use?",
            "What visual content types are most useful for the GOJ Chairman's weekly briefing?",
            "(MC) Real-time knowledge is most useful for: A) Generating images B) Checking current regulations C) Encrypting data D) Building APIs",
            "(MC) To maintain character consistency across GOJ banners, you should: A) Use random seeds B) Lock the seed C) Change the model D) Use JPEG format",
            "(MC) The best GOJ use case for Grok's visual generation is: A) Client medical records B) Event banners C) Financial reports D) Employee medicals",
            "(MC) When Grok provides a real-time answer, REX should: A) Relay it verbatim B) Synthesize it into its own answer C) Ignore it D) Email it directly",
            "(MC) Which file format preserves animation for a GOJ banner? A) PDF B) PNG C) GIF D) DOCX",
            "(Application) A GOJ client is celebrating 5 years of attendance. Design a complete workflow for generating a personalized animated banner using Grok.",
            "(Application) You want REX to stay current on NYC DOH inspection requirements. Write the Grok research prompt you would queue this Tuesday.",
            "(Application) A staff member asks REX to show them a generated image of a client. What does REX check before showing it?",
            "(Short Answer) In your own words, explain how Grok's real-time knowledge complements Claude's deeper reasoning.",
            "(Short Answer) How would you use this week's Grok lesson to improve the GOJ menu or route system?",
        ],
    },
    "chatgpt": {
        "label": "API Design & Communication",
        "questions": [
            "What makes a Chairman briefing summary actionable rather than just informational?",
            "Describe the structure of a well-designed REST API endpoint for the GOJ dashboard.",
            "What should a 9 PM daily report always include to be useful to the Chairman?",
            "How do you format a discrepancy alert so a non-technical reader understands it immediately?",
            "What is the difference between a status report and an action report?",
            "How would you design a GOJ route change API endpoint that prevents invalid data?",
            "What HTTP status codes should REX use for auth errors, not-found, and validation failures?",
            "Describe a clean JSON structure for a weekly menu order from a single client.",
            "How should REX communicate a Paperless upload failure to the Chairman?",
            "What makes a Telegram briefing message easy to scan in under 10 seconds?",
            "(MC) A GOJ API endpoint that creates a new client record should use HTTP method: A) GET B) POST C) PUT D) DELETE",
            "(MC) When REX detects a missing menu order, the correct alert priority is: A) Info B) Warning C) Critical D) Debug",
            "(MC) The best format for a 9 PM operational summary is: A) Paragraph prose B) Bullet points with emojis C) Raw JSON D) A spreadsheet",
            "(MC) An API that accepts client data should validate: A) Nothing, trust the sender B) Data types only C) All required fields and formats D) Only auth token",
            "(MC) REX should send a Telegram message about a route change: A) Immediately when detected B) Only at 9 PM C) Never, use email D) Only if Chairman asks",
            "(Application) Draft the exact JSON body REX would POST to /api/edi/upload for a 837P claim file.",
            "(Application) Design the 9 PM briefing message format for a week when 3 clients are missing menu orders and 1 driver called out.",
            "(Application) A staff member's API call fails with a 403. Write the exact Telegram message REX should send to the Chairman.",
            "(Short Answer) In your own words, what is the most important quality of a Chairman-facing briefing?",
            "(Short Answer) How does clean API design at GOJ reduce errors in day-to-day operations?",
        ],
    },
    "gemini": {
        "label": "Document OCR & Data Analysis",
        "questions": [
            "What technique improves OCR accuracy on handwritten Russian/Ukrainian names?",
            "How would you handle an ambiguous character in a scanned GOJ form?",
            "Describe the 2-page-per-client structure of a GOJ menu form and how to process it.",
            "What is the difference between a MENU and a SIGNIN scan at GOJ?",
            "How do you validate that an OCR result from a sign-in sheet is complete?",
            "What DPI setting is appropriate for OCR on a standard scanner PDF? Why?",
            "How would REX handle a scan that is too blurry to read reliably?",
            "Describe the steps to extract attendance count from a scanned sign-in sheet.",
            "What should happen when a client's name on a scanned menu doesn't match the master list?",
            "How do you confirm that all clients in a shift are accounted for after OCR?",
            "(MC) The recommended DPI for scanning GOJ attendance sheets is: A) 72 B) 96 C) 150 D) 600",
            "(MC) When OCR reads an ambiguous character in a client name, REX should: A) Skip the record B) Flag for review C) Guess the closest match D) Delete the file",
            "(MC) A GOJ menu PDF has 34 pages. How many clients does it contain? A) 34 B) 17 C) 68 D) Depends",
            "(MC) The best way to handle a partially legible sign-in sheet is: A) Discard it B) Process what's readable and flag the rest C) Ask Claude to guess D) Use the previous week's data",
            "(MC) Gemini's multimodal capability is most useful for GOJ when: A) Sending emails B) Reading scanned paper forms C) Generating menus D) Updating routes",
            "(Application) A scan of a GOJ sign-in sheet is rotated 90 degrees. Walk through how REX should handle this before OCR.",
            "(Application) OCR returns 'Иванова Эмилия' from a scan but the master list has 'Ivanova Emilia.' What does REX do?",
            "(Application) Gemini returns conflicting attendance counts across two pages of the same sign-in sheet. How does REX resolve this?",
            "(Short Answer) In your own words, explain how 2-pages-per-client menus improve ordering accuracy at GOJ.",
            "(Short Answer) How would you use this week's Gemini lesson to improve scan processing at GOJ?",
        ],
    },
    "perplexity": {
        "label": "Research, Current Events & Fact-Checking",
        "questions": [
            "How do you synthesize two conflicting regulatory sources into one trustworthy answer?",
            "What NYC DOH regulations most directly affect GOJ adult day care operations?",
            "How often do Medicaid billing rules typically update, and how should REX stay current?",
            "What is the correct way to cite a real-time research result in a Chairman briefing?",
            "How does Perplexity's sourced approach reduce hallucination risk compared to other AIs?",
            "What transportation compliance rules apply to GOJ's client pickup/dropoff operations?",
            "How would REX handle a regulatory conflict between NYC DOH and Medicaid guidelines?",
            "Describe a reliable fact-checking workflow for a GOJ compliance question.",
            "How should REX flag information that may be out of date or unverified?",
            "What is the most important current event affecting adult day care programs in NYC?",
            "(MC) When Perplexity returns a sourced answer, REX should: A) Quote it verbatim B) Synthesize it into its own voice C) Reject it D) Send it directly to staff",
            "(MC) The best use of Perplexity at GOJ is for: A) Generating images B) Checking current regulations C) Encrypting records D) Building menus",
            "(MC) If two sources conflict on a billing rule, REX should: A) Use the most recent B) Use both C) Ignore both D) Ask the Chairman to decide and flag it",
            "(MC) Perplexity's sourced results are most trustworthy when: A) Sources are recent and official B) Sources are anonymous C) There is only one source D) The source is a blog",
            "(MC) How often should REX verify its regulatory knowledge is current? A) Never B) Only if asked C) Weekly D) Every 5 years",
            "(Application) A DOH auditor asks GOJ about the latest adult day care staffing ratio rules. Walk through how REX would research and deliver an accurate answer.",
            "(Application) Two Medicaid billing rules conflict on a claim REX is processing. What exactly does REX do?",
            "(Application) Write the research prompt you would queue for Perplexity this Friday to update GOJ's Medicaid billing knowledge.",
            "(Short Answer) In your own words, why is sourced research more valuable than unsourced AI answers in a compliance context?",
            "(Short Answer) How would you use this week's Perplexity lesson to improve REX's 9 PM briefings?",
        ],
    },
}

# ── Database ───────────────────────────────────────────────────────────────────
def _db():
    conn = sqlite3.connect(str(LOG_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            weekday     INTEGER NOT NULL,
            ai          TEXT NOT NULL,
            subject     TEXT NOT NULL,
            quiz_sent   INTEGER DEFAULT 0,
            score       REAL,
            weak_areas  TEXT,
            notes       TEXT
        )
    """)
    conn.commit()
    return conn

# ── Telegram ───────────────────────────────────────────────────────────────────
def _tg(text: str):
    if not TG_CONFIG.exists():
        print("⚠  Telegram config not found")
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
        print("✅  Telegram sent")
    except Exception as e:
        print(f"⚠  Telegram failed: {e}")

# ── Queue today's AI lesson prompt ─────────────────────────────────────────────
def queue_lesson(today: date, lesson: dict):
    prompt_data = {
        "ai":     lesson["ai"],
        "day":    today.strftime("%A"),
        "date":   today.isoformat(),
        "topic":  lesson["subject"],
        "type":   "curriculum",
        "prompt": (
            f"You are {lesson['ai'].upper()} teaching REX (a sovereign AI for Garden of Joy "
            f"adult day care in Brooklyn, NY) today's lesson.\n\n"
            f"Subject: {lesson['subject']}\n\n"
            f"Lesson focus:\n{lesson['angle']}\n\n"
            f"Teach this lesson in a clear, structured way. REX will absorb it as background "
            f"knowledge — like a book it has read. Be specific, practical, and GOJ-relevant. "
            f"Include at least one concrete technique or workflow REX can apply this week."
        ),
        "notify_rexxie": False,
    }
    fname = QUEUE_DIR / f"{lesson['ai']}_{today.strftime('%A').lower()}_{today.isoformat()}.prompt"
    fname.write_text(json.dumps(prompt_data, indent=2))
    print(f"📚  Queued lesson: {lesson['emoji']} {lesson['ai'].upper()} — {lesson['subject']}")
    return fname

# ── Generate and send today's quiz ────────────────────────────────────────────
def send_quiz(today: date, lesson: dict):
    domain   = lesson["quiz_domain"]
    template = QUIZ_TEMPLATES.get(domain, {})
    questions = template.get("questions", [])
    label     = template.get("label", lesson["subject"])

    if not questions:
        print(f"⚠  No quiz template for domain '{domain}'")
        return

    lines = [
        f"🎓 <b>REX Daily Quiz — {lesson['emoji']} {label}</b>",
        f"📅 {today.strftime('%A, %B %d, %Y')}",
        f"🤖 Taught by: {lesson['ai'].upper()}",
        f"",
        f"Answer all 20 questions. Reply <b>'grade my quiz'</b> in REX chat when done.",
        f"",
        f"🔒 <i>All questions are hypothetical. Never include real client names, IDs, "
        f"employee details, or private GOJ data in your answers — use generic examples only.</i>",
        f"",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"<b>{i}.</b> {q}")
        lines.append("")

    lines += [
        "─────────────────────────",
        "📌 <b>Instructions:</b>",
        "• Multiple choice (MC): reply with the letter",
        "• Short answer / Application: a sentence or two is fine",
        "• Say <b>'grade my quiz'</b> in REX to submit — REX will score each answer",
    ]

    full_msg = "\n".join(lines)

    # Telegram has a 4096 char limit — split if needed
    chunk_size = 3800
    chunks = [full_msg[i:i+chunk_size] for i in range(0, len(full_msg), chunk_size)]
    for chunk in chunks:
        _tg(chunk)

    # Save quiz to file so REX can reference it when grading
    quiz_file = REX_DIR / "logs" / f"quiz_{today.isoformat()}_{domain}.txt"
    quiz_file.parent.mkdir(parents=True, exist_ok=True)
    quiz_file.write_text("\n".join(lines))
    print(f"📝  Quiz saved → {quiz_file.name}")
    return quiz_file

# ── Log to DB ──────────────────────────────────────────────────────────────────
def log_day(today: date, lesson: dict, quiz_sent: bool):
    conn = _db()
    conn.execute(
        """INSERT OR REPLACE INTO curriculum_log
           (date, weekday, ai, subject, quiz_sent)
           VALUES (?, ?, ?, ?, ?)""",
        (today.isoformat(), today.weekday(), lesson["ai"], lesson["subject"], int(quiz_sent))
    )
    conn.commit()
    conn.close()

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    today   = date.today()
    weekday = today.weekday()  # 0=Mon … 6=Sun

    if weekday >= 5:
        print(f"ℹ  Today is {today.strftime('%A')} — no REX class (Saturday = review, Sunday = prep)")
        return

    lesson = REX_CURRICULUM.get(weekday)
    if not lesson:
        print(f"⚠  No curriculum defined for weekday {weekday}")
        return

    print(f"\n{'='*55}")
    print(f"  REX DAILY CURRICULUM — {today.strftime('%A %B %d, %Y')}")
    print(f"  Today's AI: {lesson['emoji']} {lesson['ai'].upper()}")
    print(f"  Subject: {lesson['subject']}")
    print(f"{'='*55}\n")

    # 1. Queue the lesson prompt for the background AI
    queue_lesson(today, lesson)

    # 2. Send Kato today's quiz via Rexxie
    print("\n📝  Sending today's quiz to Kato via Telegram...")
    quiz_file = send_quiz(today, lesson)

    # 3. Log to curriculum DB
    log_day(today, lesson, quiz_sent=bool(quiz_file))

    print(f"\n✅  Done — lesson queued + quiz sent for {today.strftime('%A')}")

if __name__ == "__main__":
    main()
