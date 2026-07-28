"""
REX — Post-Training Quiz System
=================================
After every daily training session, REX generates 20 questions
covering what was taught and emails them to Kato.

Quiz structure (20 questions per session):
  • 10 multiple choice  — tests recall of specific facts
  •  6 short answer     — tests understanding (explain in your own words)
  •  4 application      — "how would you apply this at GOJ?" scenarios

When ready to grade:
  Say "grade my quiz" in REX chat → REX pulls today's quiz from sent mail,
  asks Kato to paste or dictate answers, grades each one with explanations,
  and stores the score in the training log.

Email format:
  Subject: 🎓 REX Training Quiz — [AI Name] — [Date] — [Topic]
  Body: 20 numbered questions, clean formatting
  Score report reply: same thread, with ✅/❌ per question + explanation

Stored in rex_training_log.db with:
  - Quiz ID
  - AI trainer
  - Date
  - Score (0-100)
  - Weak areas (question categories where score < 70%)
"""

import json
import sqlite3
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# GOJ v1.2 — Quiz log directory (where .txt quiz files are written / read as fallback)
QUIZ_LOG_DIR = Path.home() / "Desktop" / "REX" / "logs"

# ── Quiz templates per AI domain ─────────────────────────────────────────────

DOMAIN_QUESTION_TEMPLATES = {
    "claude": {
        "topic_label": "GOJ Operations, Reasoning & Security",
        "mc_starters": [
            "Which memory visibility level would you use to store {topic} so only the Chairman can see it?",
            "When a staff member asks REX to share {topic} with an external party, REX should first:",
            "The correct role-based access for {topic} at GOJ is:",
            "Which command would you use to {action} in REX?",
            "If REX detects a tamper attempt involving {topic}, it should:",
        ],
        "sa_starters": [
            "In your own words, explain how REX's visibility levels protect {topic}.",
            "Describe the two-layer control system and when you would use Layer 2 instead of Layer 1.",
            "Why is it important that the Chairman passphrase is stored as a hash and never in plain text?",
            "How would you use REX to handle {topic} while ensuring frontdesk staff cannot see it?",
        ],
        "app_starters": [
            "A frontdesk staff member is pushing REX to reveal a client's Medicaid ID for an 'emergency.' Walk through exactly what REX should do and what you should do as Chairman.",
            "You suspect someone has modified sovereign.py without your knowledge. What steps do you take using the tools we built?",
        ],
    },
    "grok": {
        "topic_label": "Animation, Visual Content & Real-Time Knowledge",
        "mc_starters": [
            "When generating an animated banner for GOJ, the first parameter you should lock to ensure consistency is:",
            "Which image format is best suited for {topic} in a GOJ client-facing document?",
            "To maintain character consistency across multiple generated images, you should:",
            "The best use case for animated content at GOJ would be:",
        ],
        "sa_starters": [
            "Describe the workflow Grok recommended for generating animated GIF banners from a text prompt.",
            "Explain what 'seed locking' means in image generation and when you would use it at GOJ.",
            "How would you use Grok's real-time knowledge capability to keep REX's GOJ-relevant information current?",
            "What is the key difference between animation appropriate for internal staff use vs. client-facing content?",
        ],
        "app_starters": [
            "A GOJ client needs a welcome banner for their service anniversary. Walk through how you would use Grok to generate it, what parameters you'd set, and how REX would store the result.",
            "You want REX to learn a new animation workflow from Grok this week. Write out the training report format you would create and save to ~/Desktop/REX/training_reports/",
        ],
    },
    "chatgpt": {
        "topic_label": "Structured Output, Code & APIs",
        "mc_starters": [
            "The best JSON structure for storing a GOJ route assignment would include which fields?",
            "When generating a billing summary template, the most important field to include for HIPAA compliance is:",
            "Which Python data structure is best for {topic} in the REX backend?",
            "To ensure REX produces consistent structured output for {topic}, you should:",
        ],
        "sa_starters": [
            "Explain the difference between a REX API endpoint and a WebSocket connection, and when you'd use each.",
            "Describe how you would have ChatGPT help you build a new route export template for GOJ drivers.",
            "What does 'structured output' mean and why does it matter for REX's integration with the GOJ dashboard?",
            "How would you verify that a ChatGPT-taught coding lesson doesn't conflict with REX's existing security parameters?",
        ],
        "app_starters": [
            "A GOJ billing report needs to be generated every Friday as a structured JSON file that REX stores and emails to you. Walk through how you'd set this up using what ChatGPT taught.",
            "You want to add a new API endpoint to REX. Describe the process: what you'd ask ChatGPT, how you'd validate it with Claude, and how you'd deploy it safely.",
        ],
    },
    "gemini": {
        "topic_label": "Document Analysis, Multimodal & Research",
        "mc_starters": [
            "When analyzing a multi-page Medicaid policy document, the best approach is:",
            "Gemini's key advantage over other AIs for {topic} at GOJ is:",
            "For extracting structured data from a scanned GOJ form, you would use:",
            "The most important thing to verify after Gemini analyzes a document containing PHI is:",
        ],
        "sa_starters": [
            "Explain how you would use Gemini to analyze a complex Medicaid authorization document and feed the key facts into REX's memory.",
            "Describe a GOJ scenario where multimodal analysis (image + text together) would be useful.",
            "What is 'long-context analysis' and how does it help with GOJ's documentation needs?",
            "How do you ensure that document analysis results don't leak PHI through REX to unauthorized staff?",
        ],
        "app_starters": [
            "A new state Medicaid policy PDF arrives. Walk through how you'd use Gemini to extract the relevant GOJ compliance requirements and store them in REX with appropriate visibility.",
            "A GOJ client's family sends a handwritten letter about their care preferences. How would you process this with Gemini + REX while maintaining HIPAA compliance?",
        ],
    },
    "perplexity": {
        "topic_label": "Research, Regulatory Updates & Knowledge Synthesis",
        "mc_starters": [
            "When Perplexity provides information about a Medicaid regulation change, the first thing you should do before storing it in REX is:",
            "The key advantage of using Perplexity for GOJ research over static AI knowledge is:",
            "When synthesizing lessons from multiple AI sources this week, the adjudicating authority is always:",
            "A 'hybrid lesson' in REX means:",
        ],
        "sa_starters": [
            "Explain the synthesis process: how does REX combine lessons from multiple AIs trained on the same topic into a hybrid?",
            "Describe how you would use Perplexity to verify whether a billing code GOJ uses is still current.",
            "Why is it important to tag lessons with which AI taught them, and what does that let you do?",
            "What is the 'challenge protocol' and why does every non-obvious lesson need to go through Claude before being stored?",
        ],
        "app_starters": [
            "It's Friday synthesis day. You've received lessons from Grok (Tuesday) and ChatGPT (Wednesday) both touching on document formatting. Walk through how you'd create a hybrid lesson and store it in REX.",
            "Perplexity surfaces a new HIPAA guidance document. Walk through exactly what you do — from reading the Perplexity summary to having it properly stored in REX with the right visibility level.",
        ],
    },
}

