"""
REX — AI Training Mode
========================
When TRAINING MODE is active, REX enters a special receptive state that:

  • Logs every lesson taught (who taught it, from which AI, what was learned)
  • Persists lessons as high-priority memories tagged with the trainer AI
  • Keeps a training transcript per session
  • Lets the Chairman review all training sessions (what each AI taught)
  • Claude is always the HEAD INSTRUCTOR — Claude's lessons override any other AI

Supported trainer AIs (each gets its own training log and skill tag):
  - claude      → Anthropic Claude (head instructor, highest authority)
  - grok        → xAI Grok
  - gemini      → Google Gemini
  - chatgpt     → OpenAI ChatGPT / GPT-4
  - perplexity  → Perplexity
  - mistral     → Mistral
  - llama       → Meta Llama (local via Ollama)
  - human       → Direct Chairman teaching

Skill categories REX can be trained in:
  - animation     → Grok teaches animated image generation
  - operations    → GOJ workflow, scheduling, billing
  - analysis      → Data analysis, pattern recognition
  - communication → Letter writing, reporting, GOJ voice
  - security      → HIPAA, encryption, compliance
  - reasoning     → Logic, step-by-step problem solving
  - coding        → Python, SQL, API development

Usage in REX chat:
  "training mode on: grok"          → activate training with Grok as trainer
  "training mode on: claude"        → activate training with Claude as trainer
  "training mode off"               → end training session
  "training status"                 → see current mode + active trainer
  "show training log"               → review all lessons learned
  "learned: [description of skill]" → manually log a learned skill
"""

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ── Known AI Trainers ─────────────────────────────────────────────────────────

TRAINER_PROFILES = {
    "claude": {
        "display":    "Claude (Anthropic) — Head Instructor",
        "authority":  "HEAD",
        "emoji":      "🧠",
        "specialty":  "Reasoning, GOJ operations, security, mentorship",
        "note":       "Claude's lessons are canon. All other AI lessons are cross-referenced against Claude's principles.",
    },
    "grok": {
        "display":    "Grok (xAI)",
        "authority":  "PEER",
        "emoji":      "⚡",
        "specialty":  "Animation, creative generation, real-time knowledge",
    },
    "gemini": {
        "display":    "Gemini (Google)",
        "authority":  "PEER",
        "emoji":      "♊",
        "specialty":  "Multimodal analysis, document understanding, search",
    },
    "chatgpt": {
        "display":    "ChatGPT / GPT-4 (OpenAI)",
        "authority":  "PEER",
        "emoji":      "💬",
        "specialty":  "Code generation, structured output, plugins",
    },
    "perplexity": {
        "display":    "Perplexity",
        "authority":  "PEER",
        "emoji":      "🔍",
        "specialty":  "Research synthesis, citation, live web knowledge",
    },
    "mistral": {
        "display":    "Mistral",
        "authority":  "PEER",
        "emoji":      "🌀",
        "specialty":  "Efficient reasoning, European AI, multilingual",
    },
    "llama": {
        "display":    "Llama (Meta / Ollama local)",
        "authority":  "LOCAL",
        "emoji":      "🦙",
        "specialty":  "Fully local, private, sovereign AI baseline",
    },
    "human": {
        "display":    "Direct Chairman Teaching",
        "authority":  "CHAIRMAN",
        "emoji":      "👑",
        "specialty":  "GOJ operations, business rules, personal preferences",
    },
}

SKILL_CATEGORIES = {
    "animation", "operations", "analysis", "communication",
    "security", "reasoning", "coding", "general",
}


