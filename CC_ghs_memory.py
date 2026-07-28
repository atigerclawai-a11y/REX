#!/usr/bin/env python3
"""
CC_ghs_memory.py — Persistent Memory & Knowledge for GHS Agents

Features:
- FTS5 conversation memory (survives restarts)
- Knowledge extraction — agents learn from every interaction
- Smart retrieval — inject relevant past context into LLM prompts
- Self-contained, zero external deps beyond stdlib

Usage:
    from CC_ghs_memory import GHSMemory
    mem = GHSMemory()
    mem.remember_message(chat_id, "user", "What beers do you have?")
    mem.remember_message(chat_id, "assistant", "We have 12 taps...")
    
    # Search past conversations
    context = mem.search_relevant(chat_id, "beer menu")
    
    # Extract and store knowledge
    mem.extract_knowledge(chat_id, "Kato prefers IPA beers")
"""

import sqlite3
import json
import time
import threading
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / "Desktop" / "REX" / "ghs_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,           -- 'user', 'assistant', 'masha', 'viktoriya', 'admin'
    agent TEXT NOT NULL,          -- 'masha', 'viktoriya', 'general'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    content,
    content=conversations,
    content_rowid=id
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,          -- 'masha', 'viktoriya', 'general'
    category TEXT NOT NULL,       -- 'preference', 'fact', 'procedure', 'update', 'question'
    key_text TEXT NOT NULL,       -- short identifier for dedup
    content TEXT NOT NULL,        -- the actual knowledge
    source_chat_id INTEGER,
    confidence REAL DEFAULT 0.7,
    times_recalled INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent, key_text)
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    key_text,
    content,
    content=knowledge,
    content_rowid=id
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
    INSERT INTO knowledge_fts(rowid, key_text, content) VALUES (new.id, new.key_text, new.content);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, key_text, content) VALUES ('delete', old.id, old.key_text, old.content);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, key_text, content) VALUES ('delete', old.id, old.key_text, old.content);
    INSERT INTO knowledge_fts(rowid, key_text, content) VALUES (new.id, new.key_text, new.content);
END;

CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversations(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_agent ON knowledge(agent, category);
CREATE INDEX IF NOT EXISTS idx_knowledge_recall ON knowledge(times_recalled);

-- Enable WAL for concurrent access
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
"""


class GHSMemory:
    """Thread-safe persistent memory for GHS agents."""
    
    def __init__(self, db_path: str | Path = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn
    
    def _init_db(self):
        """Initialize schema."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()
    
    # ═══════════════════════════════════════════════
    # Conversation Memory
    # ═══════════════════════════════════════════════
    
    def remember_message(self, chat_id: int, role: str, content: str, agent: str = "general"):
        """Store a conversation message."""
        if not content or not content.strip():
            return
        content = content.strip()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO conversations (chat_id, role, agent, content) VALUES (?, ?, ?, ?)",
            (chat_id, role, agent, content)
        )
        conn.commit()
    
    def get_recent_history(self, chat_id: int, limit: int = 20) -> list[dict]:
        """Get recent conversation history for a chat."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, agent, content, created_at FROM conversations "
            "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    
    def search_conversations(self, chat_id: int, query: str, limit: int = 5) -> list[dict]:
        """Full-text search past conversations."""
        conn = self._get_conn()
        # Sanitize FTS5 query
        safe_query = query.replace('"', '').replace("'", "")
        if not safe_query.strip():
            return []
        
        try:
            rows = conn.execute(
                "SELECT c.role, c.agent, c.content, c.created_at, "
                "fts.rank AS relevance "
                "FROM conversations_fts fts "
                "JOIN conversations c ON fts.rowid = c.id "
                "WHERE c.chat_id = ? AND conversations_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (chat_id, safe_query, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # FTS5 query syntax error — return empty
            return []
    
    # ═══════════════════════════════════════════════
    # Knowledge Base
    # ═══════════════════════════════════════════════
    
    def add_knowledge(self, agent: str, category: str, key_text: str, content: str,
                      chat_id: int = None, confidence: float = 0.7) -> bool:
        """Add a piece of knowledge. Returns False if duplicate."""
        if not key_text or not content:
            return False
        
        key_text = key_text.strip().lower()[:200]
        content = content.strip()
        
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO knowledge (agent, category, key_text, content, "
                "source_chat_id, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                (agent, category, key_text, content, chat_id, confidence)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Duplicate — update confidence
            conn.execute(
                "UPDATE knowledge SET confidence = MIN(1.0, confidence + 0.1), "
                "times_recalled = times_recalled + 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE agent = ? AND key_text = ?",
                (agent, key_text)
            )
            conn.commit()
            return False
    
    def search_knowledge(self, agent: str, query: str, limit: int = 5) -> list[dict]:
        """Search knowledge base — combine exact + FTS5."""
        conn = self._get_conn()
        results = []
        
        # 1. Exact key match first (for commands/known facts)
        exact = conn.execute(
            "SELECT * FROM knowledge WHERE agent = ? AND key_text = ?",
            (agent, query.strip().lower()[:200])
        ).fetchall()
        if exact:
            results.extend([dict(r) for r in exact])
        
        # 2. FTS5 fuzzy search
        safe_query = query.replace('"', '').replace("'", "")
        if safe_query.strip():
            try:
                fts_rows = conn.execute(
                    "SELECT k.*, fts.rank AS relevance "
                    "FROM knowledge_fts fts "
                    "JOIN knowledge k ON fts.rowid = k.id "
                    "WHERE k.agent = ? AND knowledge_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (agent, safe_query, limit)
                ).fetchall()
                for r in fts_rows:
                    d = dict(r)
                    if d['id'] not in {x['id'] for x in results}:
                        results.append(d)
            except sqlite3.OperationalError:
                pass
        
        # 3. If nothing found, try substring match on key_text
        if not results:
            fallback = conn.execute(
                "SELECT * FROM knowledge WHERE agent = ? AND "
                "(key_text LIKE ? OR content LIKE ?) "
                "ORDER BY times_recalled DESC, updated_at DESC LIMIT ?",
                (agent, f"%{safe_query}%", f"%{safe_query}%", limit)
            ).fetchall()
            results = [dict(r) for r in fallback]
        
        # Bump recall count
        for r in results[:3]:
            conn.execute(
                "UPDATE knowledge SET times_recalled = times_recalled + 1 WHERE id = ?",
                (r['id'],)
            )
        conn.commit()
        
        return results
    
    def get_all_knowledge(self, agent: str = None, category: str = None, limit: int = 50) -> list[dict]:
        """List knowledge entries."""
        conn = self._get_conn()
        if agent and category:
            rows = conn.execute(
                "SELECT * FROM knowledge WHERE agent = ? AND category = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (agent, category, limit)
            ).fetchall()
        elif agent:
            rows = conn.execute(
                "SELECT * FROM knowledge WHERE agent = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (agent, limit)
            ).fetchall()
        elif category:
            rows = conn.execute(
                "SELECT * FROM knowledge WHERE category = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    
    def delete_knowledge(self, key_text: str, agent: str = None):
        """Remove a knowledge entry."""
        conn = self._get_conn()
        if agent:
            conn.execute("DELETE FROM knowledge WHERE agent = ? AND key_text = ?", (agent, key_text))
        else:
            conn.execute("DELETE FROM knowledge WHERE key_text = ?", (key_text,))
        conn.commit()
    
    # ═══════════════════════════════════════════════
    # Smart Context Building
    # ═══════════════════════════════════════════════
    
    def build_context(self, chat_id: int, text: str, agent: str = "general",
                      max_history: int = 10, max_knowledge: int = 5) -> dict:
        """
        Build a rich context dict for LLM prompts.
        
        Returns: {
            'recent_messages': [...],
            'relevant_past': [...],
            'knowledge': [...],
            'key_facts': [...],
            'persona_context': '...'
        }
        """
        # Recent conversation
        recent = self.get_recent_history(chat_id, max_history)
        
        # Search past conversations for this topic
        relevant = self.search_conversations(chat_id, text, limit=3)
        
        # Search knowledge base
        knowledge = self.search_knowledge(agent, text, limit=max_knowledge)
        
        # Also search general knowledge
        general_knowledge = self.search_knowledge("general", text, limit=2)
        
        # Extract key words from the query for broader search
        import re
        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        key_terms = ' OR '.join(set(words[:5]))
        deep_knowledge = []
        if key_terms:
            deep_knowledge = self.search_knowledge(agent, key_terms, limit=3)
        
        # Deduplicate knowledge
        seen_ids = set()
        all_knowledge = []
        for k in knowledge + general_knowledge + deep_knowledge:
            if k['id'] not in seen_ids:
                seen_ids.add(k['id'])
                all_knowledge.append(k)
        
        return {
            'recent_messages': [f"{m['role']}: {m['content'][:200]}" for m in recent],
            'relevant_past': [f"[{m.get('created_at','')}] {m['role']}: {m['content'][:200]}" for m in relevant],
            'knowledge': [f"[{k['category']}] {k['content'][:300]}" for k in all_knowledge[:max_knowledge]],
            'key_facts': [k['content'] for k in all_knowledge if k['category'] in ('fact', 'preference', 'update')],
        }
    
    def format_context_for_prompt(self, context: dict, max_chars: int = 1500) -> str:
        """Format context dict into a string for LLM system prompt injection."""
        parts = []
        
        if context.get('key_facts'):
            facts = '\n'.join(f"  - {f}" for f in context['key_facts'][:5])
            parts.append(f"## Known Facts (from past conversations):\n{facts}")
        
        if context.get('knowledge'):
            kb = '\n'.join(f"  - {k}" for k in context['knowledge'][:5])
            parts.append(f"## Relevant Knowledge:\n{kb}")
        
        if context.get('relevant_past'):
            past = '\n'.join(f"  - {p}" for p in context['relevant_past'][:3])
            parts.append(f"## Related Past Conversations:\n{past}")
        
        result = '\n\n'.join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "..."
        return result
    
    # ═══════════════════════════════════════════════
    # Stats & Maintenance
    # ═══════════════════════════════════════════════
    
    def stats(self) -> dict:
        """Get memory stats."""
        conn = self._get_conn()
        return {
            'conversations': conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            'knowledge_entries': conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0],
            'knowledge_by_agent': {
                r['agent']: r['count']
                for r in conn.execute(
                    "SELECT agent, COUNT(*) as count FROM knowledge GROUP BY agent"
                ).fetchall()
            },
            'knowledge_by_category': {
                r['category']: r['count']
                for r in conn.execute(
                    "SELECT category, COUNT(*) as count FROM knowledge GROUP BY category"
                ).fetchall()
            },
            'db_size_mb': round(self.db_path.stat().st_size / 1024 / 1024, 2) if self.db_path.exists() else 0,
        }
    
    def prune_old_conversations(self, keep_days: int = 90):
        """Remove conversations older than N days."""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM conversations WHERE created_at < datetime('now', ?)",
            (f'-{keep_days} days',)
        )
        deleted = conn.total_changes
        conn.commit()
        return deleted


# ═══════════════════════════════════════════════
# Auto-Extraction: LLM learns from conversations
# ═══════════════════════════════════════════════

async def extract_knowledge_from_message(
    memory: GHSMemory,
    chat_id: int,
    agent: str,
    text: str,
    deepseek_key: str = None,
    deepseek_url: str = "https://api.deepseek.com/v1/chat/completions"
) -> list[dict]:
    """
    Use DeepSeek to extract knowledge facts from a user message.
    Returns list of extracted facts: [{agent, category, key_text, content}, ...]
    """
    if not deepseek_key or len(text) < 20:
        return []
    
    import httpx
    
    prompt = f"""Extract any useful knowledge from this message. Return a JSON array of facts.
