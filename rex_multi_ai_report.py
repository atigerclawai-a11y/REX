#!/usr/bin/env python3
"""
REX — Multi-AI Training Report Parser
========================================
After your training sessions with Grok or ChatGPT, you paste or upload
a summary of what they taught. This script parses it, extracts lessons,
and stores them properly tagged in the REX training log.

Format for your summary files (plain text or .txt):

  AI: grok
  Date: 2026-03-29

  LESSON: How to generate animated GIF banners from text prompts
  SKILL: animation
  Detail: Use the following workflow — [details here]

  LESSON: Image consistency across multiple generations
  SKILL: animation
  Detail: Lock seed values to maintain character consistency

  ---

  AI: chatgpt
  Date: 2026-03-29

  LESSON: Structured JSON output for route assignments
  SKILL: operations
  Detail: ...

Usage:
  python rex_multi_ai_report.py my_grok_session.txt
  python rex_multi_ai_report.py --text "AI: grok\nLESSON: ..."
  python rex_multi_ai_report.py --scan    (scans ~/Desktop/REX/training_reports/)

Or drop a file in ~/Desktop/REX/training_reports/ and the scheduler
will pick it up automatically every Monday before training.
"""

import sys
import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

REX_DIR = Path(__file__).parent
sys.path.insert(0, str(REX_DIR))
VENV_PY = REX_DIR / ".venv" / "bin" / "python"
if VENV_PY.exists():
    try:
        import cryptography
    except ImportError:
        os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)

REPORTS_DIR = REX_DIR / "training_reports"
PROCESSED_DIR = REPORTS_DIR / "processed"
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("rex-multi-ai")

# ── Known AI aliases ─────────────────────────────────────────────────────────
AI_ALIASES = {
    "grok":       "grok",
    "xai":        "grok",
    "chatgpt":    "chatgpt",
    "gpt":        "chatgpt",
    "gpt-4":      "chatgpt",
    "openai":     "chatgpt",
    "gemini":     "gemini",
    "google":     "gemini",
    "bard":       "gemini",
    "claude":     "claude",
    "anthropic":  "claude",
    "perplexity": "perplexity",
    "mistral":    "mistral",
    "llama":      "llama",
    "ollama":     "llama",
    "human":      "human",
    "kato":       "human",
    "chairman":   "human",
}

SKILL_KEYWORDS = {
    "animation":     ["animat", "gif", "video", "motion", "visual", "image gen", "dall-e", "midjourney"],
    "operations":    ["schedule", "route", "driver", "client", "billing", "auth", "authorization", "medicaid"],
    "analysis":      ["analy", "pattern", "report", "data", "trend", "insight", "metric"],
    "communication": ["letter", "memo", "draft", "write", "voice", "email", "message", "tone"],
    "security":      ["encrypt", "hipaa", "phi", "secure", "privacy", "vault", "tamper"],
    "reasoning":     ["reason", "logic", "think", "step", "break down", "framework", "approach"],
    "coding":        ["code", "python", "sql", "api", "script", "function", "class", "module"],
}


# ── Report parser ─────────────────────────────────────────────────────────────