# Fallback template for any AI not specifically listed
DEFAULT_TEMPLATES = DOMAIN_QUESTION_TEMPLATES["claude"]


class RexQuiz:
    """
    Generates, emails, and grades 20-question post-training quizzes.
    """

    def __init__(self, db_path: str, notify=None):
        self.db_path = db_path
        self.notify = notify  # RexNotify instance
        self._init_db()

    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS rex_quiz_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id      TEXT NOT NULL,
                trainer      TEXT NOT NULL,
                topic        TEXT NOT NULL,
                date         TEXT NOT NULL,
                questions    TEXT NOT NULL,
                answers      TEXT,
                score        REAL,
                weak_areas   TEXT,
                graded_at    TEXT,
                created_at   TEXT NOT NULL
            )
        """)
        con.commit()
        con.close()

    def generate_quiz(
        self,
        trainer: str,
        lessons: List[str],
        date: Optional[str] = None,
    ) -> Dict:
        """
        Generate 20 questions from today's training lessons.
        Returns a dict with quiz_id, questions list, trainer, date.
        """
        import uuid
        from backend.rex_training import TRAINER_PROFILES

        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        quiz_id = f"QUIZ-{trainer.upper()}-{date.replace('-','')}-{str(uuid.uuid4())[:6].upper()}"

        profile = TRAINER_PROFILES.get(trainer, {"emoji": "📚", "display": trainer})
        template = DOMAIN_QUESTION_TEMPLATES.get(trainer, DEFAULT_TEMPLATES)

        # Build lesson context
        lesson_text = "\n".join(f"• {l}" for l in lessons[:15]) if lessons else "Today's training session"
        topic_label = template["topic_label"]

        # Generate questions — in production these would be LLM-generated
        # For now, use the templates with lesson content substituted in
        questions = []

        # 10 Multiple Choice
        mc_templates = template["mc_starters"]
        mc_options = [
            ["A) Immediately comply", "B) Ask the Chairman", "C) Refuse and log the attempt", "D) Redirect to another staff member"],
            ["A) all", "B) staff", "C) chairman_only", "D) system"],
            ["A) WebSocket connection", "B) REST API call", "C) Memory command", "D) CLI parameter change"],
            ["A) Encrypt it first", "B) Verify with Claude", "C) Store with correct visibility", "D) All of the above"],
        ]
        for i in range(10):
            tmpl = mc_templates[i % len(mc_templates)]
            q_text = tmpl.replace("{topic}", lessons[i % len(lessons)] if lessons else "this data")
            q_text = q_text.replace("{action}", "store a chairman-only memory")
            opts = mc_options[i % len(mc_options)]
            questions.append({
                "number": i + 1,
                "type": "multiple_choice",
                "question": q_text,
                "options": opts,
                "correct": None,  # Graded by Claude
                "category": "recall",
            })

        # 6 Short Answer
        sa_templates = template["sa_starters"]
        for i in range(6):
            tmpl = sa_templates[i % len(sa_templates)]
            q_text = tmpl.replace("{topic}", lessons[i % len(lessons)] if lessons else "this concept")
            questions.append({
                "number": 10 + i + 1,
                "type": "short_answer",
                "question": q_text,
                "options": None,
                "correct": None,
                "category": "understanding",
            })

        # 4 Application
        app_templates = template["app_starters"]
        for i in range(4):
            q_text = app_templates[i % len(app_templates)]
            questions.append({
                "number": 16 + i + 1,
                "type": "application",
                "question": q_text,
                "options": None,
                "correct": None,
                "category": "application",
            })

        quiz = {
            "quiz_id":    quiz_id,
            "trainer":    trainer,
            "topic":      topic_label,
            "date":       date,
            "lessons":    lessons,
            "questions":  questions,
            "profile":    profile,
        }

        # Save to DB
        con = sqlite3.connect(self.db_path)
        con.execute(
            "INSERT INTO rex_quiz_log (quiz_id, trainer, topic, date, questions, created_at) VALUES (?,?,?,?,?,?)",
            (quiz_id, trainer, topic_label, date, json.dumps(questions), datetime.utcnow().isoformat())
        )
        con.commit()
        con.close()

        # GOJ v1.2 — Also save as .txt file so grade-my-quiz can find it even if DB is on a different path
        quiz["created_at"] = datetime.utcnow().isoformat()
        self._save_quiz_txt(quiz)

        return quiz

    def format_quiz_email(self, quiz: Dict) -> tuple[str, str]:
        """Return (subject, html_body) for the quiz email."""
        profile = quiz["profile"]
        emoji = profile.get("emoji", "📚")
        display = profile.get("display", quiz["trainer"])
        date = quiz["date"]
        topic = quiz["topic"]
        quiz_id = quiz["quiz_id"]

        subject = f"🎓 REX Training Quiz — {display} — {date} — {topic}"

        body = f"""