Each fact should have: agent (masha/viktoriya/general), category (preference/fact/procedure/update/question), key_text (short unique ID), content (the full fact).

Message from {agent}: "{text}"

Categories:
- preference: user likes/dislikes/wants something
- fact: something factual learned (prices, schedules, names)
- procedure: how something is done
- update: something changed (hours, menu, policy)
- question: something the user asked that should be tracked

Only extract facts that would be useful to remember for FUTURE conversations. Skip trivial chat.
Return ONLY JSON array, no other text. Example:
[{{"agent": "masha", "category": "preference", "key_text": "kato prefers ipa", "content": "Kato prefers IPA beers over lagers"}}]
If nothing worth remembering, return []."""

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                deepseek_url,
                headers={
                    "Authorization": f"Bearer {deepseek_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "user", "content": prompt},
                        {"role": "user", "content": text}
                    ],
                    "max_tokens": 400,
                    "temperature": 0,
                },
            )
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            
            # Extract JSON
            import re
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                return []
            
            facts = json.loads(match.group())
            
            # Store each fact
            stored = []
            for fact in facts:
                if isinstance(fact, dict) and fact.get('content'):
                    is_new = memory.add_knowledge(
                        agent=fact.get('agent', agent),
                        category=fact.get('category', 'fact'),
                        key_text=fact.get('key_text', ''),
                        content=fact['content'],
                        chat_id=chat_id,
                    )
                    if is_new:
                        stored.append(fact)
            
            return stored
            
    except Exception:
        return []


# ═══════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════

_memory_instance = None

def get_memory() -> GHSMemory:
    """Get or create the singleton memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = GHSMemory()
    return _memory_instance


if __name__ == "__main__":
    # Quick test
    mem = GHSMemory()
    print("Memory stats:", json.dumps(mem.stats(), indent=2, default=str))
    
    # Test conversation memory
    mem.remember_message(5587703834, "user", "What beers are on tap?", "masha")
    mem.remember_message(5587703834, "assistant", "We have IPA, Stout, Pilsner, and Wheat", "masha")
    
    history = mem.get_recent_history(5587703834, 5)
    print(f"\nRecent history ({len(history)} msgs):")
    for h in history:
        print(f"  [{h['role']}] {h['content'][:60]}")
    
    # Test knowledge
    mem.add_knowledge("masha", "preference", "kato likes ipa", "Kato prefers IPA beers", 5587703834)
    mem.add_knowledge("masha", "fact", "bbg hours weekend", "BBG is open Sat & Sun 11:30AM-2AM", 5587703834)
    
    results = mem.search_knowledge("masha", "beer preferences")
    print(f"\nKnowledge search 'beer preferences': {len(results)} results")
    for r in results:
        print(f"  [{r['category']}] {r['content']}")
    
    # Test context building
    ctx = mem.build_context(5587703834, "what beers do you have", "masha")
    prompt_ctx = mem.format_context_for_prompt(ctx)
    print(f"\nContext for prompt ({len(prompt_ctx)} chars):")
    print(prompt_ctx[:500])
