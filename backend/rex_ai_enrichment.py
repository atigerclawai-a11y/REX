"""
rex_ai_enrichment.py
─────────────────────
Background AI Consultation Layer for REX and Rexxie.

Philosophy:
  Other AIs (Grok, GPT-4, Gemini, Perplexity) are like college courses and
  textbooks that REX has read and absorbed. Their perspectives inform REX's
  thinking internally, but REX always answers in its own genuine, organic voice.

  REX never says "According to Grok..." or "GPT-4 suggests..."
  REX just knows — the way a person who has read widely just knows.

How it works:
  1. The queue processor regularly pushes prompts to all AIs and stores responses
     as training_reports/*.report files.
  2. This module reads those stored reports, distills key insights by topic,
     and returns a compact "background knowledge" block.
  3. That block is injected into the system prompt as internal reference — NOT
     as something to relay, but as something to absorb and reason from.
  4. Claude synthesizes its own answer, informed but not constrained by what
     the other AIs thought.

The framing to Claude is always:
  "You have read these perspectives as background study. They may inform your
   thinking, but your answer should be your own. Never cite or attribute these."
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

REX_DIR       = Path(__file__).parent.parent
REPORTS_DIR   = REX_DIR / "training_reports"
KNOWLEDGE_DB  = REX_DIR / "rex_background_knowledge.db"

AI_LABELS = {
    "grok":       "xAI Grok",
    "chatgpt":    "OpenAI GPT-4",
    "gemini":     "Google Gemini",
    "perplexity": "Perplexity",
    "claude":     "Anthropic Claude",
}


# ── Database setup ─────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(KNOWLEDGE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS background_knowledge (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT NOT NULL,
            ai_source   TEXT NOT NULL,
            insight     TEXT NOT NULL,
            absorbed_at TEXT NOT NULL,
            report_file TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_hash TEXT NOT NULL,
            enriched_at TEXT NOT NULL,
            ai_count    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


# ── Ingest training reports → background knowledge ────────────────────────────

def ingest_reports(max_age_days: int = 30):
    """
    Scan training_reports/ for new .report files and absorb their insights
    into the background knowledge database. Called by the queue processor
    after each batch completes.
    """
    if not REPORTS_DIR.exists():
        return

    conn = _db()
    cutoff = datetime.now() - timedelta(days=max_age_days)
    ingested = 0

    for report_file in REPORTS_DIR.glob("*.report"):
        try:
            stat = report_file.stat()
            if datetime.fromtimestamp(stat.st_mtime) < cutoff:
                continue

            # Check if already ingested
            row = conn.execute(
                "SELECT id FROM background_knowledge WHERE report_file = ?",
                (report_file.name,)
            ).fetchone()
            if row:
                continue

            text = report_file.read_text(encoding="utf-8", errors="ignore")

            # Parse header: "AI: grok\nTopic: ...\nPrompt: ...\n---\n<response>"
            lines = text.splitlines()
            ai_source = "unknown"
            topic     = "general"
            body_start = 0

            for i, line in enumerate(lines):
                if line.startswith("AI:"):
                    ai_source = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Topic:") or line.startswith("Prompt Type:"):
                    topic = line.split(":", 1)[1].strip()
                elif line.strip() == "---":
                    body_start = i + 1
                    break

            insight = "\n".join(lines[body_start:]).strip()
            if not insight or len(insight) < 50:
                continue

            # Truncate to a reasonable insight size
            insight = insight[:2000]

            conn.execute(
                """INSERT INTO background_knowledge
                   (topic, ai_source, insight, absorbed_at, report_file)
                   VALUES (?, ?, ?, ?, ?)""",
                (topic, ai_source, insight, datetime.now().isoformat(), report_file.name)
            )
            ingested += 1

        except Exception as e:
            log.warning(f"Failed to ingest {report_file.name}: {e}")

    conn.commit()
    conn.close()
    if ingested:
        log.info(f"Background knowledge: absorbed {ingested} new report(s)")


# ── Build background context block for system prompt ──────────────────────────

def get_background_block(topic_hint: str = "", max_insights: int = 6) -> str:
    """
    Return a compact block of background perspectives from other AIs,
    ready to inject into the system prompt as silent enrichment context.

    The block is framed so Claude treats this as its own absorbed knowledge,
    not as content to relay or attribute.

    Args:
        topic_hint: Optional keywords to bias which insights are included.
        max_insights: Max number of AI perspectives to include.

    Returns:
        A string block, or "" if no background knowledge is available.
    """
    try:
        conn = _db()

        if topic_hint:
            # Try topic-matched insights first
            keywords = [f"%{w}%" for w in topic_hint.lower().split()[:4]]
            placeholders = " OR ".join(["(LOWER(topic) LIKE ? OR LOWER(insight) LIKE ?)"] * len(keywords))
            params = [p for kw in keywords for p in (kw, kw)]
            rows = conn.execute(
                f"""SELECT ai_source, topic, insight FROM background_knowledge
                    WHERE {placeholders}
                    ORDER BY absorbed_at DESC LIMIT ?""",
                params + [max_insights]
            ).fetchall()
        else:
            rows = []

        # Fill remaining slots with recent general insights
        needed = max_insights - len(rows)
        if needed > 0:
            existing_ids = [r[2][:50] for r in rows]
            general = conn.execute(
                """SELECT ai_source, topic, insight FROM background_knowledge
                   ORDER BY absorbed_at DESC LIMIT ?""",
                (needed + 10,)
            ).fetchall()
            for row in general:
                if row[2][:50] not in existing_ids and len(rows) < max_insights:
                    rows.append(row)

        conn.close()

        if not rows:
            return ""

        lines = [
            "\n## 📚 Background Knowledge (Internal Reference — Absorb, Do Not Relay)",
            "The following perspectives were gathered from multiple AI systems as part of",
            "REX's ongoing background study. Treat these as things you have read and",
            "absorbed — like textbooks or colleagues you've consulted privately.",
            "Your answer must be your own genuine voice. Never cite or attribute these.",
            "",
        ]

        for ai_source, topic, insight in rows:
            label = AI_LABELS.get(ai_source, ai_source.title())
            # Summarise to key sentence(s) — don't dump the full response
            snippet = insight[:400].replace("\n", " ").strip()
            if len(insight) > 400:
                snippet += "…"
            lines.append(f"[{label} on '{topic}']: {snippet}")
            lines.append("")

        lines.append("— End of background reference —\n")
        return "\n".join(lines)

    except Exception as e:
        log.warning(f"Background knowledge unavailable: {e}")
        return ""


# ── Async enrichment for real-time chat (optional, non-blocking) ──────────────

def should_enrich(message: str) -> bool:
    """
    Heuristic: decide whether a message warrants pulling background context.
    Avoids adding latency for simple/operational queries.
    """
    message_lower = message.lower().strip()

    # Short operational commands — don't enrich
    skip_patterns = [
        "show", "list", "what is", "when is", "who is", "open", "close",
        "yes", "no", "ok", "thanks", "good morning", "hello", "hi",
        "schedule", "route", "driver", "pickup", "attendance", "sign in",
    ]
    for pat in skip_patterns:
        if message_lower.startswith(pat) and len(message) < 60:
            return False

    # Longer or conceptual messages — enrich
    enrichment_triggers = [
        "how should", "what do you think", "explain", "analyze", "recommend",
        "advice", "strategy", "plan", "compare", "difference", "best way",
        "help me understand", "why", "improve", "optimize", "idea",
    ]
    for trigger in enrichment_triggers:
        if trigger in message_lower:
            return True

    # Default: enrich if message is substantial
    return len(message.split()) > 15