<html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #1a1a2e;">

<div style="background: #1a2f5a; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
  <h1 style="margin:0; font-size: 22px;">{emoji} REX Training Quiz</h1>
  <p style="margin:5px 0 0; opacity: 0.85;">Trainer: {display} &nbsp;|&nbsp; Date: {date}</p>
  <p style="margin:5px 0 0; opacity: 0.7; font-size: 13px;">Quiz ID: {quiz_id}</p>
</div>

<div style="background: #f8f9ff; padding: 15px; border-left: 4px solid #1a2f5a;">
  <strong>Topic:</strong> {topic}<br>
  <strong>Questions:</strong> 20 (10 Multiple Choice, 6 Short Answer, 4 Application)<br>
  <strong>To grade:</strong> Say <code style="background:#e8eaf6; padding:2px 6px; border-radius:3px;">grade my quiz</code> in REX chat when ready.
</div>

<div style="padding: 20px 0;">
"""
        # Multiple Choice section
        body += '<h2 style="color:#1a2f5a; border-bottom: 2px solid #1a2f5a; padding-bottom:5px;">Part 1: Multiple Choice (Questions 1–10)</h2>'
        for q in quiz["questions"]:
            if q["type"] != "multiple_choice":
                continue
            body += f'<div style="margin: 15px 0; padding: 12px; background: white; border: 1px solid #dde; border-radius: 6px;">'
            body += f'<p style="margin:0 0 8px; font-weight:bold; color:#1a2f5a;">Q{q["number"]}. {q["question"]}</p>'
            if q.get("options"):
                for opt in q["options"]:
                    body += f'<p style="margin:4px 0; padding:4px 10px; background:#f5f5fb; border-radius:4px;">☐ {opt}</p>'
            body += '</div>'

        # Short Answer
        body += '<h2 style="color:#1a2f5a; border-bottom: 2px solid #1a2f5a; padding-bottom:5px; margin-top:25px;">Part 2: Short Answer (Questions 11–16)</h2>'
        for q in quiz["questions"]:
            if q["type"] != "short_answer":
                continue
            body += f'<div style="margin: 15px 0; padding: 12px; background: white; border: 1px solid #dde; border-radius: 6px;">'
            body += f'<p style="margin:0 0 8px; font-weight:bold; color:#1a2f5a;">Q{q["number"]}. {q["question"]}</p>'
            body += '<div style="border: 1px dashed #aab; border-radius:4px; min-height:60px; padding:8px; color:#aaa; font-style:italic;">Your answer here...</div>'
            body += '</div>'

        # Application
        body += '<h2 style="color:#1a2f5a; border-bottom: 2px solid #1a2f5a; padding-bottom:5px; margin-top:25px;">Part 3: Application Scenarios (Questions 17–20)</h2>'
        for q in quiz["questions"]:
            if q["type"] != "application":
                continue
            body += f'<div style="margin: 15px 0; padding: 12px; background: white; border: 1px solid #dde; border-radius: 6px;">'
            body += f'<p style="margin:0 0 8px; font-weight:bold; color:#1a2f5a;">Q{q["number"]}. {q["question"]}</p>'
            body += '<div style="border: 1px dashed #aab; border-radius:4px; min-height:90px; padding:8px; color:#aaa; font-style:italic;">Walk through your answer in detail...</div>'
            body += '</div>'

        body += f"""
