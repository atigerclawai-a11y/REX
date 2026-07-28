#!/usr/bin/env python3
"""
CC_rex_memory.py — REX perpetual memory / knowledge layer.

Local-only memory store on rex_memory.db. REX ACCUMULATES wisdom:
  • after each answered question, the Q&A is stored as a memory,
  • an explicit "remember: <X>" message stores a lesson,
  • recall() feeds the most-relevant memories back into the next answer.

HARD RULES (GHS canon / Directive 4):
  • PHI-bearing memories (client specifics) are scope='goj' and stay LOCAL.
  • Ranking is lexical-first (keyword + recency + importance) so recall NEVER
    depends on a cloud call. Optional embeddings use the LOCAL Ollama model only.
  • Kato-private memories (scope='kato') are never surfaced to staff/partner.

Schema (extends the original session_memory table, kept intact):
  memories(
    id, kind['fact'|'qa'|'lesson'|'preference'],
    scope['global'|'goj'|'kato'],
    text, source, created_at, importance
  )

CLI:
  python3 CC_rex_memory.py --selftest
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ── Configuration ───────────────────────────────────────────────────────────
DB_PATH = Path.home() / "Desktop" / "REX" / "rex_memory.db"
OLLAMA_BASE = "http://127.0.0.1:11434"          # LOCAL model only — never cloud
OLLAMA_EMBED_MODEL = "qwen3.5:9b"               # used only if embeddings requested

VALID_KINDS = {"fact", "qa", "lesson", "preference"}
VALID_SCOPES = {"global", "goj", "kato"}

# Recency half-life: importance of recency decays over ~30 days.
_RECENCY_HALFLIFE_DAYS = 30.0
# Stopwords stripped from queries/memory text before keyword overlap scoring.
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on", "for",
    "and", "or", "do", "does", "did", "i", "you", "we", "they", "it", "this",
    "that", "what", "who", "when", "where", "how", "why", "with", "at", "by",
    "be", "as", "from", "my", "our", "your", "their", "me", "us", "can", "will",
}


# ── DB bootstrap ────────────────────────────────────────────────────────────
def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create/upgrade schema. Idempotent. Preserves legacy session_memory."""
    con = _connect()
    try:
        # Legacy table kept intact for backward compatibility.
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS session_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL DEFAULT 'fact',
                scope TEXT NOT NULL DEFAULT 'global',
                text TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                importance REAL NOT NULL DEFAULT 1.0
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(scope)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mem_kind ON memories(kind)")
        con.commit()
    finally:
        con.close()


# ── Tokenization / ranking helpers ──────────────────────────────────────────
def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _recency_weight(created_at: str) -> float:
    """1.0 for now, decaying with a 30-day half-life. Robust to bad timestamps."""
    try:
        ts = created_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        if age_days < 0:
            age_days = 0.0
        return 0.5 ** (age_days / _RECENCY_HALFLIFE_DAYS)
    except Exception:
        return 0.5  # neutral middle weight on parse failure


def _keyword_score(query_tokens: set[str], mem_text: str) -> float:
    mem_tokens = _tokens(mem_text)
    if not query_tokens or not mem_tokens:
        return 0.0
    overlap = query_tokens & mem_tokens
    # Jaccard-ish but biased toward covering the query.
    return len(overlap) / max(1, len(query_tokens))


def _allowed_scopes(scope: str | Iterable[str] | None) -> set[str]:
    """
    Resolve the scope filter for recall.

    A string scope behaves as a TIER GATE (what the requester may see):
      'kato'   → kato + goj + global   (chairman: everything)
      'goj'    → goj + global          (partner: GOJ ops, no kato-private)
      'global' → global only           (staff: minimal, no PHI, no kato-private)
    An iterable scope is taken verbatim (explicit set).
    None → all scopes (internal/admin use only).
    """
    if scope is None:
        return set(VALID_SCOPES)
    if isinstance(scope, str):
        if scope == "kato":
            return {"kato", "goj", "global"}
        if scope == "goj":
            return {"goj", "global"}
        if scope == "global":
            return {"global"}
        return {scope}
    return {s for s in scope if s in VALID_SCOPES}


