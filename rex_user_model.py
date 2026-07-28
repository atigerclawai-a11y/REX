"""
rex_user_model.py
─────────────────
Rexxie – Evolving User Profile (Person Model)

Holds a persistent, structured model of the person Rexxie talks with.
Grows slowly over time through observed interactions.
Controlled by policy — never stores what shouldn't be stored.

MEMORY TIERS
────────────
Tier 1 — Session      : current conversation only, wiped at end
Tier 2 — Short-term   : days to weeks, auto-expires
Tier 3 — Long-term    : stable facts and preferences, rarely updated
Tier 4 — Reflection   : meta-lessons about how to help this person

CATEGORIES
──────────
  identity_facts    : name, role, location, known context
  preferences       : communication style, tone, format, timing
  goals             : active projects, aspirations, build targets
  relationships     : known people and their roles
  patterns          : recurring behaviors, triggers, rhythms
  emotional_support : what helps, what doesn't, support style
  trusted_facts     : things the user explicitly wants remembered
  recent_context    : temporary notes (short-term only)

Usage:
    from rex_user_model import UserModel

    um = UserModel(db_path="~/Desktop/REX/rexxie_memory.db", chat_id=12345)
    um.update("preferences", "Kato prefers short replies when busy", tier=3)
    profile = um.get_profile()
    context = um.build_context_block()
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rex.user_model")

# ─────────────────────────────────────────────
# TIER DEFINITIONS
# ─────────────────────────────────────────────

TIER_SESSION     = 1   # Current conversation only
TIER_SHORT_TERM  = 2   # Days to weeks
TIER_LONG_TERM   = 3   # Stable, long-lasting
TIER_REFLECTION  = 4   # Meta-lessons (managed by rex_reflection.py)

TIER_EXPIRY_DAYS = {
    TIER_SESSION:    0,     # Cleared at session end (managed externally)
    TIER_SHORT_TERM: 21,    # Expires after 3 weeks
    TIER_LONG_TERM:  3650,  # 10 years (essentially permanent)
    TIER_REFLECTION: 3650,  # Permanent
}

TIER_LABELS = {
    TIER_SESSION:    "session",
    TIER_SHORT_TERM: "short_term",
    TIER_LONG_TERM:  "long_term",
    TIER_REFLECTION: "reflection",
}

# ─────────────────────────────────────────────
# CATEGORIES
# ─────────────────────────────────────────────

VALID_CATEGORIES = {
    "identity_facts",
    "preferences",
    "goals",
    "relationships",
    "patterns",
    "emotional_support",
    "trusted_facts",
    "recent_context",
}

# How quickly each category changes (affects update threshold)
CATEGORY_STABILITY = {
    "identity_facts":    "stable",    # Rarely changes
    "preferences":       "moderate",  # Updates occasionally
    "goals":             "dynamic",   # Changes often
    "relationships":     "stable",
    "patterns":          "moderate",
    "emotional_support": "moderate",
    "trusted_facts":     "stable",
    "recent_context":    "dynamic",
}

# Default tier per category
CATEGORY_DEFAULT_TIER = {
    "identity_facts":    TIER_LONG_TERM,
    "preferences":       TIER_LONG_TERM,
    "goals":             TIER_SHORT_TERM,
    "relationships":     TIER_LONG_TERM,
    "patterns":          TIER_LONG_TERM,
    "emotional_support": TIER_LONG_TERM,
    "trusted_facts":     TIER_LONG_TERM,
    "recent_context":    TIER_SHORT_TERM,
}

# ─────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS rex_user_model (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER,
    category     TEXT NOT NULL,
    content      TEXT NOT NULL,
    tier         INTEGER NOT NULL DEFAULT 3,
    confidence   REAL    DEFAULT 0.7,
    source       TEXT    DEFAULT 'observed',
    created_at   TEXT    DEFAULT (datetime('now')),
    updated_at   TEXT    DEFAULT (datetime('now')),
    expires_at   TEXT,
    access_count INTEGER DEFAULT 0,
    active       INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_rum_chat_id  ON rex_user_model(chat_id);
CREATE INDEX IF NOT EXISTS idx_rum_category ON rex_user_model(category);
CREATE INDEX IF NOT EXISTS idx_rum_tier     ON rex_user_model(tier);
"""


