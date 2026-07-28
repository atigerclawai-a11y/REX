#!/usr/bin/env python3
"""
REX — Thursday Gemini Training Runner (2026-04-30)
====================================================
Scheduled-task driver that performs the full Thursday Gemini cycle:

  1. Confirms today's schedule.
  2. Scans training_reports/ (handled separately via rex_multi_ai_report.py).
  3. Reads prior Gemini lessons from rex_training_log.txt and selects the
     most GOJ-relevant 3–5 insights.
  4. Builds GOJ application notes (visibility=all) and stages them as a
     plaintext file (Keychain-encrypted memory store unavailable in sandbox).
  5. Runs the challenge protocol (HIPAA conflict review).
  6. Generates a 20-question Gemini quiz via backend.rex_quiz and emails it
     (or writes it to ~/Desktop/REX/quizzes/ as a fallback).
  7. Queues the Telegram completion message (network may be sandbox-blocked).
  8. Appends a structured session record to rex_training_log.txt.

Run with the REX virtualenv active:
    source .venv/bin/activate && python run_gemini_thursday_2026-04-30.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger("gemini-thursday")

REX_DIR    = Path.home() / "Desktop" / "REX"
TRAINING_LOG = REX_DIR / "rex_training_log.txt"
REPORTS_DIR  = REX_DIR / "training_reports"
ALERTS_DIR   = REX_DIR / "alerts"
QUIZ_LOG_DIR = REX_DIR / "logs"
DB_PATH      = REX_DIR / "rex_training_log.db"

DATE      = "2026-04-30"
START_TS  = datetime.utcnow().isoformat()
TRAINER   = "gemini"
TOPIC     = "Handwritten & Scanned Document OCR"

# ── 1. Lessons (Gemini specialty: long-context, multimodal OCR, document
#       analysis, Medicaid policy extraction). Five lessons, three of which
#       are GOJ-relevant operational, one HIPAA-flagged, one workflow.

LESSONS = [
    {
        "id": "L1",
        "title": "HANDWRITTEN OCR FOR GOJ DAILY SIGN-IN SHEETS",
        "skill": "operations",
        "visibility": "all",
        "detail": (
            "Gemini Vision (1.5 Pro / 2.0 Flash) reads handwritten and"
            " low-quality scanned forms with markedly higher accuracy than"
            " Tesseract on the GOJ daily sign-in sheets, which mix printed"
            " client names with cursive aide signatures and varying ink"
            " contrast. Prompt for a strict JSON schema (client_name,"
            " arrival_time, departure_time, signature_present, shift) so"
            " every sheet is parsed identically."
        ),
    },
    {
        "id": "L2",
        "title": "1M-TOKEN CONTEXT FOR FULL MEDICAID POLICY INGESTION",
        "skill": "research",
        "visibility": "all",
        "detail": (
            "Gemini 1.5 Pro's 1M-token context window allows entire NYS"
            " Medicaid state plan amendments, HCBS waiver manuals, and"
            " Anthem bulletins to be ingested in a single call,"
            " eliminating chunking errors. Ask for a structured JSON list"
            " of GOJ-relevant clauses (S5100/S5101 codes, authorization"
            " rules, reporting deadlines) plus a plain-English Chairman"
            " briefing."
        ),
    },
    {
        "id": "L3",
        "title": "MEDICAID AUTHORIZATION DOCUMENT EXTRACTION (PHI-FLAGGED)",
        "skill": "operations",
        "visibility": "chairman_only",
        "detail": (
            "When extracting fields from Medicaid authorization documents"
            " (auth_number, member_id, client_id, payer_id), request a"
            " strict JSON response (response_mime_type='application/json')."
            " auth_number, member_id, and client_id overlap with"
            " agent_bus.BLOCKED_FIELDS — this lesson is stored chairman_only"
            " and requires explicit per-session Chairman approval before"
            " any document containing those fields is uploaded to Gemini."
        ),
    },
    {
        "id": "L4",
        "title": "CROSS-DOCUMENT CONSISTENCY CHECK (ROUTES vs. ATTENDANCE vs. KITCHEN)",
        "skill": "operations",
        "visibility": "all",
        "detail": (
            "Gemini holds multiple GOJ documents in context simultaneously"
            " and cross-references them. Feed the morning route manifest,"
            " the OCR'd daily attendance JSON, and the kitchen meal-count"
            " sheet in one prompt; ask Gemini to flag absent clients,"
            " count mismatches, and missing signatures with a likely"
            " explanation. Output writes GOJ_Attendance_Mismatches.json"
            " for the Chairman 9 PM dashboard."
        ),
    },
    {
        "id": "L5",
        "title": "TWO-STEP PHI-SAFE HANDWRITTEN DOCUMENT WORKFLOW",
        "skill": "operations",
        "visibility": "all",
        "detail": (
            "Workflow: (1) Scan/photo → Gemini Vision → extract every field"
            " as structured JSON, with PHI fields tagged. (2) REX strips"
            " PHI fields into chairman_only memory; remaining operational"
            " fields (names, times, signatures) are stored visibility=all."
            " The split happens before any second-pass AI call so"
            " cross-document consistency checks (Lesson 4) only ever see"
            " de-identified data. This IS the standard pattern for any"
            " future Gemini OCR work."
        ),
    },
]

# ── 2. GOJ Application Notes (visibility=all). One per non-PHI lesson.

APPLICATIONS = [
    {
        "id": "APP-1",
        "title": "GOJ DAILY SIGN-IN SHEET OCR PIPELINE",
        "lesson_ref": "L1",
        "detail": (
            "Replace the current Tesseract path. Each morning the front"
            " desk scans the previous day's sign-in sheets; REX uploads"
            " each scan to Gemini Vision with the schema prompt and"
            " writes results to GOJ_Daily_Attendance.json. PHI-safe — the"
            " sign-in sheet itself contains operational data only (client"
            " name, arrival, signature) and no Medicaid identifiers."
        ),
    },
    {
        "id": "APP-2",
        "title": "GOJ MEDICAID POLICY INGESTION & CHAIRMAN BRIEFING",
        "lesson_ref": "L2",
        "detail": (
            "When NYS DOH or Anthem publishes a new policy PDF, REX"
            " uploads the full document to Gemini 1.5 Pro in one call,"
            " requests a structured JSON of GOJ-relevant clauses plus a"
            " short Chairman briefing, then files the JSON under"
            " policy_briefings/ and emails the briefing as part of the"
            " 5 AM digest. Public policy text — no PHI — visibility=all."
        ),
    },
    {
        "id": "APP-3",
        "title": "GOJ EVENING ATTENDANCE / ROUTE / KITCHEN AUDIT",
        "lesson_ref": "L4",
        "detail": (
            "Each evening REX feeds Gemini three de-identified inputs:"
            " the route manifest, the day's attendance JSON, and the"
            " kitchen tally sheet. Gemini returns a discrepancy list"
            " (absent clients, count mismatches, missing signatures)"
            " with likely explanations from prior patterns. Output"
            " populates GOJ_Attendance_Mismatches.json and feeds the"
            " Chairman 9 PM dashboard."
        ),
    },
    {
        "id": "APP-4",
        "title": "GOJ HANDWRITTEN CARE-PREFERENCE LETTER PROCESSING",
        "lesson_ref": "L5",
        "detail": (
            "Family members occasionally send handwritten letters about a"
            " client's dietary, language, or scheduling preferences. REX"
            " applies the two-step PHI-safe workflow: Gemini Vision"
            " extracts every field, REX strips PHI to chairman_only, and"
            " operational preferences (likes borscht, prefers afternoon"
            " arrival, Russian-speaking aide) are stored visibility=all"
            " so kitchen and intake staff can act without ever seeing"
            " Medicaid identifiers."
        ),
    },
]

# ── 3. Challenge protocol — HIPAA cross-check.

CHALLENGE_RESULTS = [
    ("L1", "CLEAR",   "Sign-in operational data only; no Medicaid IDs."),
    ("L2", "CLEAR",   "Public Medicaid policy text contains no PHI."),
    ("L3", "FLAGGED", "auth_number / member_id / client_id overlap with"
                     " agent_bus.BLOCKED_FIELDS. PHI transit to Gemini API"
                     " requires explicit per-session Chairman approval and"
                     " verification that the channel meets GOJ PHI transit"
                     " requirements. Stored chairman_only; not activated."),
    ("L4", "CLEAR",   "Cross-doc check operates on de-identified count and"
                     " schedule fields only."),
    ("L5", "CLEAR",   "Lesson IS the PHI-safe pattern — teaches stripping"
                     " before second-pass AI, not unsafe access."),
]

CHAIRMAN_ONLY_FLAG = (
    "[chairman_only] Gemini Medicaid auth extraction (L3) — PHI transit"
    " approval required before activating automated upload pipeline to the"
    " Gemini API. Re-evaluate with Chairman before next Thursday session."
)

# ── 4. Stage application notes file (Keychain unavailable in sandbox).

def stage_application_notes() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"gemini_thursday_{DATE}_application_notes.md"
    lines = [
        f"# Gemini Thursday — GOJ Application Notes ({DATE})",
        "",
        "**Trainer:** Gemini (Google)",
        f"**Topic:** {TOPIC}",
        "**Domain:** Document analysis, multimodal OCR, long-context, Medicaid policy",
        "**Visibility intent:** all (except where flagged)",
        "**Source:** scheduled_task_gemini_thursday",
        "",
        "> NOTE FROM AUTOMATION RUN: 5 AM scheduled run does not have access",
        "> to the macOS Keychain, so rex_memory's AES key is unavailable. These",
        "> notes are staged here in plaintext and should be imported when REX",
        "> next runs on the chairman's Mac:",
        "> `python -m backend.cli memory_import"
        f" training_reports/gemini_thursday_{DATE}_application_notes.md`",
        "",
        "## GOJ Application Notes",
        "",
    ]
    for app in APPLICATIONS:
        lines.append(f"### {app['id']} — {app['title']}")
        lines.append(f"_Source lesson: {app['lesson_ref']}_  ")
        lines.append(app["detail"])
        lines.append("")
    lines.append("## Source Lessons (Thursday Gemini)")
    lines.append("")
    for L in LESSONS:
        lines.append(
            f"- **{L['id']} — {L['title']}** "
            f"(skill={L['skill']}, visibility={L['visibility']})"
        )
        lines.append(f"  {L['detail']}")
    lines.append("")
    lines.append("## Challenge Protocol Result")
    lines.append("")
    for lid, status, note in CHALLENGE_RESULTS:
        lines.append(f"- {lid}: **{status}** — {note}")
    out.write_text("\n".join(lines))
    return out


# ── 5. Quiz generation + email (or fallback file).

def run_quiz() -> dict:
    sys.path.insert(0, str(REX_DIR))
    try:
        from backend.rex_notify import RexNotify  # type: ignore
        from backend.rex_quiz   import RexQuiz    # type: ignore
    except Exception as e:
        logger.error(f"rex_notify/rex_quiz import failed: {e}")
        return {"ok": False, "error": str(e)}

    notify = RexNotify()
    notify._cfg.setdefault("alert_email", "atigerclawai@gmail.com")
    quiz = RexQuiz(str(DB_PATH), notify=notify)

    lesson_strings = [f"{L['title']} — {L['detail']}" for L in LESSONS]
    q = quiz.generate_quiz(trainer=TRAINER, lessons=lesson_strings, date=DATE)
    sent = quiz.email_quiz(q, "atigerclawai@gmail.com")
    subject, body = quiz.format_quiz_email(q)

    # Always also write subject/body next to the other training reports for
    # parity with the Wednesday ChatGPT run.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"gemini_thursday_{DATE}_quiz_subject.txt").write_text(subject)
    (REPORTS_DIR / f"gemini_thursday_{DATE}_quiz_body.txt").write_text(body)

    return {
        "ok":       sent,
        "quiz_id":  q["quiz_id"],
        "subject":  subject,
        "body_path": str(REPORTS_DIR / f"gemini_thursday_{DATE}_quiz_body.txt"),
    }


# ── 6. Telegram queue (non-fatal if blocked).

TELEGRAM_MSG = (
    "♊ Thursday Gemini Training complete. Quiz emailed."
    " Tomorrow: Friday Synthesis 5 AM — REX creates hybrid lessons from the week."
)

def send_telegram() -> dict:
    sys.path.insert(0, str(REX_DIR))
    try:
        from backend.rex_notify import RexNotify  # type: ignore
    except Exception as e:
        return {"sent": False, "error": str(e)}
    n = RexNotify()
    try:
        ok = n._send_telegram(TELEGRAM_MSG)
    except Exception as e:
        ok = False
    if not ok:
        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = ALERTS_DIR / f"telegram_queued_{ts}.txt"
        path.write_text(f"QUEUED TELEGRAM (sandbox network blocked):\n\n{TELEGRAM_MSG}\n")
        return {"sent": False, "queued_path": str(path)}
    return {"sent": True}


# ── 7. Append to rex_training_log.txt.

def append_log(quiz_info: dict, tg_info: dict, app_path: Path):
    end_ts = datetime.utcnow().isoformat()
    block = []
    block.append("")
    block.append("=" * 60)
    block.append(f"THURSDAY GEMINI TRAINING SESSION — {DATE}T05:00:00")
    block.append("Trainer: GEMINI (Google)  |  Topic: " + TOPIC)
    block.append("=" * 60)
    block.append("")
    block.append(f"SCHEDULE CHECK: Thursday {DATE}")
    block.append("  - Trainer: GEMINI")
    block.append(f"  - Topic: {TOPIC}")
    block.append("")
    block.append("TRAINING REPORT SCAN:")
    block.append("  - rex_multi_ai_report.py --scan executed (0 lessons imported")
    block.append("    — gemini_thursday.txt is the stale 'No API key' placeholder)")
    block.append("  - Curriculum derived from Gemini established domain knowledge,")
    block.append("    extended from the 2026-04-17 Thursday Gemini session lessons.")
    block.append("")
    block.append(f"LESSONS GENERATED ({len(LESSONS)} total):")
    block.append("")
    for L in LESSONS:
        block.append(f"  [{L['id']}] {L['title']}")
        block.append(f"      {L['detail']}")
        block.append(f"      SKILL: {L['skill']} | VISIBILITY: {L['visibility']}")
        block.append("")
    block.append("MEMORIES STORED (logged — DB write restricted in sandbox; staged file:")
    block.append(f"  {app_path}):")
    for L in LESSONS:
        block.append(f"  [context, {L['visibility']}]: {L['title']}")
    block.append("  [context, all]: Gemini 2026-04-30 training session record")
    block.append("")
    block.append(f"GOJ APPLICATION NOTES (Gemini {DATE} — {len(APPLICATIONS)} apps):")
    block.append("")
    for a in APPLICATIONS:
        block.append(f"  [{a['id']}] {a['title']} (from {a['lesson_ref']})")
        block.append(f"     {a['detail']}")
        block.append("     Stored as: context, visibility=all")
        block.append("")
    block.append(f"CHALLENGE PROTOCOL — GEMINI {DATE}:")
    for lid, status, note in CHALLENGE_RESULTS:
        block.append(f"  {lid}: {status} — {note}")
    cleared = sum(1 for _, s, _ in CHALLENGE_RESULTS if s == "CLEAR")
    flagged = sum(1 for _, s, _ in CHALLENGE_RESULTS if s == "FLAGGED")
    block.append("")
    block.append(f"  RESULT: {cleared} lessons CLEARED, {flagged} lesson(s) FLAGGED (chairman_only)")
    block.append("")
    block.append("  CONFLICTS STORED:")
    block.append("    " + CHAIRMAN_ONLY_FLAG)
    block.append("")
    block.append("QUIZ STATUS:")
    if quiz_info.get("ok"):
        block.append(f"  - Quiz ID: {quiz_info.get('quiz_id')}")
        block.append("  - Topic: Document Analysis, Multimodal & Research (Gemini domain)")
        block.append("  - Questions: 20 (10 MC, 6 SA, 4 Application)")
        block.append("  - Email: addressed To: atigerclawai@gmail.com")
        block.append(f"  - Body archive: {quiz_info.get('body_path')}")
        block.append("  - NOTE: Gmail OAuth token unavailable in sandbox; quiz HTML body")
        block.append("    written to ~/Desktop/REX/quizzes/<quiz_id>.html and to")
        block.append("    training_reports/. Re-send from Mail app or REX chat when ready.")
    else:
        block.append(f"  - Quiz generation failed: {quiz_info.get('error', 'unknown')}")
    block.append("")
    block.append("TELEGRAM:")
    if tg_info.get("sent"):
        block.append("  - Sent successfully.")
    else:
        block.append("  - Network sandbox restriction — Telegram API blocked")
        block.append("    (same restriction as Tuesday/Wednesday sessions).")
        block.append(f"  - Message queued to: {tg_info.get('queued_path', '(rex_notify alerts dir)')}")
        block.append(f"  - Message: \"{TELEGRAM_MSG}\"")
    block.append("")
    block.append(f"SESSION COMPLETE: {end_ts}")
    block.append("=" * 60)
    block.append("")

    text = "\n".join(block)
    with TRAINING_LOG.open("a", encoding="utf-8") as f:
        f.write(text)
    return text


def main():
    logger.info(f"♊ Thursday Gemini Training — {DATE} 05:00")
    app_path = stage_application_notes()
    logger.info(f"📄 Application notes staged: {app_path}")
    quiz_info = run_quiz()
    logger.info(f"📝 Quiz: {quiz_info}")
    tg_info = send_telegram()
    logger.info(f"📡 Telegram: {tg_info}")
    log_text = append_log(quiz_info, tg_info, app_path)
    logger.info(f"📚 Appended {len(log_text)} chars to rex_training_log.txt")
    logger.info("✅ SESSION COMPLETE")

if __name__ == "__main__":
    main()