# ── Public API ──────────────────────────────────────────────────────────────
def remember(
    text: str,
    kind: str = "fact",
    scope: str = "global",
    source: str = "rex",
    importance: float = 1.0,
) -> int:
    """
    Store a memory. Returns the new row id.

    Dedupes exact (scope, normalized-text) collisions by bumping importance and
    refreshing created_at instead of inserting a duplicate.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("remember(): text is required")
    if kind not in VALID_KINDS:
        kind = "fact"
    if scope not in VALID_SCOPES:
        scope = "global"
    importance = max(0.1, min(10.0, float(importance)))

    init_db()
    con = _connect()
    try:
        norm = text.lower().strip()
        existing = con.execute(
            "SELECT id, importance FROM memories WHERE scope=? AND lower(trim(text))=?",
            (scope, norm),
        ).fetchone()
        if existing:
            new_imp = min(10.0, existing["importance"] + 0.5)
            con.execute(
                "UPDATE memories SET importance=?, created_at=datetime('now') WHERE id=?",
                (new_imp, existing["id"]),
            )
            con.commit()
            return int(existing["id"])
        cur = con.execute(
            "INSERT INTO memories(kind, scope, text, source, importance) VALUES (?,?,?,?,?)",
            (kind, scope, text, source, importance),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def remember_qa(question: str, answer: str, scope: str = "global", source: str = "rex-guide") -> int:
    """Convenience: store an answered Q&A pair as a 'qa' memory."""
    text = f"Q: {question.strip()}\nA: {answer.strip()}"
    return remember(text, kind="qa", scope=scope, source=source, importance=1.0)


def recall(query: str, scope: str | Iterable[str] | None = "global", k: int = 5,
           use_embeddings: bool = False) -> list[dict]:
    """
    Retrieve the k most-relevant memories.

    Ranking = keyword_overlap * 1.0  +  recency * 0.6  +  importance * 0.4
    `scope` acts as a TIER GATE (see _allowed_scopes): a staff request with
    scope='global' can NEVER pull goj (PHI) or kato-private memories.

    `use_embeddings=True` adds a LOCAL-only cosine bonus if Ollama answers; it
    is purely additive and degrades gracefully to lexical ranking on failure.
    """
    init_db()
    scopes = _allowed_scopes(scope)
    if not scopes:
        return []
    qtokens = _tokens(query)

    con = _connect()
    try:
        placeholders = ",".join("?" for _ in scopes)
        rows = con.execute(
            f"SELECT id, kind, scope, text, source, created_at, importance "
            f"FROM memories WHERE scope IN ({placeholders})",
            tuple(scopes),
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return []

    q_vec = _embed(query) if use_embeddings else None

    scored: list[tuple[float, dict]] = []
    for r in rows:
        kw = _keyword_score(qtokens, r["text"])
        rec = _recency_weight(r["created_at"])
        imp = min(1.0, r["importance"] / 5.0)  # normalize importance into 0..1-ish
        score = kw * 1.0 + rec * 0.6 + imp * 0.4
        if q_vec is not None:
            m_vec = _embed(r["text"])
            if m_vec is not None:
                score += _cosine(q_vec, m_vec) * 0.8
        scored.append(
            (
                score,
                {
                    "id": r["id"],
                    "kind": r["kind"],
                    "scope": r["scope"],
                    "text": r["text"],
                    "source": r["source"],
                    "created_at": r["created_at"],
                    "importance": r["importance"],
                    "score": round(score, 4),
                },
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[: max(1, k)]]


def recall_context(query: str, scope: str | Iterable[str] | None = "global", k: int = 5) -> str:
    """Render recalled memories as a compact context block for the local model."""
    mems = recall(query, scope=scope, k=k)
    if not mems:
        return ""
    lines = ["[REX remembers]:"]
    for m in mems:
        snippet = m["text"].replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        lines.append(f"  • ({m['kind']}) {snippet}")
    return "\n".join(lines)


def count(scope: str | Iterable[str] | None = None) -> int:
    init_db()
    scopes = _allowed_scopes(scope) if scope is not None else set(VALID_SCOPES)
    con = _connect()
    try:
        placeholders = ",".join("?" for _ in scopes)
        row = con.execute(
            f"SELECT COUNT(*) AS n FROM memories WHERE scope IN ({placeholders})",
            tuple(scopes),
        ).fetchone()
        return int(row["n"])
    finally:
        con.close()


# ── Optional LOCAL embeddings (never cloud) ─────────────────────────────────
def _embed(text: str) -> list[float] | None:
    try:
        body = json.dumps({"model": OLLAMA_EMBED_MODEL, "prompt": text}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/embeddings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            resp = json.loads(r.read())
        vec = resp.get("embedding")
        return vec if isinstance(vec, list) and vec else None
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Self-test ───────────────────────────────────────────────────────────────
def _selftest() -> int:
    print(f"[selftest] DB: {DB_PATH}")
    init_db()
    before = count()
    print(f"[selftest] memories before: {before}")

    remember("The center serves lunch at 12:30pm every weekday.",
             kind="fact", scope="global", source="selftest")
    remember("Garden of Joy clients sign IN only — there is no sign-out by design.",
             kind="lesson", scope="goj", source="selftest")
    remember("Kato prefers consolidated HTML reports, never JIRA.",
             kind="preference", scope="kato", source="selftest")

    after = count()
    print(f"[selftest] memories after: {after}  (grew by {after - before})")
    assert after >= before + 3, "memory did not grow"

    print("\n[selftest] recall('when is lunch served', scope=global, k=3):")
    res = recall("when is lunch served", scope="global", k=3)
    for m in res:
        print(f"   score={m['score']:<7} scope={m['scope']:<6} {m['text'][:60]}")
    assert res, "recall returned nothing"
    assert "lunch" in res[0]["text"].lower(), "ranking failed: top hit not the lunch fact"
    # staff scope must NOT surface goj/kato memories
    assert all(m["scope"] == "global" for m in res), "scope gate leaked PHI/private to staff"
    print("   ✓ top hit is the lunch fact; ✓ no goj/kato leakage at staff scope")

    print("\n[selftest] recall('sign in policy', scope=goj, k=3) [partner tier]:")
    res2 = recall("sign in policy", scope="goj", k=3)
    for m in res2:
        print(f"   score={m['score']:<7} scope={m['scope']:<6} {m['text'][:60]}")
    assert any("sign" in m["text"].lower() for m in res2), "goj recall failed"
    assert all(m["scope"] in ("goj", "global") for m in res2), "partner saw kato-private"
    print("   ✓ goj memory recalled; ✓ kato-private NOT surfaced to partner")

    print("\n[selftest] recall('report preference', scope=kato, k=3) [chairman tier]:")
    res3 = recall("report preference jira", scope="kato", k=3)
    for m in res3:
        print(f"   score={m['score']:<7} scope={m['scope']:<6} {m['text'][:60]}")
    assert any(m["scope"] == "kato" for m in res3), "chairman could not see kato-private"
    print("   ✓ chairman sees kato-private memory")

    print("\n[selftest] PASS — memory grows, ranking works, tier scope gate enforced.")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--remember" in sys.argv:
        i = sys.argv.index("--remember")
        txt = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        print("stored id:", remember(txt, kind="lesson", source="cli"))
    elif "--recall" in sys.argv:
        i = sys.argv.index("--recall")
        q = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        for m in recall(q, scope="global", k=5):
            print(f"{m['score']:<7} [{m['scope']}] {m['text'][:80]}")
    else:
        print(__doc__)
