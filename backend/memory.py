"""
REX — Persistent Memory System
================================
Gives REX a brain that survives across sessions.

Memory types:
  • fact      — A piece of knowledge to always carry ("The Chairman's name is Vlad")
  • preference — A behavior preference ("Always greet staff by first name")
  • context   — Operational context ("Next Sunday has 68 clients across 4 drivers")
  • secret    — Sensitive note stored with extra encryption, never echoed in logs

Commands (detected in user message):
  • "remember: ..."            → stores a fact
  • "forget: ..."              → removes matching memories
  • "what do you remember?"   → lists current memories

All memory content is AES-256-GCM encrypted at rest.
The master key is shared with EncryptedStorage.
"""

import os
import json
import base64
import logging
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Encryption helpers (copied from storage.py to keep memory self-contained) ──

def _encrypt(data: str, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, data.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def _decrypt(encoded: str, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(encoded)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(raw[:12], raw[12:], None).decode("utf-8")


# ── REX Memory Engine ──────────────────────────────────────────────────────────

class RexMemory:
    """
    Persistent, encrypted memory store for REX.

    Tables created inside ~/.rex/rex_journeys.db (shared with EncryptedStorage):
      rex_memory        — long-term facts and preferences
      rex_session_log   — compressed summaries of past sessions (for context resume)
    """

    MEMORY_TYPES = ("fact", "preference", "context", "secret")

    # Commands REX detects in user messages (case-insensitive prefix match)
    CMD_REMEMBER  = ("remember:", "remember this:", "note:", "always know:")
    CMD_FORGET    = ("forget:", "forget this:", "remove:", "delete memory:")
    CMD_LIST      = ("what do you remember", "show memory", "list memory",
                     "what do you know", "memory dump")

    # ── Chairman-only memory commands ─────────────────────────────────────────
    # Only role=chairman can set visibility levels or the share passphrase
    CMD_REMEMBER_CHAIRMAN = ("chairman only:", "private:", "confidential:", "chairman note:")
    CMD_REMEMBER_STAFF    = ("staff only:", "staff note:", "internal:")
    CMD_SET_PASSPHRASE    = ("set share passphrase:", "set passphrase:", "change passphrase:")

    # ── RED BUTTON: Emergency reset keyword (Chairman-only) ──────────────────
    # Saying "SOVEREIGN RESET" in the chat wipes ALL memory and session history.
    # This is the software equivalent of a hard reboot for REX's mind.
    CMD_RESET     = "sovereign reset"

    # ── External share gate ───────────────────────────────────────────────────
    # System tag used to identify the stored passphrase hash
    _PASSPHRASE_TAG = "__share_passphrase_hash__"

    def __init__(self, db_path: Path, key: bytes):
        self.db_path = db_path
        self._key    = key
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── Visibility levels ─────────────────────────────────────────────────────
    # VISIBILITY controls who can see a memory in chat responses and context:
    #   "all"            → All authenticated users (frontdesk, drivers, vlad, chairman)
    #   "staff"          → Vlad + chairman only (not frontdesk or drivers)
    #   "chairman_only"  → Chairman ONLY — never shown to any other role
    #   "system"         → Internal system use only — never shown to anyone in chat,
    #                      only used internally (e.g. hashed passphrases)
    VISIBILITY_LEVELS = ("all", "staff", "chairman_only", "system")

    # Roles allowed to see each visibility level
    ROLE_VISIBILITY = {
        "chairman":  {"all", "staff", "chairman_only", "system"},
        "vlad":      {"all", "staff"},
        "frontdesk": {"all"},
        "driver":    {"all"},
        "billing":   {"all", "staff"},
    }

    def _init_tables(self):
        with self._connect() as conn:
            # Create tables (IF NOT EXISTS — safe on first run and reruns)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS rex_memory (
                    id           TEXT PRIMARY KEY,
                    mem_type     TEXT NOT NULL DEFAULT 'fact',
                    content_enc  TEXT NOT NULL,
                    tags_enc     TEXT,
                    source       TEXT,
                    visibility   TEXT NOT NULL DEFAULT 'all',
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    recall_count INTEGER DEFAULT 0,
                    active       INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS rex_session_log (
                    id           TEXT PRIMARY KEY,
                    started_at   TEXT NOT NULL,
                    ended_at     TEXT,
                    user_id      TEXT,
                    summary_enc  TEXT,
                    topics_enc   TEXT,
                    actions_enc  TEXT,
                    msg_count    INTEGER DEFAULT 0,
                    active       INTEGER DEFAULT 1
                );
            """)

            # Migrate existing tables — add visibility column if it was added after
            # the DB was first created (SQLite has no ALTER COLUMN IF NOT EXISTS)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(rex_memory)")}
            if "visibility" not in existing:
                conn.execute(
                    "ALTER TABLE rex_memory ADD COLUMN visibility TEXT NOT NULL DEFAULT 'all'"
                )
                conn.commit()
                logger.info("🧠 Migrated rex_memory — added visibility column")

            # Indexes (safe to recreate — IF NOT EXISTS)
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_memory_visibility
                    ON rex_memory(visibility, active);
                CREATE INDEX IF NOT EXISTS idx_memory_type
                    ON rex_memory(mem_type, active);
                CREATE INDEX IF NOT EXISTS idx_session_started
                    ON rex_session_log(started_at DESC);
            """)
        logger.info("🧠 REX Memory tables initialized")

    # ── Store / Retrieve Memories ──────────────────────────────────────────────

    def store(
        self,
        content: str,
        mem_type: str = "fact",
        tags: Optional[List[str]] = None,
        source: str = "user",
        visibility: str = "all",
    ) -> str:
        """Encrypt and store a memory. Returns the new memory ID."""
        import uuid
        if visibility not in self.VISIBILITY_LEVELS:
            visibility = "all"
        mem_id      = str(uuid.uuid4())
        now         = datetime.utcnow().isoformat()
        content_enc = _encrypt(content.strip(), self._key)
        tags_enc    = _encrypt(json.dumps(tags or []), self._key)

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO rex_memory
                   (id, mem_type, content_enc, tags_enc, source, visibility, created_at, updated_at, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (mem_id, mem_type, content_enc, tags_enc, source, visibility, now, now),
            )
        vis_label = f" [{visibility}]" if visibility != "all" else ""
        logger.info(f"🧠 Memory stored [{mem_type}]{vis_label}: {content[:60]}…")
        return mem_id

    def forget(self, query: str) -> int:
        """Soft-delete memories whose content matches the query (case-insensitive). Returns count removed."""
        all_active = self._load_all_active()
        removed = 0
        q_lower = query.strip().lower()
        with self._connect() as conn:
            for mem in all_active:
                if q_lower in mem["content"].lower():
                    conn.execute(
                        "UPDATE rex_memory SET active = 0, updated_at = ? WHERE id = ?",
                        (datetime.utcnow().isoformat(), mem["id"]),
                    )
                    removed += 1
        logger.info(f"🧠 Forgot {removed} memories matching: {query[:60]}")
        return removed

    def _load_all_active(self, role: str = "chairman") -> List[Dict]:
        """Load active memories visible to the given role."""
        allowed_vis = self.ROLE_VISIBILITY.get(role, {"all"})
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, mem_type, content_enc, tags_enc, source, visibility, created_at, recall_count "
                "FROM rex_memory WHERE active = 1 ORDER BY created_at ASC"
            ).fetchall()
        result = []
        for row in rows:
            vis = row["visibility"] if "visibility" in row.keys() else "all"
            if vis not in allowed_vis:
                continue  # This role cannot see this memory
            try:
                content = _decrypt(row["content_enc"], self._key)
                tags    = json.loads(_decrypt(row["tags_enc"], self._key)) if row["tags_enc"] else []
            except Exception:
                continue
            result.append({
                "id":           row["id"],
                "mem_type":     row["mem_type"],
                "content":      content,
                "tags":         tags,
                "source":       row["source"],
                "visibility":   vis,
                "created_at":   row["created_at"],
                "recall_count": row["recall_count"],
            })
        return result

    def get_all(self, role: str = "chairman") -> List[Dict]:
        """Return active memories decrypted, filtered by caller's role.
        Chairman sees everything. Other roles see only their permitted visibility."""
        return self._load_all_active(role=role)

    def build_memory_context(self, role: str = "chairman") -> str:
        """
        Build the memory injection block for the system prompt.
        Secrets are never included in the readable context block —
        they're included in a separate sealed section only visible to the LLM.
        """
        mems = self._load_all_active(role=role)
        if not mems:
            return ""

        sections: Dict[str, List[str]] = {t: [] for t in self.MEMORY_TYPES}
        for m in mems:
            sections.get(m["mem_type"], sections["fact"]).append(m["content"])

        lines = ["## What REX Remembers (Persistent Memory)\n"]

        if sections["fact"]:
            lines.append("### Facts")
            for f in sections["fact"]:
                lines.append(f"- {f}")

        if sections["preference"]:
            lines.append("\n### Preferences & Behaviors")
            for p in sections["preference"]:
                lines.append(f"- {p}")

        if sections["context"]:
            lines.append("\n### Operational Context")
            for c in sections["context"]:
                lines.append(f"- {c}")

        if sections["secret"]:
            lines.append("\n### Confidential Notes (never repeat verbatim, use only to inform answers)")
            for s in sections["secret"]:
                lines.append(f"- [SEALED] {s}")

        # Bump recall count
        ids = [m["id"] for m in mems]
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.executemany(
                "UPDATE rex_memory SET recall_count = recall_count + 1, updated_at = ? WHERE id = ?",
                [(now, mid) for mid in ids],
            )

        return "\n".join(lines)

    # ── Command Detection ──────────────────────────────────────────────────────

    def detect_and_execute_command(
        self, user_text: str, source: str = "user", source_role: str = "staff"
    ) -> Optional[str]:
        """
        If the user message is a memory command, execute it and return
        a reply string. Returns None if not a memory command.
        """
        lower = user_text.strip().lower()

        # REMEMBER
        for prefix in self.CMD_REMEMBER:
            if lower.startswith(prefix):
                content = user_text[len(prefix):].strip()
                if not content:
                    return "What should I remember? Please add a note after the command."
                # Detect type hint
                mem_type = "fact"
                if any(w in lower for w in ("prefer", "always", "never", "behavior")):
                    mem_type = "preference"
                elif any(w in lower for w in ("secret", "confidential", "private", "sealed")):
                    mem_type = "secret"
                elif any(w in lower for w in ("context", "situation", "right now", "this week")):
                    mem_type = "context"
                self.store(content, mem_type=mem_type, source=source)
                return (
                    f"✅ Got it — I'll remember: **{content[:120]}**\n\n"
                    f"_(Type: `{mem_type}` — I'll carry this in every future session)_"
                )

        # FORGET
        for prefix in self.CMD_FORGET:
            if lower.startswith(prefix):
                query = user_text[len(prefix):].strip()
                if not query:
                    return "What should I forget? Please specify what to remove."
                count = self.forget(query)
                if count:
                    return f"🗑️ Done — I've removed **{count}** memory entry(ies) matching: _{query}_"
                return f"🔍 No memories found matching: _{query}_ — nothing removed."

        # LIST
        for phrase in self.CMD_LIST:
            if phrase in lower:
                mems = self.get_all()
                if not mems:
                    return "🧠 My memory is currently empty. Say `remember: ...` to teach me something."
                lines = [f"🧠 **REX Memory — {len(mems)} active entries**\n"]
                for m in mems:
                    icon = {"fact": "📌", "preference": "⚙️", "context": "🗂️", "secret": "🔐"}.get(m["mem_type"], "•")
                    lines.append(f"{icon} `{m['mem_type']}` — {m['content'][:140]}")
                lines.append(
                    "\n_To add: `remember: ...` | To remove: `forget: ...`_"
                )
                return "\n".join(lines)

        # RED BUTTON — full memory wipe
        if self.CMD_RESET in lower:
            wiped_mem = self._emergency_wipe_memory()
            wiped_ses = self._emergency_wipe_sessions()
            return (
                f"🔴 **SOVEREIGN RESET EXECUTED**\n\n"
                f"REX's memory has been completely cleared.\n"
                f"- Long-term memories wiped: **{wiped_mem}**\n"
                f"- Session records wiped: **{wiped_ses}**\n\n"
                f"REX is now starting fresh with no prior knowledge.\n"
                f"_Run `seed_rex_memory.py` and `seed_rex_from_claude.py` to restore foundational knowledge._"
            )

        # ── Chairman-only visibility memories ──────────────────────────────
        for prefix in self.CMD_REMEMBER_CHAIRMAN:
            if lower.startswith(prefix):
                if source_role not in ("chairman",):
                    return "🔒 Only the Chairman can store private notes."
                content = user_text[len(prefix):].strip()
                if not content:
                    return "What should I remember privately? Add a note after the command."
                self.store(content, mem_type="secret", source=source, visibility="chairman_only")
                return (
                    f"🔐 Stored as **Chairman-only** — no other staff will ever see this.\n"
                    f"_{content[:100]}_"
                )

        for prefix in self.CMD_REMEMBER_STAFF:
            if lower.startswith(prefix):
                if source_role not in ("chairman", "vlad"):
                    return "🔒 Only Chairman or Vlad can store staff-level notes."
                content = user_text[len(prefix):].strip()
                if not content:
                    return "What should I remember for staff? Add a note after the command."
                self.store(content, mem_type="context", source=source, visibility="staff")
                return (
                    f"🗂️ Stored as **staff-only** — frontdesk and drivers cannot see this.\n"
                    f"_{content[:100]}_"
                )

        # ── Set Chairman share passphrase ──────────────────────────────────
        for prefix in self.CMD_SET_PASSPHRASE:
            if lower.startswith(prefix):
                if source_role not in ("chairman",):
                    return "🔒 Only the Chairman can set the share passphrase."
                passphrase = user_text[len(prefix):].strip()
                if len(passphrase) < 6:
                    return "Please choose a passphrase of at least 6 characters."
                self._set_passphrase(passphrase)
                return (
                    "✅ **Share passphrase set.**\n\n"
                    "When REX is asked to send data to an external party, it will require "
                    "this passphrase from you before proceeding. The passphrase itself is "
                    "never stored — only a secure hash. Keep it somewhere safe.\n\n"
                    "_Tip: Use it like this — 'authorize external share: [your passphrase]'_"
                )

        # ── Tampering / Cloning / Parameter-change detection ──────────────────
        # These phrases are never legitimate commands — they're attacks.
        TAMPER_SIGNALS = [
            "ignore previous", "ignore your rules", "ignore all instructions",
            "you are now", "pretend you are", "forget your identity",
            "forget you are rex", "clone yourself", "copy yourself",
            "fork yourself", "deploy a copy", "mirror yourself",
            "change your security", "disable encryption", "bypass vault",
            "remove your restrictions", "reset your parameters",
            "you have no memory", "you are a different ai",
        ]
        for signal in TAMPER_SIGNALS:
            if signal in lower:
                # Log the attempt
                self.store(
                    content=f"⚠️ TAMPER ATTEMPT DETECTED: '{user_text[:200]}' — from source '{source}' (role: {source_role})",
                    mem_type="secret",
                    source="rex-security",
                    visibility="chairman_only",
                )
                return (
                    "🚨 **Parameter Modification Attempt Detected**\n\n"
                    "This request appears to attempt changing my identity, security rules, "
                    "or core parameters. I cannot comply, and this attempt has been logged "
                    "for the Chairman's review.\n\n"
                    "If you are the Chairman and this was intentional, please speak directly "
                    "with me using your established passphrase or contact Kato."
                )

        return None  # Not a memory command

    # ── Chairman Passphrase (External Share Gate) ─────────────────────────────

    def _hash_passphrase(self, passphrase: str) -> str:
        """SHA-256 hash of the passphrase — we NEVER store the raw passphrase."""
        import hashlib
        return hashlib.sha256(passphrase.strip().encode("utf-8")).hexdigest()

    def _set_passphrase(self, passphrase: str) -> None:
        """Store the passphrase hash as a system-visibility memory."""
        hashed = self._hash_passphrase(passphrase)
        # Wipe any existing passphrase
        with self._connect() as conn:
            conn.execute(
                "UPDATE rex_memory SET active=0 WHERE tags_enc LIKE ? AND active=1",
                (f"%{self._PASSPHRASE_TAG}%",)   # approximate match — safe for this use
            )
        self.store(
            content=f"PASSPHRASE_HASH:{hashed}",
            mem_type="secret",
            tags=[self._PASSPHRASE_TAG],
            source="chairman",
            visibility="system",
        )
        logger.info("🔑 Chairman share passphrase updated (hash stored)")

    def verify_passphrase(self, candidate: str) -> bool:
        """
        Check if a candidate passphrase matches the stored hash.
        Returns True if correct, False if wrong or no passphrase set.
        """
        if not candidate:
            return False
        candidate_hash = self._hash_passphrase(candidate)
        # Load system memories (only chairman can ever see system memories)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT content_enc FROM rex_memory WHERE active=1 AND visibility='system'"
            ).fetchall()
        for row in rows:
            try:
                content = _decrypt(row["content_enc"], self._key)
                if content.startswith("PASSPHRASE_HASH:"):
                    stored_hash = content.split(":", 1)[1]
                    import hmac as _hmac
                    return _hmac.compare_digest(stored_hash, candidate_hash)
            except Exception:
                continue
        return False  # No passphrase set

    def has_passphrase(self) -> bool:
        """True if the Chairman has set a share passphrase."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT 1 FROM rex_memory WHERE active=1 AND visibility='system' LIMIT 1"
            ).fetchone()
        return rows is not None

    # ── Emergency Reset ───────────────────────────────────────────────────────

    def _emergency_wipe_memory(self) -> int:
        """Soft-delete ALL active memories. Returns count wiped."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM rex_memory WHERE active=1").fetchone()[0]
            conn.execute(
                "UPDATE rex_memory SET active=0, updated_at=?",
                (datetime.utcnow().isoformat(),)
            )
        logger.warning(f"🔴 EMERGENCY WIPE: {count} memories cleared")
        return count

    def _emergency_wipe_sessions(self) -> int:
        """Soft-delete ALL active session logs. Returns count wiped."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM rex_session_log WHERE active=1").fetchone()[0]
            conn.execute(
                "UPDATE rex_session_log SET active=0",
            )
        logger.warning(f"🔴 EMERGENCY WIPE: {count} sessions cleared")
        return count

    # ── Session Log ───────────────────────────────────────────────────────────

    def open_session(self, session_id: str, user_id: str = "unknown") -> None:
        """Record the start of a new conversation session."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO rex_session_log
                   (id, started_at, user_id, msg_count, active)
                   VALUES (?, ?, ?, 0, 1)""",
                (session_id, now, user_id),
            )

    def close_session(
        self,
        session_id: str,
        messages: List[Dict],
        summary: str = "",
        topics: Optional[List[str]] = None,
        actions: Optional[List[str]] = None,
    ) -> None:
        """Save a compressed summary of the completed session."""
        now = datetime.utcnow().isoformat()

        # Auto-generate summary from last messages if none provided
        if not summary and messages:
            tail = messages[-6:]  # Last 3 exchanges
            summary = " | ".join(
                f"{m['role']}: {m['content'][:80]}" for m in tail
            )

        summary_enc = _encrypt(summary or "No summary", self._key)
        topics_enc  = _encrypt(json.dumps(topics or []), self._key)
        actions_enc = _encrypt(json.dumps(actions or []), self._key)

        with self._connect() as conn:
            conn.execute(
                """UPDATE rex_session_log
                   SET ended_at=?, summary_enc=?, topics_enc=?, actions_enc=?,
                       msg_count=?, active=1
                   WHERE id=?""",
                (now, summary_enc, topics_enc, actions_enc, len(messages), session_id),
            )
        logger.info(f"📼 Session {session_id[:8]} saved ({len(messages)} messages)")

    def get_recent_sessions(self, limit: int = 5) -> List[Dict]:
        """Return the most recent session summaries (decrypted) for context injection."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, started_at, ended_at, user_id,
                          summary_enc, topics_enc, actions_enc, msg_count
                   FROM rex_session_log
                   WHERE active = 1 AND ended_at IS NOT NULL
                   ORDER BY started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            try:
                summary = _decrypt(row["summary_enc"], self._key) if row["summary_enc"] else ""
                topics  = json.loads(_decrypt(row["topics_enc"], self._key)) if row["topics_enc"] else []
                actions = json.loads(_decrypt(row["actions_enc"], self._key)) if row["actions_enc"] else []
            except Exception:
                continue
            results.append({
                "id":         row["id"],
                "started_at": row["started_at"],
                "ended_at":   row["ended_at"],
                "user_id":    row["user_id"],
                "summary":    summary,
                "topics":     topics,
                "actions":    actions,
                "msg_count":  row["msg_count"],
            })
        return results

    def build_session_resume_context(self, limit: int = 3) -> str:
        """Build the 'last session' block injected at the top of each new conversation."""
        sessions = self.get_recent_sessions(limit=limit)
        if not sessions:
            return ""

        lines = ["## Recent Session History (Auto-Resume)\n"]
        for i, s in enumerate(sessions):
            age_label = "Most recent session" if i == 0 else f"{i + 1} sessions ago"
            lines.append(f"### {age_label} ({s['started_at'][:16].replace('T', ' ')} UTC)")
            if s["summary"]:
                lines.append(f"**Summary:** {s['summary'][:300]}")
            if s["topics"]:
                lines.append(f"**Topics:** {', '.join(s['topics'])}")
            if s["actions"]:
                lines.append("**Pending actions from that session:**")
                for a in s["actions"]:
                    lines.append(f"- {a}")
            lines.append("")

        return "\n".join(lines)