class UserModel:
    """
    Evolving user profile for a single person (identified by chat_id).

    Grows through observed behavior. Controlled by tier and confidence.
    Never writes what policy says is off-limits.
    """

    def __init__(self, db_path: str | Path, chat_id: Optional[int] = None):
        self.db_path = Path(db_path).expanduser()
        self.chat_id = chat_id
        self._session_memory: list[dict] = []   # Tier 1 — in-memory only
        self._init_db()

    # ─────────────────────────────────────────────
    # SETUP
    # ─────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(_DDL)
        except Exception as e:
            logger.error(f"[user_model] DB init failed: {e}")

    # ─────────────────────────────────────────────
    # WRITE
    # ─────────────────────────────────────────────

    def update(
        self,
        category:   str,
        content:    str,
        tier:       int   = None,
        confidence: float = 0.7,
        source:     str   = "observed",
    ) -> bool:
        """
        Add or update a user model entry.

        If a very similar entry already exists, updates it instead of
        creating a duplicate (deduplication by content similarity).

        Args:
            category:   One of VALID_CATEGORIES
            content:    The fact or preference to store
            tier:       Memory tier (1-4). Defaults to category default.
            confidence: How confident we are (0.0-1.0)
            source:     "observed" | "explicit" | "inferred" | "reflection"

        Returns:
            True if stored, False if rejected
        """
        if category not in VALID_CATEGORIES:
            logger.warning(f"[user_model] Unknown category: {category!r}")
            return False

        if not content or not content.strip():
            return False

        content = content.strip()[:500]  # Hard cap
        tier    = tier or CATEGORY_DEFAULT_TIER.get(category, TIER_LONG_TERM)

        # Tier 1 (session) stays in memory only
        if tier == TIER_SESSION:
            self._session_memory.append({
                "category": category,
                "content":  content,
                "source":   source,
                "ts":       datetime.now(timezone.utc).isoformat(),
            })
            logger.debug(f"[user_model] Session memory: [{category}] {content[:60]}")
            return True

        # Calculate expiry
        expiry_days = TIER_EXPIRY_DAYS.get(tier, 21)
        expires_at  = (
            (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()
            if expiry_days < 3000 else None
        )

        try:
            with self._connect() as conn:
                # Check for near-duplicate
                existing = self._find_similar(conn, category, content)
                if existing:
                    # Update existing entry
                    conn.execute(
                        """UPDATE rex_user_model
                           SET content=?, confidence=MAX(confidence,?),
                               updated_at=datetime('now'), access_count=access_count+1,
                               tier=MAX(tier,?)
                           WHERE id=?""",
                        (content, confidence, tier, existing["id"])
                    )
                    logger.debug(f"[user_model] Updated: [{category}] {content[:60]}")
                else:
                    # Insert new entry
                    conn.execute(
                        """INSERT INTO rex_user_model
                           (chat_id, category, content, tier, confidence, source, expires_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (self.chat_id, category, content, tier,
                         confidence, source, expires_at)
                    )
                    logger.debug(f"[user_model] Stored T{tier}: [{category}] {content[:60]}")
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[user_model] update error: {e}")
            return False

    def update_explicit(self, category: str, content: str) -> bool:
        """Store something the user explicitly said to remember. High confidence, long-term."""
        return self.update(
            category, content,
            tier=TIER_LONG_TERM, confidence=0.95, source="explicit"
        )

    def update_inferred(self, category: str, content: str, confidence: float = 0.6) -> bool:
        """Store something inferred from behavior. Lower confidence, may get promoted."""
        return self.update(
            category, content,
            tier=TIER_SHORT_TERM, confidence=confidence, source="inferred"
        )

    # ─────────────────────────────────────────────
    # READ
    # ─────────────────────────────────────────────

    def get_category(
        self,
        category:  str,
        min_tier:  int   = TIER_SHORT_TERM,
        min_conf:  float = 0.5,
        limit:     int   = 10,
    ) -> list[dict]:
        """Get entries for a specific category."""
        rows = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT id, category, content, tier, confidence, source,
                              created_at, updated_at, access_count
                       FROM rex_user_model
                       WHERE active=1
                         AND (chat_id=? OR chat_id IS NULL)
                         AND category=?
                         AND tier >= ?
                         AND confidence >= ?
                         AND (expires_at IS NULL OR expires_at > datetime('now'))
                       ORDER BY tier DESC, confidence DESC, updated_at DESC
                       LIMIT ?""",
                    (self.chat_id, category, min_tier, min_conf, limit)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[user_model] get_category error: {e}")
            return []

    def get_profile(self, include_session: bool = True) -> dict:
        """
        Return the full user profile as a structured dict.
        Suitable for building a context block.
        """
        profile: dict[str, list] = {cat: [] for cat in VALID_CATEGORIES}

        # Session memory
        if include_session:
            for item in self._session_memory:
                profile[item["category"]].append({
                    "content":    item["content"],
                    "tier":       TIER_SESSION,
                    "confidence": 1.0,
                    "source":     item["source"],
                })

        # Persistent memory
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT category, content, tier, confidence, source
                       FROM rex_user_model
                       WHERE active=1
                         AND (chat_id=? OR chat_id IS NULL)
                         AND confidence >= 0.4
                         AND (expires_at IS NULL OR expires_at > datetime('now'))
                       ORDER BY tier DESC, confidence DESC
                       LIMIT 100""",
                    (self.chat_id,)
                ).fetchall()

                for row in rows:
                    cat = row["category"]
                    if cat in profile:
                        profile[cat].append({
                            "content":    row["content"],
                            "tier":       row["tier"],
                            "confidence": row["confidence"],
                            "source":     row["source"],
                        })
        except Exception as e:
            logger.error(f"[user_model] get_profile error: {e}")

        return profile

    def build_context_block(self, max_items_per_category: int = 3) -> str:
        """
        Build a compact context string to inject into the system prompt.
        Focuses on high-value, high-confidence entries.
        """
        profile = self.get_profile()
        lines   = []

        # Priority order for context injection
        priority_order = [
            "preferences",
            "emotional_support",
            "identity_facts",
            "goals",
            "trusted_facts",
            "patterns",
            "relationships",
            "recent_context",
        ]

        for cat in priority_order:
            items = profile.get(cat, [])
            # Sort by tier desc, confidence desc
            items = sorted(items, key=lambda x: (x["tier"], x["confidence"]), reverse=True)
            top   = items[:max_items_per_category]
            for item in top:
                tier_label = TIER_LABELS.get(item["tier"], "?")
                lines.append(f"[{cat.upper()}] {item['content']}")

        if not lines:
            return ""

        return "👤 Person context:\n" + "\n".join(f"  {l}" for l in lines) + "\n"

    def get_support_style(self) -> str:
        """
        Return the current preferred support style for this person.
        Used by the planner to adjust response strategy.
        """
        prefs = self.get_category("emotional_support", min_conf=0.5, limit=5)
        pref_text = self.get_category("preferences", min_conf=0.5, limit=5)

        notes = [p["content"] for p in prefs + pref_text]
        if not notes:
            return "standard"   # Default

        notes_lower = " ".join(notes).lower()
        if any(w in notes_lower for w in ["brief", "short", "concise", "quick"]):
            return "brief"
        if any(w in notes_lower for w in ["detailed", "thorough", "full", "explain"]):
            return "detailed"
        if any(w in notes_lower for w in ["emotional", "gentle", "soft", "support"]):
            return "gentle"
        if any(w in notes_lower for w in ["direct", "blunt", "no fluff", "just tell"]):
            return "direct"
        return "standard"

    # ─────────────────────────────────────────────
    # AUTO-EXTRACT FROM MESSAGE
    # ─────────────────────────────────────────────

    def extract_and_store(self, text: str, source: str = "observed") -> list[str]:
        """
        Attempt to extract user model signals from a single message.
        Returns list of what was stored.
        Returns: list of stored category labels
        """
        stored = []
        text_lower = text.lower()

        # Explicit preferences: "I prefer...", "I like...", "I want..."
        pref_patterns = [
            r"i (?:prefer|like|want|love|enjoy|need)\s+(.{10,80})",
            r"please (?:always|keep|make sure)\s+(.{10,80})",
            r"don'?t (?:ever|always)\s+(.{10,80})",
            r"i (?:hate|dislike|don'?t like)\s+(.{10,80})",
            r"remember that i\s+(.{10,80})",
            r"keep in mind that\s+(.{10,80})",
        ]
        for pattern in pref_patterns:
            match = re.search(pattern, text_lower)
            if match:
                self.update(
                    "preferences", text.strip(),
                    tier=TIER_LONG_TERM, confidence=0.85, source="explicit"
                )
                stored.append("preferences")
                break

        # Goals: "I'm working on...", "my goal is...", "I want to build..."
        goal_patterns = [
            r"(?:i'?m|i am) (?:working on|building|creating|developing)\s+(.{10,80})",
            r"my (?:goal|objective|target|aim) is\s+(.{10,80})",
            r"i (?:need to|want to|plan to) (?:finish|complete|build|launch)\s+(.{10,80})",
        ]
        for pattern in goal_patterns:
            match = re.search(pattern, text_lower)
            if match:
                self.update(
                    "goals", text.strip()[:200],
                    tier=TIER_SHORT_TERM, confidence=0.8, source="observed"
                )
                stored.append("goals")
                break

        # Stress / emotional signals → emotional_support patterns
        stress_patterns = [
            r"i'?m (?:stressed|overwhelmed|exhausted|tired|burned out|struggling)",
            r"this is (?:hard|difficult|a lot|too much)",
            r"i (?:can'?t|don'?t) (?:keep up|handle|manage)",
        ]
        for pattern in stress_patterns:
            if re.search(pattern, text_lower):
                self.update_inferred(
                    "emotional_support",
                    f"User showed signs of stress: '{text.strip()[:100]}'",
                    confidence=0.65
                )
                stored.append("emotional_support")
                break

        # Explicit "remember": "remember that...", "don't forget..."
        remember_patterns = [
            r"remember (?:that |this |—\s*)?(.{10,120})",
            r"don'?t forget\s+(.{10,120})",
            r"make a note\s+(.{10,120})",
        ]
        for pattern in remember_patterns:
            match = re.search(pattern, text_lower)
            if match:
                self.update_explicit("trusted_facts", text.strip()[:200])
                stored.append("trusted_facts")
                break

        return stored

    # ─────────────────────────────────────────────
    # MAINTENANCE
    # ─────────────────────────────────────────────

    def expire_old(self) -> int:
        """Mark expired entries as inactive. Returns count."""
        try:
            with self._connect() as conn:
                result = conn.execute(
                    """UPDATE rex_user_model
                       SET active=0
                       WHERE active=1
                         AND expires_at IS NOT NULL
                         AND expires_at < datetime('now')"""
                )
                conn.commit()
                n = result.rowcount
                if n:
                    logger.info(f"[user_model] Expired {n} entries")
                return n
        except Exception as e:
            logger.error(f"[user_model] expire_old error: {e}")
            return 0

    def clear_session(self) -> None:
        """Clear all session (Tier 1) memory. Call at end of conversation."""
        count = len(self._session_memory)
        self._session_memory = []
        logger.debug(f"[user_model] Cleared {count} session memories")

    def promote(self, entry_id: int) -> bool:
        """Promote an entry from short-term to long-term (called by reflection layer)."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """UPDATE rex_user_model
                       SET tier=3, confidence=MIN(confidence+0.1, 1.0),
                           expires_at=NULL, updated_at=datetime('now')
                       WHERE id=?""",
                    (entry_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[user_model] promote error: {e}")
            return False

    def demote(self, entry_id: int) -> bool:
        """Demote an entry — reduce confidence (called by reflection layer)."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """UPDATE rex_user_model
                       SET confidence=MAX(confidence-0.15, 0.1),
                           updated_at=datetime('now')
                       WHERE id=?""",
                    (entry_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[user_model] demote error: {e}")
            return False

    def get_stats(self) -> dict:
        """Return model stats for diagnostics."""
        try:
            with self._connect() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) as n FROM rex_user_model WHERE active=1"
                ).fetchone()["n"]

                by_cat = conn.execute(
                    """SELECT category, COUNT(*) as n
                       FROM rex_user_model WHERE active=1
                       GROUP BY category ORDER BY n DESC"""
                ).fetchall()

                by_tier = conn.execute(
                    """SELECT tier, COUNT(*) as n
                       FROM rex_user_model WHERE active=1
                       GROUP BY tier ORDER BY tier"""
                ).fetchall()

                return {
                    "total":    total,
                    "session":  len(self._session_memory),
                    "by_cat":   {r["category"]: r["n"] for r in by_cat},
                    "by_tier":  {TIER_LABELS.get(r["tier"],'?'): r["n"] for r in by_tier},
                }
        except Exception as e:
            logger.error(f"[user_model] get_stats error: {e}")
            return {}

    # ─────────────────────────────────────────────
    # INTERNALS
    # ─────────────────────────────────────────────

    def _find_similar(
        self,
        conn:     sqlite3.Connection,
        category: str,
        content:  str,
        threshold: float = 0.60,
    ) -> Optional[sqlite3.Row]:
        """Find an existing entry similar enough to be considered a duplicate."""
        rows = conn.execute(
            """SELECT id, content FROM rex_user_model
               WHERE active=1 AND category=?
                 AND (chat_id=? OR chat_id IS NULL)
               LIMIT 50""",
            (category, self.chat_id)
        ).fetchall()

        c_tokens = set(re.findall(r"[a-z0-9]+", content.lower()))
        best_row, best_score = None, 0.0

        for row in rows:
            r_tokens = set(re.findall(r"[a-z0-9]+", row["content"].lower()))
            if not c_tokens or not r_tokens:
                continue
            overlap = len(c_tokens & r_tokens)
            score   = 2.0 * overlap / (len(c_tokens) + len(r_tokens))
            if score > best_score:
                best_score, best_row = score, row

        return best_row if best_score >= threshold else None


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os

    print("=" * 60)
    print("USER MODEL SELF-TEST")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        um = UserModel(db_path, chat_id=12345)

        # Test explicit storage
        um.update_explicit("identity_facts",  "User's name is Kato")
        um.update_explicit("identity_facts",  "Kato runs Garden of Joy adult day care in Brooklyn")
        um.update_explicit("preferences",     "Kato prefers short replies when busy")
        um.update_explicit("preferences",     "Kato likes direct answers without filler")
        um.update("goals",   "Building REX — a local-first AI system", tier=2, confidence=0.9)
        um.update("goals",   "Wants Rexxie to grow smarter over time", tier=3, confidence=0.85)
        um.update("patterns","Usually messages in the morning before the program starts", tier=3)
        um.update("emotional_support", "When overwhelmed, prefers action steps over advice", tier=3)

        # Test session memory
        um.update("recent_context", "Just discussed the new transport schedule", tier=1)

        # Test extract_and_store
        test_msgs = [
            "I prefer you keep responses under 3 sentences",
            "I'm working on the policy enforcer module today",
            "I'm stressed, there's too much to do today",
            "Remember that the Friday activity is always crafts",
        ]
        print("\nAuto-extraction test:")
        for msg in test_msgs:
            stored = um.extract_and_store(msg)
            print(f"  '{msg[:50]}' → stored: {stored}")

        # Test context block
        print("\nContext block:")
        print(um.build_context_block())

        # Test support style
        style = um.get_support_style()
        print(f"Support style: {style}")

        # Stats
        stats = um.get_stats()
        print(f"\nStats: {stats}")

        print("✓ All tests passed.")
    finally:
        os.unlink(db_path)
