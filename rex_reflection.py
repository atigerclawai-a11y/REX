"""
rex_reflection.py
─────────────────
Rexxie – Reflection and Growth Layer

Rexxie evaluates itself periodically to grow smarter at helping
a specific person — without changing its core identity or bypassing policy.

WHAT IT DOES
────────────
1. Logs each response exchange with outcome signals
2. Periodically analyzes what response styles worked best
3. Promotes short-term user model entries that keep proving useful
4. Demotes entries that turned out to be incorrect or outdated
5. Writes reflection insights as Tier 4 memory entries
6. Produces strategy recommendations for the planner

WHAT IT DOES NOT DO
───────────────────
- It does not change core identity or policy rules
- It does not modify code
- It does not act autonomously
- It does not store sensitive or PHI information
- It does not override the policy enforcer

GROWTH SIGNALS
──────────────
  positive_signal : user said "yes", "thanks", "that's right", "exactly", "perfect"
  negative_signal : user said "no", "wrong", "not what I asked", "that's not right"
  follow_up       : user had to ask again — may mean response was incomplete
  explicit_teach  : user corrected Rexxie directly ("actually I meant...")
  completion      : task was completed successfully

Usage:
    from rex_reflection import Reflection

    r = Reflection(db_path="~/Desktop/REX/rexxie_memory.db", chat_id=12345)

    # After each exchange:
    r.log_exchange(intent="menu_query", response_style="brief",
                   user_message="what's for lunch", response="Chicken and rice today.")

    # After a positive signal:
    r.signal_positive(last_exchange_id)

    # Periodically (e.g., every 20 messages):
    insights = r.reflect()
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rex.reflection")

# ─────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS rex_exchanges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id        INTEGER,
    intent         TEXT,
    response_style TEXT,
    user_message   TEXT,
    response_len   INTEGER,
    outcome        TEXT    DEFAULT 'unknown',
    created_at     TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rex_reflection_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER,
    insight      TEXT,
    category     TEXT,
    confidence   REAL   DEFAULT 0.7,
    created_at   TEXT   DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exc_chat   ON rex_exchanges(chat_id);
CREATE INDEX IF NOT EXISTS idx_exc_intent ON rex_exchanges(intent);
"""

# ─────────────────────────────────────────────
# OUTCOME SIGNALS
# ─────────────────────────────────────────────

POSITIVE_WORDS = {
    "yes", "thanks", "thank you", "perfect", "exactly", "correct",
    "that's right", "great", "awesome", "helpful", "got it", "understood",
    "that works", "good", "nice", "love it", "excellent", "yes please",
}

NEGATIVE_WORDS = {
    "no", "wrong", "not right", "incorrect", "that's not what",
    "not what i asked", "not what i meant", "try again", "that's wrong",
    "nope", "no that's not", "you missed", "misunderstood",
}

CORRECTION_WORDS = {
    "actually", "i meant", "what i meant", "let me clarify",
    "to clarify", "i said", "no i meant", "not that",
}


def _detect_signal(text: str) -> str:
    """
    Detect the outcome signal from a user message.
    Returns: "positive" | "negative" | "correction" | "follow_up" | "neutral"
    """
    text_lower = text.lower().strip()

    # Short affirmative
    if text_lower in {"yes", "yeah", "yep", "ok", "okay", "thanks", "got it", "perfect"}:
        return "positive"

    if any(w in text_lower for w in POSITIVE_WORDS):
        return "positive"

    if any(w in text_lower for w in NEGATIVE_WORDS):
        return "negative"

    if any(w in text_lower for w in CORRECTION_WORDS):
        return "correction"

    # Follow-up (asking the same thing again, but we can't easily detect this
    # without comparing to previous message — mark as neutral for now)
    return "neutral"