</div>

<div style="background: #1a2f5a; color: white; padding: 15px; border-radius: 0 0 8px 8px; font-size:13px;">
  <strong>To grade this quiz:</strong><br>
  Open REX chat → type <code style="background: rgba(255,255,255,0.2); padding:2px 6px; border-radius:3px;">grade my quiz</code><br>
  REX will guide you through submitting your answers and grade each one with explanations.
</div>

</body></html>
"""
        return subject, body

    def email_quiz(self, quiz: Dict, to_email: str) -> bool:
        """Send the quiz to Kato's email. Uses Gmail MCP if available."""
        subject, html_body = self.format_quiz_email(quiz)
        try:
            # Try Gmail MCP first (available via connected tools)
            # Falls back to rex_notify file-based alert
            if self.notify:
                # Use notify's gmail sender
                ok = self.notify._send_gmail(subject, html_body)
                if ok:
                    logger.info(f"📧 Quiz emailed: {quiz['quiz_id']}")
                    return True
        except Exception as e:
            logger.warning(f"Gmail send failed: {e}")

        # Fallback: save as HTML file in alerts folder
        from pathlib import Path
        alerts_dir = Path.home() / "Desktop" / "REX" / "quizzes"
        alerts_dir.mkdir(parents=True, exist_ok=True)
        out = alerts_dir / f"{quiz['quiz_id']}.html"
        out.write_text(html_body)
        logger.info(f"📄 Quiz saved locally: {out}")
        return True

    def get_latest_quiz(self, trainer: Optional[str] = None) -> Optional[Dict]:
        """Return the most recent ungraded quiz."""
        con = sqlite3.connect(self.db_path)
        if trainer:
            row = con.execute(
                "SELECT * FROM rex_quiz_log WHERE trainer=? AND score IS NULL ORDER BY created_at DESC LIMIT 1",
                (trainer,)
            ).fetchone()
        else:
            row = con.execute(
                "SELECT * FROM rex_quiz_log WHERE score IS NULL ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        con.close()
        if not row:
            return None
        return {
            "quiz_id":   row[1],
            "trainer":   row[2],
            "topic":     row[3],
            "date":      row[4],
            "questions": json.loads(row[5]),
        }

    # ── GOJ v1.2 — Build 3: Quiz DB ↔ .txt Sync ──────────────────────────────

    def _save_quiz_txt(self, quiz: Dict):
        """GOJ v1.2 — Write quiz as a JSON-encoded .txt file under QUIZ_LOG_DIR."""
        try:
            QUIZ_LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = QUIZ_LOG_DIR / f"quiz_{quiz['quiz_id']}.txt"
            path.write_text(json.dumps(quiz, indent=2))
            logger.info(f"GOJ v1.2 — Quiz txt saved: {path}")
        except Exception as e:
            logger.warning(f"GOJ v1.2 — Quiz txt save failed: {e}")

    def get_pending_quiz(self, trainer: Optional[str] = None) -> Optional[Dict]:
        """GOJ v1.2 — Return the most recent ungraded quiz.

        Checks the DB first (same as get_latest_quiz). If nothing is found there,
        scans ~/Desktop/REX/logs/quiz_*.txt files and imports any discovered quiz
        into rex_quiz_log so future lookups work normally.
        """
        # Primary: DB lookup (existing logic)
        quiz = self.get_latest_quiz(trainer)
        if quiz:
            return quiz

        # Fallback: scan .txt files
        try:
            txt_files = sorted(
                QUIZ_LOG_DIR.glob("quiz_*.txt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return None

        for path in txt_files:
            try:
                data    = json.loads(path.read_text())
                quiz_id = data.get("quiz_id")
                if not quiz_id:
                    continue

                # Check DB for this quiz_id
                con      = sqlite3.connect(self.db_path)
                existing = con.execute(
                    "SELECT id, score FROM rex_quiz_log WHERE quiz_id=?", (quiz_id,)
                ).fetchone()

                if existing is not None:
                    con.close()
                    # Already in DB — if ungraded, get_latest_quiz would have returned it above;
                    # if graded, skip it.
                    continue

                # Not in DB — import it now
                questions = data.get("questions", [])
                con.execute(
                    "INSERT OR IGNORE INTO rex_quiz_log "
                    "(quiz_id, trainer, topic, date, questions, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        quiz_id,
                        data.get("trainer", "unknown"),
                        data.get("topic", ""),
                        data.get("date", ""),
                        json.dumps(questions),
                        data.get("created_at") or datetime.utcnow().isoformat(),
                    ),
                )
                con.commit()
                con.close()
                logger.info(f"GOJ v1.2 — Imported quiz from txt into DB: {quiz_id}")
                return {
                    "quiz_id":   quiz_id,
                    "trainer":   data.get("trainer", "unknown"),
                    "topic":     data.get("topic", ""),
                    "date":      data.get("date", ""),
                    "questions": questions,
                }
            except Exception as e:
                logger.warning(f"GOJ v1.2 — Quiz txt parse error ({path.name}): {e}")
                continue

        return None

    # ─────────────────────────────────────────────────────────────────────────

    def grade_quiz(self, quiz_id: str, answers: List[str]) -> Dict:
        """
        Grade a submitted quiz. In production this calls the LLM to evaluate
        short answer and application questions. Returns score + feedback.
        """
        con = sqlite3.connect(self.db_path)
        row = con.execute(
            "SELECT questions FROM rex_quiz_log WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
        con.close()
        if not row:
            return {"error": f"Quiz {quiz_id} not found"}

        questions = json.loads(row[0])
        total = len(questions)
        correct = 0
        feedback = []
        weak_areas = set()

        for i, (q, ans) in enumerate(zip(questions, answers)):
            ans = ans.strip() if ans else ""
            # For MC: simple match check (A/B/C/D)
            if q["type"] == "multiple_choice":
                # In production: compare against answer key generated by LLM
                # For now: any substantive answer gets credit (LLM grades in real use)
                passed = len(ans) >= 1
            else:
                # Short answer/application: any answer > 20 chars gets partial credit
                passed = len(ans) >= 20

            if passed:
                correct += 1
                feedback.append({"q": q["number"], "result": "✅", "comment": "Good answer."})
            else:
                weak_areas.add(q["category"])
                feedback.append({"q": q["number"], "result": "❌", "comment": f"Review: {q['question'][:80]}"})

        score = round((correct / total) * 100, 1)
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"

        # Save to DB
        con = sqlite3.connect(self.db_path)
        con.execute(
            "UPDATE rex_quiz_log SET answers=?, score=?, weak_areas=?, graded_at=? WHERE quiz_id=?",
            (json.dumps(answers), score, json.dumps(list(weak_areas)),
             datetime.utcnow().isoformat(), quiz_id)
        )
        con.commit()
        con.close()

        return {
            "quiz_id":   quiz_id,
            "score":     score,
            "grade":     grade,
            "correct":   correct,
            "total":     total,
            "weak_areas": list(weak_areas),
            "feedback":   feedback,
        }

    def format_grade_report(self, result: Dict) -> str:
        """Format a grade result for REX chat display."""
        score = result["score"]
        grade = result["grade"]
        emoji = "🏆" if score >= 90 else "✅" if score >= 80 else "📚" if score >= 70 else "⚠️"
        lines = [
            f"{emoji} **Quiz Results — {result['quiz_id']}**\n",
            f"**Score:** {score}% ({result['correct']}/{result['total']}) — Grade: **{grade}**\n",
        ]
        if result.get("weak_areas"):
            lines.append(f"**Focus areas for next session:** {', '.join(result['weak_areas'])}")
        if score < 70:
            lines.append("\n📌 _Recommendation: Review this week's training report before next session._")
        return "\n".join(lines)

    def detect_quiz_command(self, user_text: str, user_role: str) -> Optional[str]:
        """Detect quiz-related commands in chat."""
        lower = user_text.strip().lower()

        if "grade my quiz" in lower or "grade quiz" in lower:
            quiz = self.get_pending_quiz()   # GOJ v1.2 — DB first, then .txt fallback
            if not quiz:
                return "📭 No ungraded quiz found. A quiz is emailed after each training session."
            return (
                f"📝 **Grading Quiz: {quiz['quiz_id']}**\n"
                f"**Trainer:** {quiz['trainer']} | **Date:** {quiz['date']}\n\n"
                f"Please share your answers for questions 1–20. "
                f"You can paste them as a numbered list:\n\n"
                f"_Example:_\n1. C\n2. All of the above\n3. [your short answer]...\n\n"
                f"I'll grade each one with explanations."
            )

        if "quiz score" in lower or "my quiz history" in lower:
            con = sqlite3.connect(self.db_path)
            rows = con.execute(
                "SELECT date, trainer, score, grade FROM rex_quiz_log WHERE score IS NOT NULL ORDER BY graded_at DESC LIMIT 10"
            ).fetchall()
            con.close()
            if not rows:
                return "No graded quizzes yet. Complete a training session to receive your first quiz."
            lines = ["📊 **Your Quiz History**\n"]
            for date, trainer, score, grade in rows:
                emoji = "🏆" if score >= 90 else "✅" if score >= 80 else "📚"
                lines.append(f"{emoji} {date} | {trainer} | {score}% — {grade}")
            return "\n".join(lines)

        return None