class MultiAIReportParser:

    def parse_text(self, text: str) -> List[Dict]:
        """
        Parse a training report text into structured lesson records.
        Handles both structured format (AI: / LESSON: / SKILL:) and
        free-form text (tries to extract lessons intelligently).
        """
        lessons = []
        current_ai = None
        current_date = datetime.utcnow().strftime("%Y-%m-%d")

        # Try structured parsing first
        lines = text.strip().splitlines()
        current_lesson = None
        current_skill = "general"
        current_detail_lines = []

        def flush_lesson():
            nonlocal current_lesson, current_skill, current_detail_lines
            if current_lesson and current_ai:
                lessons.append({
                    "ai":      current_ai,
                    "date":    current_date,
                    "lesson":  current_lesson.strip(),
                    "skill":   current_skill,
                    "detail":  " ".join(current_detail_lines).strip(),
                })
            current_lesson = None
            current_skill = "general"
            current_detail_lines = []

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            # AI marker
            if lower.startswith("ai:") or lower.startswith("trainer:"):
                flush_lesson()
                ai_raw = re.sub(r"^(ai|trainer):\s*", "", stripped, flags=re.IGNORECASE).strip()
                current_ai = AI_ALIASES.get(ai_raw.lower(), ai_raw.lower())
                continue

            # Date marker
            if lower.startswith("date:"):
                current_date = stripped[5:].strip()
                continue

            # Section separator
            if stripped in ("---", "===", "***"):
                flush_lesson()
                continue

            # Lesson marker
            if lower.startswith("lesson:"):
                flush_lesson()
                current_lesson = stripped[7:].strip()
                continue

            # Skill marker
            if lower.startswith("skill:") or lower.startswith("category:"):
                val = re.sub(r"^(skill|category):\s*", "", stripped, flags=re.IGNORECASE).strip().lower()
                current_skill = val if val in SKILL_KEYWORDS else self._infer_skill(val)
                continue

            # Detail lines
            if lower.startswith("detail:") or lower.startswith("notes:"):
                current_detail_lines = [re.sub(r"^(detail|notes):\s*", "", stripped, flags=re.IGNORECASE).strip()]
                continue

            # Continuation of detail
            if current_lesson and stripped and not lower.startswith(("lesson:", "ai:", "skill:", "---")):
                current_detail_lines.append(stripped)

        flush_lesson()

        # If structured parse yielded nothing, try free-form extraction
        if not lessons and current_ai:
            lessons = self._free_form_extract(text, current_ai, current_date)

        return lessons

    def _infer_skill(self, text: str) -> str:
        """Infer skill category from text content."""
        lower = text.lower()
        for cat, keywords in SKILL_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return cat
        return "general"

    def _free_form_extract(self, text: str, ai: str, date: str) -> List[Dict]:
        """Extract lessons from free-form text (bullets, numbered lists, etc.)."""
        lessons = []
        # Match bullet points, numbered items, or sentences starting with action verbs
        patterns = [
            r"^[-•*]\s+(.+)$",              # bullet points
            r"^\d+\.\s+(.+)$",              # numbered list
            r"^(?:Learned?|Taught?|Key|Important|Note):\s*(.+)$",  # labeled
        ]
        for line in text.splitlines():
            stripped = line.strip()
            for pat in patterns:
                m = re.match(pat, stripped, re.IGNORECASE)
                if m:
                    lesson_text = m.group(1).strip()
                    if len(lesson_text) > 15:  # ignore very short matches
                        lessons.append({
                            "ai":     ai,
                            "date":   date,
                            "lesson": lesson_text,
                            "skill":  self._infer_skill(lesson_text),
                            "detail": "",
                        })
                    break
        return lessons

    def parse_file(self, filepath: Path) -> List[Dict]:
        """Parse a report from a file."""
        text = filepath.read_text(encoding="utf-8", errors="replace")
        logger.info(f"Parsing: {filepath.name} ({len(text)} chars)")
        return self.parse_text(text)

    def store_lessons(self, lessons: List[Dict]) -> int:
        """Store all parsed lessons in REX's training log. Returns count stored."""
        if not lessons:
            return 0
        from backend.rex_training import RexTraining
        from backend.storage import EncryptedStorage
        storage = EncryptedStorage()
        trainer = RexTraining(db_path=str(storage.db_path))
        count = 0
        for lesson in lessons:
            ai = lesson["ai"]
            # Activate the right trainer (silently)
            trainer._trainer = ai
            trainer._session_id = f"import-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            trainer._session_lessons = []
            trainer.log_lesson(
                lesson=lesson["lesson"],
                detail=lesson.get("detail", ""),
                skill_cat=lesson.get("skill", "general"),
                trainer_override=ai,
            )
            count += 1
            logger.info(f"  ✅ Stored [{ai}/{lesson['skill']}]: {lesson['lesson'][:80]}")
        trainer._trainer = None
        trainer._session_id = None
        return count

    def scan_reports_dir(self) -> int:
        """Scan the training_reports folder and process any unprocessed .txt files."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        total = 0
        for txt_file in sorted(REPORTS_DIR.glob("*.txt")):
            lessons = self.parse_file(txt_file)
            if lessons:
                count = self.store_lessons(lessons)
                total += count
                # Move to processed
                dest = PROCESSED_DIR / txt_file.name
                txt_file.rename(dest)
                logger.info(f"  📥 Processed {txt_file.name}: {count} lessons stored → moved to processed/")
            else:
                logger.warning(f"  ⚠️ No lessons found in {txt_file.name}")
        return total

    def generate_summary_report(self, lessons: List[Dict]) -> str:
        """Human-readable summary of what was imported."""
        if not lessons:
            return "No lessons extracted."
        by_ai: Dict[str, List] = {}
        for l in lessons:
            by_ai.setdefault(l["ai"], []).append(l)
        lines = [f"**Multi-AI Training Import — {len(lessons)} lessons**\n"]
        for ai, ai_lessons in by_ai.items():
            from backend.rex_training import TRAINER_PROFILES
            profile = TRAINER_PROFILES.get(ai, {"emoji": "📚", "display": ai})
            lines.append(f"\n{profile['emoji']} **{profile.get('display', ai)}** — {len(ai_lessons)} lessons")
            for l in ai_lessons:
                lines.append(f"  • `[{l['skill']}]` {l['lesson'][:90]}")
        return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Multi-AI Training Report Parser")
    parser.add_argument("file",   nargs="?", help="Training report file to parse")
    parser.add_argument("--text", help="Parse inline text instead of a file")
    parser.add_argument("--scan", action="store_true", help="Scan training_reports/ folder")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't store")
    args = parser.parse_args()

    p = MultiAIReportParser()

    if args.scan:
        logger.info("Scanning training_reports/ folder...")
        total = p.scan_reports_dir()
        print(f"\n✅ {total} lessons imported from training reports folder")
        sys.exit(0)

    if args.text:
        lessons = p.parse_text(args.text)
    elif args.file:
        lessons = p.parse_file(Path(args.file))
    else:
        print("Usage: python rex_multi_ai_report.py <file.txt>")
        print("       python rex_multi_ai_report.py --scan")
        print("\nDrop training report files in: ~/Desktop/REX/training_reports/")
        sys.exit(1)

    print(p.generate_summary_report(lessons))
    if not args.dry_run:
        count = p.store_lessons(lessons)
        print(f"\n✅ {count} lessons stored in REX training log")
    else:
        print(f"\n[DRY RUN — {len(lessons)} lessons parsed, not stored]")
