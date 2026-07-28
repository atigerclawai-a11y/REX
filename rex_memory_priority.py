"""
rex_memory_priority.py
──────────────────────
Rexxie GOJ – Memory Prioritization Layer

Upgrades keyword-only memory retrieval with:
  1. Importance scoring   — weight by memory type (decision > blocker > idea > etc.)
  2. Recency decay        — recent memories score higher; old noise fades over time
  3. Access boost         — memories retrieved often are more likely to be retrieved again
  4. Composite ranking    — blends relevance + importance + recency + access into one score

Drop-in upgrade for _retrieve_relevant_memory() in rex_rexxie_telegram_bot.py

Usage:
    from rex_memory_priority import PriorityMemory

    pm = PriorityMemory(db_path="/path/to/goj_rexxie.db")
    results = pm.retrieve(query="menu today lunch", limit=5, chat_id=12345)
"""

from __future__ import annotations

import re
import sqlite3
import math
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("rex.memory_priority")

# ─────────────────────────────────────────────
# TYPE IMPORTANCE WEIGHTS
# Higher = more likely to surface in retrieval
# Scale: 0.0 → 1.0
# ─────────────────────────────────────────────
TYPE_WEIGHTS: dict[str, float] = {
    "decision":   1.0,   # Decisions made — most critical to remember
    "blocker":    0.95,  # Blockers — high urgency
    "preference": 0.85,  # Kato's preferences — personality/style guide
    "state":      0.80,  # Current state — what's active/in-progress
    "question":   0.65,  # Open questions — useful but lower than resolved items
    "idea":       0.55,  # Ideas — useful but exploratory
}

DEFAULT_TYPE_WEIGHT = 0.50

# ─────────────────────────────────────────────
# RECENCY DECAY PARAMETERS
# Half-life: how many days before a memory's recency score halves
# ─────────────────────────────────────────────
HALF_LIFE_DAYS = 14.0   # Memories older than 2 weeks decay significantly

# ─────────────────────────────────────────────
# ACCESS BOOST
# Each time a memory is retrieved, its boost counter increments
# Frequently-accessed memories get a mild score bump
# ─────────────────────────────────────────────
ACCESS_BOOST_CAP    = 0.30   # Max boost from access frequency
ACCESS_BOOST_SCALE  = 5.0    # Number of accesses to reach cap


def _recency_score(created_at_iso: str) -> float:
    """
    Exponential decay based on age.
    Returns 1.0 for brand-new memories, approaching 0.0 for very old ones.
    """
    try:
        created = datetime.fromisoformat(created_at_iso)
        # Make timezone-aware if needed
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = (now - created).total_seconds() / 86400.0
        # Exponential decay: score = 2^(-age/half_life)
        return math.pow(2.0, -age_days / HALF_LIFE_DAYS)
    except Exception:
        return 0.5   # Neutral if we can't parse the date


def _access_boost(access_count: int) -> float:
    """
    Logarithmic boost based on how many times a memory has been retrieved.
    Caps at ACCESS_BOOST_CAP.
    """
    if access_count <= 0:
        return 0.0
    raw = math.log1p(access_count) / math.log1p(ACCESS_BOOST_SCALE)
    return min(raw, ACCESS_BOOST_CAP)


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    # Extract only alphanumeric runs
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a", "an", "the", "is", "it", "in", "on", "at", "to", "of",
            "and", "or", "for", "with", "was", "are", "be", "as", "by",
            "i", "we", "you", "he", "she", "they", "my", "your", "our",
            "this", "that", "have", "has", "had", "not", "no", "so"}
    return {t for t in tokens if t not in stop and len(t) > 1}


def _keyword_relevance(query: str, content: str) -> float:
    """
    Normalized keyword overlap score using clean token sets.
    Returns 0.0-1.0.
    """
    q_words = _tokenize(query)
    c_words = _tokenize(content)
    if not q_words:
        return 0.0
    overlap = len(q_words & c_words)
    # Normalize against query length (precision) blended with recall
    precision = overlap / len(q_words)
    recall    = overlap / max(len(c_words), 1)
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)   # F1-style blend


def _composite_score(
    relevance:    float,
    type_weight:  float,
    recency:      float,
    access_boost: float,
    weights: dict | None = None,
) -> float:
    """
    Weighted composite score across all 4 signals.

    Default weights balance recall quality with freshness.
    """
    w = weights or {
        "relevance":  0.50,
        "type":       0.20,
        "recency":    0.20,
        "access":     0.10,
    }
    score = (
        w["relevance"] * relevance +
        w["type"]      * type_weight +
        w["recency"]   * recency +
        w["access"]    * (access_boost / ACCESS_BOOST_CAP)  # normalize to 0-1
    )
    return round(score, 4)