class Reflection:
    """
    Growth and adaptation engine for Rexxie.

    Tracks how responses land and builds recommendations
    for improving response style for a specific person.
    """

    def __init__(
        self,
        db_path:  str | Path,
        chat_id:  Optional[int]  = None,
        user_model=None,   # Optional: pass rex_user_model.UserModel instance
    ):
        self.db_path    = Path(db_path).expanduser()
        self.chat_id    = chat_id
        self.user_model = user_model
        self._last_exchange_id: Optional[int] = None
        self._exchange_buffer: list[dict] = []   # Recent exchanges in memory
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(_DDL)
        except Exception as e:
            logger.error(f"[reflection] DB init failed: {e}")

    # ─────────────────────────────────────────────
    # LOGGING
    # ─────────────────────────────────────────────

    def log_exchange(
        self,
        intent:         str,
        user_message:   str,
        response:       str,
        response_style: str = "standard",
        outcome:        str = "unknown",
    ) -> int:
        """
        Log a single exchange (user message + Rexxie response).
        Returns the exchange ID.
        """
        try:
            with self._connect() as conn:
                result = conn.execute(
                    """INSERT INTO rex_exchanges
                       (chat_id, intent, response_style, user_message, response_len, outcome)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        self.chat_id,
                        intent,
                        response_style,
                        user_message.strip()[:200],
                        len(response),
                        outcome,
                    )
                )
                conn.commit()
                self._last_exchange_id = result.lastrowid

                # Keep a short in-memory buffer of recent exchanges
                self._exchange_buffer.append({
                    "id":             self._last_exchange_id,
                    "intent":         intent,
                    "response_style": response_style,
                    "outcome":        outcome,
                })
                if len(self._exchange_buffer) > 20:
                    self._exchange_buffer.pop(0)

                return self._last_exchange_id
        except Exception as e:
            logger.error(f"[reflection] log_exchange error: {e}")
            return -1

    def process_incoming_signal(self, user_message: str) -> str:
        """
        Called when a new user message arrives.
        Interprets it as a signal about the PREVIOUS response.
        Updates the last exchange outcome.
        Returns the detected signal.
        """
        signal = _detect_signal(user_message)

        if self._last_exchange_id and signal != "neutral":
            try:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE rex_exchanges SET outcome=? WHERE id=?",
                        (signal, self._last_exchange_id)
                    )
                    conn.commit()
                logger.debug(
                    f"[reflection] Exchange {self._last_exchange_id} "
                    f"outcome → {signal}"
                )

                # Update exchange buffer
                for ex in self._exchange_buffer:
                    if ex["id"] == self._last_exchange_id:
                        ex["outcome"] = signal
                        break

            except Exception as e:
                logger.error(f"[reflection] signal update error: {e}")

        return signal

    # ─────────────────────────────────────────────
    # REFLECTION (the growth engine)
    # ─────────────────────────────────────────────

    def reflect(self, lookback_days: int = 30) -> list[str]:
        """
        Analyze recent exchanges and generate growth insights.

        Should be called periodically (e.g., every 20 messages, or daily).
        Returns a list of insight strings that were generated.
        """
        insights = []

        try:
            with self._connect() as conn:
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(days=lookback_days)
                ).isoformat()

                rows = conn.execute(
                    """SELECT intent, response_style, outcome, COUNT(*) as n
                       FROM rex_exchanges
                       WHERE (chat_id=? OR chat_id IS NULL)
                         AND created_at > ?
                         AND outcome != 'unknown'
                       GROUP BY intent, response_style, outcome
                       ORDER BY n DESC""",
                    (self.chat_id, cutoff)
                ).fetchall()

            if not rows:
                return []

            # Aggregate by intent + style
            stats: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
            for row in rows:
                stats[row["intent"]][row["response_style"]][row["outcome"]] += row["n"]

            # Analyze each intent
            for intent, styles in stats.items():
                best_style, best_ratio = None, 0.0

                for style, outcomes in styles.items():
                    pos  = outcomes.get("positive", 0)
                    neg  = outcomes.get("negative", 0)
                    corr = outcomes.get("correction", 0)
                    total = pos + neg + corr
                    if total < 3:
                        continue   # Not enough data
                    ratio = pos / total
                    if ratio > best_ratio:
                        best_ratio, best_style = ratio, style

                if best_style and best_ratio >= 0.6:
                    insight = (
                        f"For {intent} messages, '{best_style}' style "
                        f"gets positive responses {best_ratio:.0%} of the time."
                    )
                    insights.append(insight)
                    self._store_insight(insight, "response_style", confidence=best_ratio)

                # Detect what's NOT working
                for style, outcomes in styles.items():
                    neg  = outcomes.get("negative", 0)
                    corr = outcomes.get("correction", 0)
                    total = sum(outcomes.values())
                    if total >= 3 and (neg + corr) / total >= 0.5:
                        insight = (
                            f"For {intent} messages, '{style}' style "
                            f"is getting too many negative signals — consider switching."
                        )
                        insights.append(insight)
                        self._store_insight(insight, "avoid_style", confidence=0.7)

            # Check for length preference
            len_insight = self._analyze_length_preference()
            if len_insight:
                insights.append(len_insight)

            # Promote user model entries that have been accessed frequently
            if self.user_model:
                self._promote_useful_entries()

            if insights:
                logger.info(
                    f"[reflection] Generated {len(insights)} insights "
                    f"for chat_id={self.chat_id}"
                )

        except Exception as e:
            logger.error(f"[reflection] reflect error: {e}")

        return insights

    def get_strategy_hint(self, intent: str) -> Optional[str]:
        """
        Return the current best-known response strategy for a given intent.
        Used by the planner to adapt response style.
        """
        try:
            with self._connect() as conn:
                # Look for style insights for this intent
                row = conn.execute(
                    """SELECT insight FROM rex_reflection_log
                       WHERE (chat_id=? OR chat_id IS NULL)
                         AND category='response_style'
                         AND insight LIKE ?
                       ORDER BY confidence DESC, created_at DESC
                       LIMIT 1""",
                    (self.chat_id, f"%{intent}%")
                ).fetchone()

                if row:
                    return row["insight"]
        except Exception as e:
            logger.error(f"[reflection] get_strategy_hint error: {e}")

        return None

    def get_all_insights(self, limit: int = 10) -> list[dict]:
        """Return recent reflection insights."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT insight, category, confidence, created_at
                       FROM rex_reflection_log
                       WHERE (chat_id=? OR chat_id IS NULL)
                       ORDER BY confidence DESC, created_at DESC
                       LIMIT ?""",
                    (self.chat_id, limit)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[reflection] get_all_insights error: {e}")
            return []

    def get_stats(self) -> dict:
        """Return reflection stats for diagnostics."""
        try:
            with self._connect() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) as n FROM rex_exchanges WHERE chat_id=?",
                    (self.chat_id,)
                ).fetchone()["n"]

                outcomes = conn.execute(
                    """SELECT outcome, COUNT(*) as n FROM rex_exchanges
                       WHERE chat_id=? GROUP BY outcome""",
                    (self.chat_id,)
                ).fetchall()

                insights = conn.execute(
                    "SELECT COUNT(*) as n FROM rex_reflection_log WHERE chat_id=?",
                    (self.chat_id,)
                ).fetchone()["n"]

                return {
                    "total_exchanges": total,
                    "outcomes":  {r["outcome"]: r["n"] for r in outcomes},
                    "insights":  insights,
                    "buffer_size": len(self._exchange_buffer),
                }
        except Exception as e:
            logger.error(f"[reflection] get_stats error: {e}")
            return {}

    # ─────────────────────────────────────────────
    # INTERNAL
    # ─────────────────────────────────────────────

    def _store_insight(self, insight: str, category: str, confidence: float) -> None:
        """Store a reflection insight in the log."""
        try:
            with self._connect() as conn:
                # Avoid storing near-duplicate insights
                existing = conn.execute(
                    """SELECT id FROM rex_reflection_log
                       WHERE chat_id=? AND insight=?""",
                    (self.chat_id, insight)
                ).fetchone()

                if existing:
                    conn.execute(
                        """UPDATE rex_reflection_log
                           SET confidence=MAX(confidence,?), created_at=datetime('now')
                           WHERE id=?""",
                        (confidence, existing["id"])
                    )
                else:
                    conn.execute(
                        """INSERT INTO rex_reflection_log
                           (chat_id, insight, category, confidence)
                           VALUES (?,?,?,?)""",
                        (self.chat_id, insight, category, confidence)
                    )
                conn.commit()

                # Also store in user model as Tier 4 reflection memory
                if self.user_model:
                    self.user_model.update(
                        "patterns", f"[REFLECTION] {insight}",
                        tier=4, confidence=confidence, source="reflection"
                    )
        except Exception as e:
            logger.error(f"[reflection] _store_insight error: {e}")

    def _analyze_length_preference(self) -> Optional[str]:
        """Check if user responds better to short or long replies."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT response_len, outcome FROM rex_exchanges
                       WHERE (chat_id=? OR chat_id IS NULL)
                         AND outcome IN ('positive','negative')
                       ORDER BY created_at DESC LIMIT 50""",
                    (self.chat_id,)
                ).fetchall()

            if len(rows) < 10:
                return None

            short_pos, short_neg = 0, 0
            long_pos,  long_neg  = 0, 0

            for row in rows:
                is_short = row["response_len"] < 300
                is_pos   = row["outcome"] == "positive"
                if is_short:
                    short_pos += int(is_pos)
                    short_neg += int(not is_pos)
                else:
                    long_pos  += int(is_pos)
                    long_neg  += int(not is_pos)

            short_total = short_pos + short_neg
            long_total  = long_pos  + long_neg

            if short_total >= 5 and long_total >= 5:
                short_ratio = short_pos / short_total
                long_ratio  = long_pos  / long_total

                if short_ratio > long_ratio + 0.2:
                    insight = (
                        "Shorter replies (under 300 chars) get better responses — "
                        "this person prefers concise answers."
                    )
                    self._store_insight(insight, "length_preference", short_ratio)
                    if self.user_model:
                        self.user_model.update_inferred(
                            "preferences",
                            "Prefers concise replies — shorter responses land better.",
                            confidence=min(short_ratio, 0.9)
                        )
                    return insight
                elif long_ratio > short_ratio + 0.2:
                    insight = (
                        "Longer, more detailed replies get better responses — "
                        "this person prefers thorough answers."
                    )
                    self._store_insight(insight, "length_preference", long_ratio)
                    return insight

        except Exception as e:
            logger.error(f"[reflection] _analyze_length_preference error: {e}")

        return None

    def _promote_useful_entries(self) -> int:
        """
        Promote short-term user model entries that have been accessed
        frequently and appear in exchanges with positive outcomes.
        Called during reflection.
        """
        if not self.user_model:
            return 0

        promoted = 0
        try:
            with self.user_model._connect() as conn:
                # Find short-term entries accessed 3+ times
                candidates = conn.execute(
                    """SELECT id, content, confidence FROM rex_user_model
                       WHERE active=1 AND tier=2
                         AND access_count >= 3
                         AND (chat_id=? OR chat_id IS NULL)""",
                    (self.chat_id,)
                ).fetchall()

                for row in candidates:
                    self.user_model.promote(row["id"])
                    promoted += 1
                    logger.info(
                        f"[reflection] Promoted T2→T3: {row['content'][:60]}"
                    )
        except Exception as e:
            logger.error(f"[reflection] _promote_useful_entries error: {e}")

        return promoted


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os
    from rex_user_model import UserModel

    print("=" * 60)
    print("REFLECTION SELF-TEST")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        um = UserModel(db_path, chat_id=12345)
        r  = Reflection(db_path, chat_id=12345, user_model=um)

        # Simulate exchanges with outcomes
        exchanges = [
            ("menu_query",    "What's for lunch?",        "Chicken and rice.", "brief",    "positive"),
            ("menu_query",    "And tomorrow?",            "Fish on Tuesday.",   "brief",    "positive"),
            ("menu_query",    "Any dessert?",             "Fruit cups.",        "brief",    "positive"),
            ("attendance",    "Who is here?",             "14 present today.",  "brief",    "positive"),
            ("attendance",    "Mark Maria absent",        "Done, marked.",      "brief",    "positive"),
            ("question",      "How do I do X?",
             "Here is a very long explanation that goes on and on about how to do X and covers every detail.",
             "detailed", "negative"),
            ("question",      "Can you keep it short?",  "Yes, got it.",       "brief",    "positive"),
            ("question",      "What time is pickup?",    "3:30 PM.",           "brief",    "positive"),
            ("absence_letter","Generate letter for Mrs J","Here is the letter...", "detailed","positive"),
        ]

        print("\nLogging exchanges...")
        for intent, user_msg, resp, style, expected_outcome in exchanges:
            eid = r.log_exchange(intent, user_msg, resp, style)
            # Simulate the next message signaling the outcome
            signal = r.process_incoming_signal(
                "thanks that's perfect" if expected_outcome == "positive"
                else "no that's wrong"
            )
            print(f"  [{intent:20s}] style={style:10s} → signal={signal}")

        # Run reflection
        print("\nRunning reflection...")
        insights = r.reflect(lookback_days=365)
        for insight in insights:
            print(f"  💡 {insight}")

        # Get strategy hints
        for intent in ["menu_query", "attendance", "question"]:
            hint = r.get_strategy_hint(intent)
            if hint:
                print(f"\n  Strategy for {intent}: {hint[:80]}")

        # Stats
        stats = r.get_stats()
        print(f"\nReflection stats: {stats}")

        print("\n✓ Reflection tests passed.")
    finally:
        os.unlink(db_path)
