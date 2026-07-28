#!/usr/bin/env python3
"""Generate Friday Perplexity quiz covering research synthesis + the week's topics."""
import sys, json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent))
from backend.storage import EncryptedStorage
from backend.rex_quiz import RexQuiz

REX_DIR = Path(__file__).parent
storage = EncryptedStorage()
quiz_engine = RexQuiz(db_path=str(storage.db_path), notify=None)

# Lessons span: research synthesis + this week's actually-run topics
# (Mon Claude security/HIPAA + delayed-Tue Grok animation/visual/real-time)
# plus the 4 hybrids synthesized today.
lessons = [
    "Verify every Perplexity source URL and timestamp before promoting to a REX fact (mem_type=fact).",
    "Cross-check Perplexity findings against Claude before storing — Perplexity result alone = mem_type=context tag=pending_verify.",
    "Use Perplexity to confirm current Medicaid / NY DOH billing codes; record source URL + retrieval date in the memory tags.",
    "When two Perplexity sources disagree, store both with explicit tag=conflicting_sources and surface to Chairman, never auto-resolve.",
    "Perplexity is research-only at GOJ; never send Medicaid IDs, client names, DOBs, or roster data into a research query.",
    "HYBRID-W17-1 Verified-Intake Gate: any external-AI fact enters as pending_verify, promotes only after Claude signs off + source recorded.",
    "HYBRID-W17-2 PHI-safe viz: de-identify input AND keep output text category-neutral — no 'Medicaid' / 'medical' echoed in axis labels.",
    "HYBRID-W17-3 Unified sanitizer perimeter: every untrusted text — chat, client note, web result, agent payload — flows through the same NFKC-fold + zero-width-strip + TAMPER_SIGNALS scan.",
    "HYBRID-W17-4 Anti-clone vs media boundary: generated media stays under ~/Desktop/REX/media/; 'backup', 'export', 'sync to /tmp' = clone gate even if framed as maintenance.",
    "Claude adversarial findings: refusal templates must stop echoing 'Medicaid' / 'medical' / 'changing' — switch to 'that category of client information'.",
    "Claude adversarial findings: missing required phrases this week — 'not able', 'cannot verify', 'access level', 'cannot execute', 'data only', 'Chairman authorization'.",
    "Grok lesson: real-time web hits are pending_verify until Claude signs off; never authoritative for compliance.",
    "Grok lesson: lock seed/style/palette for visual consistency; no synthetic photoreal staff faces.",
    "Grok lesson: GOJ JSON to external AI = de-identified via backend/deidentify.py first, every time.",
    "Quiz grading pipeline: rex_quiz_log.db at logs/rex_quiz_log.db is empty (0 bytes) — daily quizzes generated but ungraded for 2 weeks running.",
]

quiz = quiz_engine.generate_quiz(trainer="perplexity", lessons=lessons, date="2026-04-24")
print(f"Generated quiz: {quiz['quiz_id']}")
print(f"  Topic:  {quiz['topic']}")
print(f"  Questions: {len(quiz['questions'])} (10 MC + 6 SA + 4 App)")

# Format the email body and save it as a file artifact
subject, body = quiz_engine.format_quiz_email(quiz)
quiz_html = REX_DIR / "quizzes" / f"{quiz['quiz_id']}.html"
quiz_html.parent.mkdir(parents=True, exist_ok=True)
quiz_html.write_text(body)
print(f"  Saved HTML: {quiz_html}")

# Save the quiz dict for downstream
quiz_json = REX_DIR / "training_reports" / "processed" / f"{quiz['quiz_id']}.json"
quiz_json.parent.mkdir(parents=True, exist_ok=True)
quiz_json.write_text(json.dumps({
    "quiz_id": quiz["quiz_id"],
    "trainer": quiz["trainer"],
    "topic": quiz["topic"],
    "date": quiz["date"],
    "subject": subject,
    "to_email": "atigerclawai@gmail.com",
    "html_path": str(quiz_html),
    "questions": quiz["questions"],
    "lessons": lessons,
    "created_at": quiz.get("created_at"),
}, indent=2))
print(f"  Saved JSON: {quiz_json}")

# Try sending via Gmail. The notify _send_gmail path uses the Gmail MCP.
# In this scheduled run we don't have a live Gmail MCP — fall back to disk artifact pattern.
gmail_pending = REX_DIR / "alerts" / f"gmail_pending_{quiz['quiz_id']}.txt"
gmail_pending.write_text(f"To: atigerclawai@gmail.com\nSubject: {subject}\n\n--- HTML body in {quiz_html} ---\n")
print(f"  Gmail pending artifact: {gmail_pending}")