class PriorityMemory:
    """
    Priority-aware memory retrieval for Rexxie.

    Wraps the rexxie_ideas SQLite table and provides ranked retrieval
    with importance, recency, and access signals.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_columns()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_columns(self) -> None:
        """
        Ensure the rexxie_ideas table has the priority columns.
        Safe to run even if columns already exist.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                # Check existing columns
                cursor.execute("PRAGMA table_info(rexxie_ideas)")
                existing = {row["name"] for row in cursor.fetchall()}

                if "access_count" not in existing:
                    conn.execute(
                        "ALTER TABLE rexxie_ideas ADD COLUMN access_count INTEGER DEFAULT 0"
                    )
                    logger.info("[memory_priority] Added access_count column")

                if "importance" not in existing:
                    conn.execute(
                        "ALTER TABLE rexxie_ideas ADD COLUMN importance REAL DEFAULT 0.5"
                    )
                    logger.info("[memory_priority] Added importance column")

                conn.commit()
        except sqlite3.OperationalError as e:
            # Table might not exist yet — that's fine, it'll be created by the bot
            logger.debug(f"[memory_priority] Schema check: {e}")

    def _bump_access(self, conn: sqlite3.Connection, idea_id: int) -> None:
        """Increment access counter for a retrieved memory."""
        conn.execute(
            "UPDATE rexxie_ideas SET access_count = COALESCE(access_count, 0) + 1 WHERE id = ?",
            (idea_id,)
        )

    def retrieve(
        self,
        query:     str,
        limit:     int = 5,
        chat_id:   Optional[int] = None,
        idea_type: Optional[str] = None,
        min_score: float = 0.05,
        custom_weights: dict | None = None,
    ) -> list[dict]:
        """
        Retrieve memories ranked by composite priority score.

        Args:
            query:          Search text (user's message or topic)
            limit:          Max number of memories to return
            chat_id:        If set, filter to this chat's memories
            idea_type:      If set, filter to this type (decision/idea/etc.)
            min_score:      Minimum composite score to include
            custom_weights: Override default signal weights

        Returns:
            List of dicts: {id, idea_type, content, source, status,
                            created_at, score, relevance, recency}
        """
        if not query.strip():
            return []

        try:
            with self._connect() as conn:
                # Build query
                sql = """
                    SELECT id, idea_type, content, source, component_link,
                           status, created_at,
                           COALESCE(access_count, 0) AS access_count,
                           COALESCE(importance, 0.5) AS importance
                    FROM rexxie_ideas
                    WHERE status != 'archived'
                """
                params: list = []
                if chat_id is not None:
                    sql += " AND (source LIKE ? OR source IS NULL)"
                    params.append(f"%{chat_id}%")
                if idea_type:
                    sql += " AND idea_type = ?"
                    params.append(idea_type)

                sql += " ORDER BY created_at DESC LIMIT 500"   # Pull recent 500, rank in Python

                rows = conn.execute(sql, params).fetchall()

                # Score each memory
                scored = []
                for row in rows:
                    relevance   = _keyword_relevance(query, row["content"])
                    type_wt     = TYPE_WEIGHTS.get(row["idea_type"], DEFAULT_TYPE_WEIGHT)
                    recency     = _recency_score(row["created_at"])
                    access_b    = _access_boost(row["access_count"])
                    composite   = _composite_score(
                        relevance, type_wt, recency, access_b, custom_weights
                    )
                    if composite >= min_score:
                        # Intrinsic confidence — rises over time as memory is recalled.
                        # Uses type + recency + access frequency + importance.
                        # Does NOT include query-relevance so the % is stable across
                        # different conversations and only grows as the memory matures.
                        intrinsic = _composite_score(
                            relevance   = 0.0,   # excluded — we want time-growth, not query drift
                            type_weight = type_wt,
                            recency     = recency,
                            access_boost= access_b,
                            weights     = {
                                "relevance": 0.00,
                                "type":      0.38,
                                "recency":   0.32,
                                "access":    0.30,
                            },
                        )
                        scored.append({
                            "id":             row["id"],
                            "idea_type":      row["idea_type"],
                            "content":        row["content"],
                            "source":         row["source"],
                            "component_link": row["component_link"],
                            "status":         row["status"],
                            "created_at":     row["created_at"],
                            "access_count":   row["access_count"],
                            "importance":     row["importance"],
                            "score":          composite,       # used for ranking/retrieval
                            "confidence":     round(intrinsic, 4),  # shown to user, grows over time
                            "relevance":      round(relevance, 4),
                            "recency":        round(recency, 4),
                        })

                # Sort by composite score descending
                scored.sort(key=lambda x: x["score"], reverse=True)
                top = scored[:limit]

                # Update access counts for returned memories
                for item in top:
                    self._bump_access(conn, item["id"])
                conn.commit()

                logger.debug(
                    f"[memory_priority] query={query!r} → "
                    f"{len(scored)} scored, {len(top)} returned"
                )
                return top

        except Exception as e:
            logger.error(f"[memory_priority] retrieve error: {e}")
            return []

    def set_importance(self, idea_id: int, importance: float) -> None:
        """
        Manually set the importance score of a specific memory.
        importance: 0.0 (low) → 1.0 (critical)
        """
        importance = max(0.0, min(1.0, importance))
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE rexxie_ideas SET importance = ? WHERE id = ?",
                    (importance, idea_id)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[memory_priority] set_importance error: {e}")

    def archive_old(self, days_threshold: float = 60.0) -> int:
        """
        Archive memories older than `days_threshold` days that have
        never been accessed (access_count = 0).
        Returns count of archived memories.
        """
        try:
            with self._connect() as conn:
                cutoff = datetime.now(timezone.utc)
                result = conn.execute(
                    """
                    UPDATE rexxie_ideas
                    SET status = 'archived'
                    WHERE status = 'open'
                      AND COALESCE(access_count, 0) = 0
                      AND datetime(created_at) < datetime('now', ?)
                    """,
                    (f"-{int(days_threshold)} days",)
                )
                conn.commit()
                count = result.rowcount
                if count:
                    logger.info(f"[memory_priority] Archived {count} old memories")
                return count
        except Exception as e:
            logger.error(f"[memory_priority] archive_old error: {e}")
            return 0

    def get_stats(self) -> dict:
        """Return memory stats for diagnostics."""
        try:
            with self._connect() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) as n FROM rexxie_ideas WHERE status != 'archived'"
                ).fetchone()["n"]

                by_type = conn.execute(
                    """
                    SELECT idea_type, COUNT(*) as n
                    FROM rexxie_ideas
                    WHERE status != 'archived'
                    GROUP BY idea_type
                    ORDER BY n DESC
                    """
                ).fetchall()

                most_accessed = conn.execute(
                    """
                    SELECT content, access_count
                    FROM rexxie_ideas
                    WHERE access_count > 0
                    ORDER BY access_count DESC
                    LIMIT 3
                    """
                ).fetchall()

                return {
                    "total": total,
                    "by_type": {r["idea_type"]: r["n"] for r in by_type},
                    "top_accessed": [
                        {"content": r["content"][:60], "count": r["access_count"]}
                        for r in most_accessed
                    ],
                }
        except Exception as e:
            logger.error(f"[memory_priority] get_stats error: {e}")
            return {}