class RexTraining:
    """
    Manages REX's AI Training Mode.

    Training sessions are stored in the rex_memory.db in a dedicated
    `rex_training_log` table. Each lesson is persisted and tagged
    with the trainer AI so the Chairman can audit exactly what each
    AI taught REX.
    """

    # ── Chat commands ─────────────────────────────────────────────────────

    CMD_TRAIN_ON    = "training mode on"
    CMD_TRAIN_OFF   = ("training mode off", "end training", "stop training")
    CMD_STATUS      = ("training status", "training mode status")
    CMD_SHOW_LOG    = ("show training log", "training log", "what have i learned")
    CMD_LEARNED     = "learned:"
    CMD_LESSON      = "lesson:"  # trainer injects a lesson directly
    CMD_MAKEUP      = ("makeup class", "take class", "run class", "missed class",
                       "catch up class", "do class", "start class", "run today's class",
                       "take today's class", "run training", "take training")

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._active: bool = False
        self._trainer: Optional[str] = None        # e.g. "grok"
        self._session_id: Optional[str] = None
        self._session_start: Optional[str] = None
        self._session_lessons: List[Dict] = []
        self._init_db()

    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS rex_training_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                trainer     TEXT NOT NULL,
                authority   TEXT NOT NULL,
                skill_cat   TEXT DEFAULT 'general',
                lesson      TEXT NOT NULL,
                detail      TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        con.commit()
        con.close()

    # ── Mode management ───────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        return self._active

    @property
    def trainer(self) -> Optional[str]:
        return self._trainer

    def activate(self, trainer_key: str) -> str:
        """Start a training session with the specified AI trainer."""
        trainer_key = trainer_key.strip().lower()
        # Normalize aliases
        alias_map = {"gpt": "chatgpt", "openai": "chatgpt", "google": "gemini",
                     "anthropic": "claude", "xai": "grok", "meta": "llama",
                     "ollama": "llama", "chairman": "human", "kato": "human"}
        trainer_key = alias_map.get(trainer_key, trainer_key)
        profile = TRAINER_PROFILES.get(trainer_key)
        if not profile:
            trainers = ", ".join(TRAINER_PROFILES.keys())
            return (
                f"❓ Unknown trainer: `{trainer_key}`\n\n"
                f"Available trainers: {trainers}\n\n"
                f"Example: `training mode on: grok`"
            )
        import uuid
        self._active = True
        self._trainer = trainer_key
        self._session_id = str(uuid.uuid4())[:8]
        self._session_start = datetime.utcnow().isoformat()
        self._session_lessons = []
        emoji = profile["emoji"]
        display = profile["display"]
        authority = profile["authority"]
        specialty = profile["specialty"]
        authority_note = ""
        if authority == "HEAD":
            authority_note = "\n\n⚠️ **Claude is HEAD INSTRUCTOR** — lessons taught now are treated as canonical REX behavior."
        elif authority == "CHAIRMAN":
            authority_note = "\n\n👑 **Chairman is teaching directly** — highest authority. All lessons stored as permanent memory."
        return (
            f"🎓 **TRAINING MODE ACTIVATED**\n\n"
            f"{emoji} **Trainer:** {display}\n"
            f"📚 **Specialty:** {specialty}\n"
            f"🔑 **Authority level:** {authority}\n"
            f"🆔 **Session:** #{self._session_id}{authority_note}\n\n"
            f"REX is now in receptive learning mode.\n"
            f"Everything taught this session will be logged and stored.\n\n"
            f"Use `learned: [skill description]` to explicitly log a lesson.\n"
            f"Type `training mode off` when done."
        )

    def deactivate(self) -> str:
        """End the training session and summarize what was learned."""
        if not self._active:
            return "Training mode is not currently active."
        count = len(self._session_lessons)
        trainer_display = TRAINER_PROFILES.get(self._trainer or "", {}).get("display", self._trainer or "unknown")
        self._active = False
        trainer = self._trainer
        self._trainer = None
        session_id = self._session_id
        self._session_id = None
        summary_lines = [f"🎓 **Training Session #{session_id} Complete**\n"]
        summary_lines.append(f"**Trainer:** {trainer_display}")
        summary_lines.append(f"**Lessons logged:** {count}")
        if self._session_lessons:
            summary_lines.append("\n**What REX learned this session:**")
            for i, lesson in enumerate(self._session_lessons, 1):
                summary_lines.append(f"{i}. {lesson['lesson'][:100]}")
        summary_lines.append(
            "\n_All lessons are stored in REX's training log. "
            "Type `show training log` to review all sessions._"
        )
        self._session_lessons = []
        return "\n".join(summary_lines)

    def log_lesson(
        self,
        lesson: str,
        detail: str = "",
        skill_cat: str = "general",
        trainer_override: Optional[str] = None,
        data_class: Optional[str] = None,
    ) -> str:
        """
        Log a lesson — Phase 12 gate: all lessons route through RexTrainingClassifier.
        Content classified as private_personal or restricted_sensitive is BLOCKED.
        Sanitization fails closed. Only operational content becomes a training candidate.
        The candidate is submitted for Chairman approval — not auto-committed.
        """
        trainer = trainer_override or self._trainer or "human"
        profile = TRAINER_PROFILES.get(trainer, {"authority": "PEER", "emoji": "📚"})
        emoji   = profile.get("emoji", "📚")

        # Phase 12: Route through classifier before any write to DB
        try:
            from .rex_training_classifier import RexTrainingClassifier
            clf    = RexTrainingClassifier()
            result = clf.submit_candidate(
                text        = f"{lesson}\n{detail}".strip(),
                source      = f"rex_training/{trainer}",
                trainer     = trainer,
                skill_cat   = skill_cat,
                force_class = data_class,
            )
            if not result.get("ok"):
                logger.warning("Training BLOCKED: %s | %s", lesson[:60], result.get("reason",""))
                return (
                    f"⛔ **Training blocked:** {result.get('message','Content not eligible.')}\n"
                    f"_Only `public_operational` or `internal_operational` content may train Rex._"
                )
            cid = result.get("candidate_id", "?")
            self._session_lessons.append({
                "lesson": lesson, "detail": detail, "skill_cat": skill_cat,
                "trainer": trainer, "data_class": result.get("data_class"),
                "candidate_id": cid, "ts": datetime.utcnow().isoformat(),
            })
            return (
                f"✅ **Training candidate submitted:** {lesson[:100]}\n"
                f"_{emoji} Class: `{result.get('data_class')}` | Candidate: `{cid}` | "
                f"Pending Chairman approval. Approve: `approve training {cid}`_"
            )
        except ImportError:
            logger.error("RexTrainingClassifier unavailable — lesson BLOCKED (fail-safe)")
            return "⛔ Training classifier unavailable. Lesson not logged."

    def get_training_log(self, trainer_filter: Optional[str] = None, limit: int = 50) -> str:
        """Return a formatted summary of all training log entries."""
        con = sqlite3.connect(self.db_path)
        if trainer_filter:
            rows = con.execute(
                "SELECT trainer, skill_cat, lesson, created_at FROM rex_training_log "
                "WHERE trainer=? ORDER BY created_at DESC LIMIT ?",
                (trainer_filter, limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT trainer, skill_cat, lesson, created_at FROM rex_training_log "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        con.close()
        if not rows:
            return (
                "📚 **REX Training Log — Empty**\n\n"
                "No lessons have been logged yet.\n"
                "Activate training with `training mode on: [ai-name]`"
            )
        lines = [f"📚 **REX Training Log — {len(rows)} lessons**\n"]
        current_trainer = None
        for trainer, skill_cat, lesson, ts in rows:
            profile = TRAINER_PROFILES.get(trainer, {"emoji": "📚", "display": trainer})
            if trainer != current_trainer:
                current_trainer = trainer
                lines.append(f"\n**{profile['emoji']} {profile.get('display', trainer)}**")
            date_str = ts[:10] if ts else "?"
            lines.append(f"  • `[{skill_cat}]` {lesson[:120]} _(_{date_str}_)_")
        return "\n".join(lines)

    def get_context_block(self) -> str:
        """Return a context string to inject into sovereign prompt during training."""
        if not self._active or not self._trainer:
            return ""
        profile = TRAINER_PROFILES.get(self._trainer, {})
        emoji = profile.get("emoji", "📚")
        display = profile.get("display", self._trainer)
        authority = profile.get("authority", "PEER")
        lessons_this_session = len(self._session_lessons)
        return (
            f"\n## 🎓 TRAINING MODE ACTIVE\n"
            f"**Current trainer:** {emoji} {display} (authority: {authority})\n"
            f"**Session lessons so far:** {lessons_this_session}\n"
            f"Be actively receptive. Acknowledge each lesson. "
            f"Ask clarifying questions if needed. Tag learned behaviors clearly.\n"
        )

    # ── Command detector ──────────────────────────────────────────────────

    def detect_training_command(self, user_text: str, user_role: str) -> Optional[str]:
        """
        Detect training commands in chat. Returns reply or None.
        Only Chairman can activate/deactivate training mode.
        """
        lower = user_text.strip().lower()

        # STATUS — anyone can check
        for cmd in self.CMD_STATUS:
            if cmd in lower:
                if self._active:
                    profile = TRAINER_PROFILES.get(self._trainer or "", {})
                    return (
                        f"🎓 **Training Mode: ACTIVE**\n\n"
                        f"**Trainer:** {profile.get('emoji','📚')} {profile.get('display', self._trainer)}\n"
                        f"**Lessons this session:** {len(self._session_lessons)}\n"
                        f"**Session ID:** #{self._session_id}\n\n"
                        f"Type `training mode off` to end the session."
                    )
                return "🎓 **Training Mode: OFF**\n\nType `training mode on: [ai-name]` to begin."

        # SHOW LOG — Chairman only
        for cmd in self.CMD_SHOW_LOG:
            if cmd in lower:
                if user_role != "chairman":
                    return "🔒 Training logs are Chairman-only."
                return self.get_training_log()

        # ACTIVATE
        if lower.startswith(self.CMD_TRAIN_ON):
            if user_role != "chairman":
                return "🔒 Only the Chairman can activate Training Mode."
            # Parse trainer: "training mode on: grok" or "training mode on grok"
            rest = user_text[len(self.CMD_TRAIN_ON):].strip().lstrip(":").strip()
            if not rest:
                trainers = ", ".join(TRAINER_PROFILES.keys())
                return (
                    f"Which AI trainer? Available: {trainers}\n\n"
                    f"Example: `training mode on: grok`"
                )
            return self.activate(rest)

        # DEACTIVATE
        for cmd in self.CMD_TRAIN_OFF:
            if lower.startswith(cmd) or lower == cmd:
                if user_role != "chairman":
                    return "🔒 Only the Chairman can control Training Mode."
                return self.deactivate()

        # LOG A LESSON (while training is active)
        if lower.startswith(self.CMD_LEARNED) and self._active:
            lesson_text = user_text[len(self.CMD_LEARNED):].strip()
            if not lesson_text:
                return "What was learned? Add a description after `learned:`"
            # Auto-detect skill category from content
            skill_cat = "general"
            cat_keywords = {
                "animation": ["animat", "gif", "video", "motion", "visual"],
                "operations": ["schedule", "route", "driver", "client", "billing", "auth"],
                "analysis": ["analy", "pattern", "report", "data", "trend"],
                "communication": ["letter", "memo", "draft", "write", "voice"],
                "security": ["encrypt", "hipaa", "phi", "secure", "privacy"],
                "reasoning": ["reason", "logic", "think", "step", "break down"],
                "coding": ["code", "python", "sql", "api", "script", "function"],
            }
            for cat, keywords in cat_keywords.items():
                if any(kw in lower for kw in keywords):
                    skill_cat = cat
                    break
            return self.log_lesson(lesson_text, skill_cat=skill_cat)

        # MAKEUP CLASS — run today's missed curriculum on demand
        for cmd in self.CMD_MAKEUP:
            if cmd in lower:
                if user_role != "chairman":
                    return "🔒 Only the Chairman can trigger makeup classes."
                return self.run_makeup_class()

        return None

    def run_makeup_class(self) -> str:
        """
        Trigger today's curriculum lesson on demand (makeup class).
        Runs the rex_daily_curriculum.py script in the background.
        """
        import subprocess
        import threading
        from pathlib import Path

        rex_dir = Path(__file__).parent.parent  # ~/Desktop/REX
        curriculum_script = rex_dir / "rex_daily_curriculum.py"

        if not curriculum_script.exists():
            return "❌ Can't find rex_daily_curriculum.py — training system not installed."

        # Determine today's trainer
        day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}
        trainers  = {0: ("Claude", "🧠"), 1: ("Grok", "⚡"), 2: ("ChatGPT", "💬"),
                     3: ("Gemini", "♊"), 4: ("Perplexity", "🔍")}
        today = datetime.now().weekday()

        if today > 4:
            return "📅 No classes on weekends! Saturday is review day, Sunday is rest day."

        trainer_name, emoji = trainers[today]
        day_name = day_names[today]

        def _run():
            try:
                subprocess.run(
                    ["python3", str(curriculum_script)],
                    cwd=str(rex_dir),
                    capture_output=True,
                    timeout=120,
                )
            except Exception as e:
                logger.error(f"Makeup class failed: {e}")

        # Run in background thread so chat doesn't block
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        return (
            f"🎓 **Makeup Class Started!**\n\n"
            f"📅 {day_name}'s class with {emoji} **{trainer_name}**\n"
            f"Running the curriculum now in the background...\n\n"
            f"I'll process the lesson and it'll show up in my training reports.\n"
            f"Check back in a minute or say `training status` to see progress."
        )