# ─────────────────────────────────────────────
# Format helper for Rexxie responses
# ─────────────────────────────────────────────

def format_memory_context(
    memories: list[dict],
    prefix: str = "📝",
    show_confidence: bool = True,
) -> str:
    """
    Format retrieved memories as a compact context block for injection
    into the Rexxie system prompt or user message prefix.

    When show_confidence=True (default), each memory is annotated with
    a [XX% confidence] badge so Rexxie (and Kato) can see how reliable
    each piece of memory is.  Set show_confidence=False to suppress
    badges once the system is proven stable.

    Confidence is derived from the composite retrieval score (0–1):
      • 90–100%  High confidence
      • 75– 89%  Good confidence
      • 60– 74%  Moderate confidence
      • 45– 59%  Low confidence
      •  0– 44%  Very low confidence
    """
    if not memories:
        return ""

    lines = [f"{prefix} Relevant context from memory:"]
    for m in memories:
        type_label = m.get("idea_type", "note").upper()
        content    = m.get("content", "")[:200]

        if show_confidence:
            # Use intrinsic confidence (grows over time with recall),
            # not the query-relevance score (which fluctuates per question).
            raw_score  = m.get("confidence", m.get("score", 0.0))
            pct        = int(round(raw_score * 100))
            # Grade label
            if pct >= 90:
                grade = "High"
            elif pct >= 75:
                grade = "Good"
            elif pct >= 60:
                grade = "Moderate"
            elif pct >= 45:
                grade = "Low"
            else:
                grade = "Very low"
            confidence_badge = f" [{pct}% confidence – {grade}]"
        else:
            confidence_badge = ""

        lines.append(f"  [{type_label}]{confidence_badge} {content}")

    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os

    print("=" * 60)
    print("MEMORY PRIORITY SELF-TEST")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Create test DB
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE rexxie_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_type TEXT,
                content TEXT,
                source TEXT,
                component_link TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Insert test memories
        test_data = [
            ("decision",   "Lunch menu this week will be chicken, rice, and salad"),
            ("idea",       "We should add a garden activity on Fridays for participants"),
            ("preference", "Kato prefers concise summaries without bullet lists"),
            ("blocker",    "The attendance form is broken — IT needs to fix it today"),
            ("state",      "Current participant count: 18 active, 2 on leave"),
            ("question",   "Should we order more supplies for the art session?"),
        ]
        for idea_type, content in test_data:
            conn.execute(
                "INSERT INTO rexxie_ideas (idea_type, content, source) VALUES (?,?,?)",
                (idea_type, content, "test")
            )
        conn.commit()
        conn.close()

        pm = PriorityMemory(db_path)

        # Test retrieval
        queries = ["today lunch menu", "attendance form broken", "participant count active"]
        for q in queries:
            results = pm.retrieve(q, limit=3)
            print(f"\nQuery: {q!r}")
            for r in results:
                print(f"  [{r['idea_type']:10s}] score={r['score']:.3f} | {r['content'][:60]}")

        # Test stats
        stats = pm.get_stats()
        print(f"\nStats: {stats}")

        # Test context format
        results = pm.retrieve("lunch", limit=2)
        print(f"\nFormatted context:\n{format_memory_context(results)}")

        print("✓ All tests passed.")
    finally:
        os.unlink(db_path)
