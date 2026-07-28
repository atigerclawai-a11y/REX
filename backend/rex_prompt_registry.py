#!/usr/bin/env python3
"""
REX — Prompt Registry Engine (rex_prompt_registry.py)
══════════════════════════════════════════════════════════════════════════════
Treats every operational prompt as a governed system asset.
No direct uncontrolled edits. No silent changes.

ARCHITECTURE:

  state/prompt_registry.json  — authoritative registry (all metadata)
  prompts/<category>/<name>.md — prompt content files
  prompts/versions/<id>/<ts>.md — immutable version snapshots
  data/vaults/prompt_edits.db  — pending edit queue (governed flow)

APPROVAL TIERS:

  Tier 1 (low risk):     Direct edit allowed. No staged review.
                         Content is written, hash updated, version bumped.
  Tier 2 (medium risk):  Kato acknowledge required via Telegram before applying.
                         Edit is staged for 24h. Kato can approve or reject.
  Tier 3 (governed):     Full governed flow: staged edit → Kato explicit approval
                         → version snapshot → apply. Affects: identity, governance,
                         ocr, cls, memory, override categories.
                         No edit is applied until approval received.

GOVERNED CATEGORIES (always Tier 3 minimum):
  identity, governance, ocr, cls, memory, override

VERSIONING:
  Every applied edit (any tier) creates a snapshot in prompts/versions/<id>/.
  Snapshot filename: <timestamp>_v<version>.md
  Rollback: restore snapshot content, bump version, notify.

ROLLBACK:
  registry.rollback(prompt_id, version) → restore that version's content
  Creates a new version snapshot of the restored content (chain preserved).

COMMANDS (Kato via Telegram or REX chat):
  "approve prompt edit <edit_id>"   → applies a staged edit
  "reject prompt edit <edit_id>"    → discards a staged edit
  "rollback prompt <id> to v<n>"    → restores version n
  "prompt status <id>"              → shows current prompt metadata
  "list prompts [category]"         → lists registry entries

Usage:
  from backend.rex_prompt_registry import PromptRegistry
  reg = PromptRegistry()
  entry = reg.get("rex-identity-v1")
  reg.stage_edit("rex-identity-v1", new_content="...", editor="chairman")
  reg.approve_edit("edit_abc123")
  reg.rollback("rex-identity-v1", version=1)
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("prompt_registry")

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE        = Path(__file__).parent.parent
REGISTRY_FILE = _BASE / "state" / "prompt_registry.json"
PROMPTS_DIR   = _BASE / "prompts"
VERSIONS_DIR  = _BASE / "prompts" / "versions"
EDITS_DB      = _BASE / "data" / "vaults" / "prompt_edits.db"
TG_CONFIG     = _BASE / "rex_rexxie_telegram_config.json"
AUDIT_LOG     = _BASE / "state" / "prompt_audit.log"
USAGE_DB      = _BASE / "data" / "vaults" / "prompt_usage.db"

VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
(_BASE / "data" / "vaults").mkdir(parents=True, exist_ok=True)
(_BASE / "state").mkdir(parents=True, exist_ok=True)

# ── Governed categories — always Tier 3 minimum ───────────────────────────────
GOVERNED_CATEGORIES = frozenset({
    "identity", "governance", "ocr", "cls", "memory", "override"
})

# ══════════════════════════════════════════════════════════════════════════════
# DIFF ENGINE — stdlib only, no external dependencies
# ══════════════════════════════════════════════════════════════════════════════

def _compute_diff(old_text: str, new_text: str, context_lines: int = 3) -> List[Dict]:
    """
    Compute a line-by-line diff between two strings using difflib.
    Returns a list of dicts:
      {"type": "context"|"added"|"removed", "line_no": int, "line": str}

    context_lines: how many unchanged lines to show around each change block.
    Uses unified diff internally then converts to our clean format.
    """
    import difflib

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    result: List[Dict] = []

    # Use SequenceMatcher for fine-grained line matching
    matcher  = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    opcodes  = matcher.get_opcodes()

    # Collect changed block ranges so we know where to emit context
    changed_blocks = [
        (i1, i2, j1, j2)
        for tag, i1, i2, j1, j2 in opcodes
        if tag != "equal"
    ]

    # Emit context + changed lines with surrounding context_lines
    emitted_old: set = set()
    emitted_new: set = set()

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            # Emit context lines near changes only
            lines_to_emit = []
            for idx in range(i1, i2):
                near = any(
                    (abs(idx - bi1) < context_lines or abs(idx - bi2) < context_lines)
                    for bi1, bi2, _, _ in changed_blocks
                )
                if near and idx not in emitted_old:
                    lines_to_emit.append(idx)
                    emitted_old.add(idx)
            for idx in lines_to_emit:
                result.append({
                    "type":    "context",
                    "line_no": idx + 1,
                    "line":    old_lines[idx],
                })
        elif tag in ("replace", "delete"):
            for idx in range(i1, i2):
                if idx not in emitted_old:
                    result.append({
                        "type":    "removed",
                        "line_no": idx + 1,
                        "line":    old_lines[idx],
                    })
                    emitted_old.add(idx)
        if tag in ("replace", "insert"):
            for idx in range(j1, j2):
                if idx not in emitted_new:
                    result.append({
                        "type":    "added",
                        "line_no": idx + 1,
                        "line":    new_lines[idx],
                    })
                    emitted_new.add(idx)

    return result


# Edit expiry for staged edits
TIER2_EXPIRE_HOURS     = 24
TIER3_EXPIRE_HOURS     = 72    # 3 days — governed edits need deliberate review
PROTECTED_MIN_HOURS    = 48    # PR-CF-3: protected prompts must stage for at least 48h
PROTECTED_EXPIRE_HOURS = 96    # PR-CF-3: 4-day window for protected prompt approvals


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PromptEntry:
    id:               str
    title:            str
    short_description: str
    owner:            str
    category:         str
    approval_tier:    int
    risk_level:       str
    status:           str           # active | inactive | archive
    version:          int
    last_updated:     str
    path:             str
    content_hash:     str = ""
    source_var:       Optional[str] = None
    source_file:      Optional[str] = None
    notes:            str = ""

    @property
    def is_governed(self) -> bool:
        return self.category in GOVERNED_CATEGORIES or self.approval_tier == 3

    @property
    def is_protected(self) -> bool:
        """True if this prompt carries the protected flag (PR-CF-3)."""
        return getattr(self, "_protected", False)

    @property
    def status_badge(self) -> Dict[str, str]:
        """
        PR-CF-1: Computed status badge for Command Center rendering.
        Returns label, color, and icon so the UI needs no badge logic of its own.

        badge = {
          "status_label":    "Active",
          "status_color":    "green",          # green | yellow | gray
          "risk_label":      "Critical",
          "risk_color":      "red",            # red | orange | yellow | green
          "risk_icon":       "🔴",
          "tier_label":      "Governed (T3)",
          "protected_label": "Protected",      # or ""
        }
        """
        status_map = {
            "active":   ("Active",   "green"),
            "inactive": ("Inactive", "yellow"),
            "archive":  ("Archived", "gray"),
        }
        risk_map = {
            "critical": ("Critical", "red",    "🔴"),
            "high":     ("High",     "orange", "🟠"),
            "medium":   ("Medium",   "yellow", "🟡"),
            "low":      ("Low",      "green",  "🟢"),
        }
        tier_map = {
            3: "Governed (T3)",
            2: "Reviewed (T2)",
            1: "Direct (T1)",
        }
        s_label, s_color     = status_map.get(self.status, (self.status.title(), "gray"))
        r_label, r_color, r_icon = risk_map.get(self.risk_level, ("Unknown", "gray", "⚪"))
        protected_label      = "Protected" if self.is_protected else ""

        return {
            "status_label":    s_label,
            "status_color":    s_color,
            "risk_label":      r_label,
            "risk_color":      r_color,
            "risk_icon":       r_icon,
            "tier_label":      tier_map.get(self.approval_tier, f"T{self.approval_tier}"),
            "protected_label": protected_label,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":                self.id,
            "title":             self.title,
            "short_description": self.short_description,
            "owner":             self.owner,
            "category":         self.category,
            "approval_tier":    self.approval_tier,
            "risk_level":       self.risk_level,
            "status":           self.status,
            "version":          self.version,
            "last_updated":     self.last_updated,
            "path":             self.path,
            "content_hash":     self.content_hash,
            "source_var":       self.source_var,
            "source_file":      self.source_file,
            "notes":            self.notes,
            "protected":        self.is_protected,   # PR-CF-3
            "badge":            self.status_badge,   # PR-CF-1
        }


@dataclass
class PendingEdit:
    edit_id:        str
    prompt_id:      str
    new_content:    str
    editor:         str
    reason:         str
    approval_tier:  int
    status:         str         # pending | approved | rejected | expired
    submitted_at:   str
    expires_at:     str
    decided_at:     Optional[str] = None
    applied_version: Optional[int] = None


# ══════════════════════════════════════════════════════════════════════════════
# EDITS DB (pending governed edits queue)
# ══════════════════════════════════════════════════════════════════════════════

class _EditStore:
    def __init__(self):
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(EDITS_DB))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_edits (
                    edit_id         TEXT PRIMARY KEY,
                    prompt_id       TEXT NOT NULL,
                    new_content     TEXT NOT NULL,
                    editor          TEXT NOT NULL,
                    reason          TEXT DEFAULT '',
                    approval_tier   INTEGER NOT NULL,
                    protected       INTEGER NOT NULL DEFAULT 0,
                    confirmed       INTEGER NOT NULL DEFAULT 0,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    submitted_at    TEXT NOT NULL,
                    earliest_apply  TEXT,
                    expires_at      TEXT NOT NULL,
                    decided_at      TEXT,
                    applied_version INTEGER
                )
            """)
            # Migrate: add columns to existing DB if absent
            for col, definition in [
                ("protected",      "INTEGER NOT NULL DEFAULT 0"),
                ("confirmed",      "INTEGER NOT NULL DEFAULT 0"),
                ("earliest_apply", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE pending_edits ADD COLUMN {col} {definition}")
                except Exception:
                    pass  # column already exists

    def submit(self, prompt_id: str, new_content: str, editor: str,
               reason: str, approval_tier: int, protected: bool = False) -> str:
        edit_id = str(uuid.uuid4())[:10]
        now     = _now_iso()
        if protected:
            hours = PROTECTED_EXPIRE_HOURS   # PR-CF-3: longer window + confirm required
        elif approval_tier == 2:
            hours = TIER2_EXPIRE_HOURS
        else:
            hours = TIER3_EXPIRE_HOURS
        expires = (_now_dt() + timedelta(hours=hours)).isoformat()
        earliest = (
            (_now_dt() + timedelta(hours=PROTECTED_MIN_HOURS)).isoformat()
            if protected else None
        )
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO pending_edits
                    (edit_id, prompt_id, new_content, editor, reason,
                     approval_tier, protected, confirmed, status,
                     submitted_at, earliest_apply, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?, ?, ?)
            """, (edit_id, prompt_id, new_content, editor, reason,
                  approval_tier, int(protected), now, earliest, expires))
        return edit_id

    def get(self, edit_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pending_edits WHERE edit_id = ?", (edit_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_status(self, edit_id: str, status: str,
                   applied_version: Optional[int] = None) -> None:
        now = _now_iso()
        with self._conn() as conn:
            conn.execute("""
                UPDATE pending_edits
                SET status = ?, decided_at = ?, applied_version = ?
                WHERE edit_id = ?
            """, (status, now, applied_version, edit_id))

    def list_pending(self, prompt_id: Optional[str] = None) -> List[Dict]:
        with self._conn() as conn:
            if prompt_id:
                rows = conn.execute(
                    "SELECT * FROM pending_edits WHERE status='pending' AND prompt_id=? ORDER BY submitted_at DESC",
                    (prompt_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM pending_edits WHERE status='pending' ORDER BY submitted_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def expire_stale(self) -> List[str]:
        now = _now_iso()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT edit_id FROM pending_edits WHERE status='pending' AND expires_at < ?",
                (now,)
            ).fetchall()
        expired = [r["edit_id"] for r in rows]
        for eid in expired:
            self.set_status(eid, "expired")
        return expired


# ══════════════════════════════════════════════════════════════════════════════
# PR-CF-2: USAGE STORE — tracks when each prompt is loaded
# ══════════════════════════════════════════════════════════════════════════════

class _UsageStore:
    """
    Lightweight usage log for prompt loading events.

    Schema: one row per usage event.
      prompt_id  — which prompt was loaded
      context    — where it was loaded: "chat" | "rexxie_mode" | "api_call" | "test" | ...
      role       — caller role: "chairman" | "staff" | "system"
      used_at    — ISO timestamp (UTC)

    Queried for:
      - aggregate load counts per prompt (identify unused prompts)
      - last-used timestamp per prompt (identify stale active prompts)
      - usage by context (understand where each prompt is consumed)
    """

    def __init__(self, db_path: Path = USAGE_DB):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_usage (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id  TEXT NOT NULL,
                    context    TEXT NOT NULL DEFAULT 'unknown',
                    role       TEXT NOT NULL DEFAULT 'unknown',
                    used_at    TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_prompt ON prompt_usage(prompt_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_used_at ON prompt_usage(used_at)")

    def record(self, prompt_id: str, context: str = "unknown", role: str = "unknown") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO prompt_usage (prompt_id, context, role, used_at) VALUES (?, ?, ?, ?)",
                (prompt_id, context, role, _now_iso())
            )

    def counts(self, days: int = 30) -> List[Dict]:
        """Total load count per prompt over the last N days, descending."""
        cutoff = (_now_dt() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT prompt_id,
                       COUNT(*) AS total_loads,
                       MAX(used_at) AS last_used,
                       COUNT(DISTINCT context) AS distinct_contexts
                FROM prompt_usage
                WHERE used_at >= ?
                GROUP BY prompt_id
                ORDER BY total_loads DESC
            """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]

    def for_prompt(self, prompt_id: str, limit: int = 50) -> List[Dict]:
        """Recent usage events for one prompt."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT context, role, used_at
                FROM prompt_usage
                WHERE prompt_id = ?
                ORDER BY used_at DESC
                LIMIT ?
            """, (prompt_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def never_used(self, all_ids: List[str], days: int = 30) -> List[str]:
        """Return prompt IDs from all_ids that have zero usage in the last N days."""
        cutoff = (_now_dt() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT DISTINCT prompt_id FROM prompt_usage WHERE used_at >= ?
            """, (cutoff,)).fetchall()
        used = {r["prompt_id"] for r in rows}
        return [pid for pid in all_ids if pid not in used]


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT REGISTRY ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class PromptRegistry:
    """
    Central registry for all REX/Rexxie operational prompts.

    Every prompt is a governed system asset:
      • Metadata tracked in state/prompt_registry.json
      • Content stored in prompts/<category>/<name>.md
      • Every applied edit creates an immutable version snapshot
      • Tier 3 prompts require explicit Kato approval before any edit lands
    """

    def __init__(self):
        self._store  = _EditStore()
        self._usage  = _UsageStore()   # PR-CF-2
        self._data   = self._load()

    # ── Registry I/O ──────────────────────────────────────────────────────────

    def _load(self) -> Dict:
        if not REGISTRY_FILE.exists():
            raise FileNotFoundError(
                f"Prompt registry not found at {REGISTRY_FILE}. "
                "Run setup to initialize."
            )
        return json.loads(REGISTRY_FILE.read_text())

    def _save(self) -> None:
        self._data["_updated"] = _now_iso()
        tmp = REGISTRY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.replace(REGISTRY_FILE)

    def _find_index(self, prompt_id: str) -> int:
        for i, p in enumerate(self._data["prompts"]):
            if p["id"] == prompt_id:
                return i
        return -1

    # ── Read operations ────────────────────────────────────────────────────────

    def get(self, prompt_id: str) -> Optional[PromptEntry]:
        idx = self._find_index(prompt_id)
        if idx < 0:
            return None
        return self._entry_from_dict(self._data["prompts"][idx])

    def list(
        self,
        category: Optional[str] = None,
        status:   Optional[str] = None,
        tier:     Optional[int] = None,
    ) -> List[PromptEntry]:
        results = []
        for p in self._data["prompts"]:
            if category and p["category"] != category:
                continue
            if status and p["status"] != status:
                continue
            if tier is not None and p["approval_tier"] != tier:
                continue
            results.append(self._entry_from_dict(p))
        return results

    def get_content(self, prompt_id: str, strip_header: bool = True) -> Optional[str]:
        """
        Read current prompt content from disk.
        By default strips YAML frontmatter so callers get clean body text.
        Pass strip_header=False to get the full file including frontmatter.
        """
        entry = self.get(prompt_id)
        if not entry:
            return None
        full_path = _BASE / entry.path
        if not full_path.exists():
            return None
        raw = full_path.read_text()
        return strip_frontmatter(raw) if strip_header else raw

    def list_versions(self, prompt_id: str) -> List[Dict]:
        """List all available version snapshots for a prompt."""
        ver_dir = VERSIONS_DIR / prompt_id
        if not ver_dir.exists():
            return []
        snapshots = []
        for f in sorted(ver_dir.glob("*.md")):
            snapshots.append({
                "filename":    f.name,
                "path":        str(f),
                "size":        f.stat().st_size,
                "modified_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            })
        return snapshots

    def get_version_content(self, prompt_id: str, version: int) -> Optional[str]:
        """Read content from a specific version snapshot."""
        ver_dir = VERSIONS_DIR / prompt_id
        if not ver_dir.exists():
            return None
        # Find snapshot matching v<version>
        for f in ver_dir.glob(f"*_v{version}.md"):
            return f.read_text()
        return None

    # ── PR-CF-2: Usage tracking ───────────────────────────────────────────────

    def track_usage(
        self,
        prompt_id: str,
        context:   str = "unknown",
        role:      str = "unknown",
    ) -> None:
        """
        Record that a prompt was loaded.
        Call this wherever a prompt's content is injected into a system prompt.

        context: "chat" | "rexxie_mode" | "api_call" | "nightly_brief" | "test" | ...
        role:    "chairman" | "staff" | "system"

        Usage example (in sovereign.py / build_system_prompt):
            from backend.rex_prompt_registry import PromptRegistry
            reg = PromptRegistry()
            reg.track_usage("rex-identity-v1", context="chat", role=caller_role)
        """
        entry = self.get(prompt_id)
        if not entry:
            log.warning("track_usage: unknown prompt_id '%s'", prompt_id)
            return
        if entry.status != "active":
            log.debug("track_usage: prompt '%s' is %s — still recording", prompt_id, entry.status)
        self._usage.record(prompt_id, context, role)

    def usage_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        PR-CF-2: Return usage counts for all tracked prompts over the last N days.
        Also identifies active prompts with zero recent usage (archive candidates).

        Returns:
          {
            "window_days": 30,
            "loaded": [
              {"prompt_id": "rex-identity-v1", "total_loads": 42,
               "last_used": "...", "distinct_contexts": 2}, ...
            ],
            "never_used": ["training-grok-tuesday-v1", ...],
            "never_used_count": 3,
          }
        """
        counts     = self._usage.counts(days=days)
        all_active = [e.id for e in self.list(status="active")]
        never      = self._usage.never_used(all_active, days=days)
        return {
            "window_days":    days,
            "loaded":         counts,
            "never_used":     never,
            "never_used_count": len(never),
        }

    def usage_for(self, prompt_id: str, limit: int = 50) -> Dict[str, Any]:
        """
        PR-CF-2: Return recent usage events for a single prompt.
        """
        entry  = self.get(prompt_id)
        if not entry:
            return {"ok": False, "error": f"Prompt '{prompt_id}' not found"}
        events = self._usage.for_prompt(prompt_id, limit=limit)
        return {
            "ok":       True,
            "prompt_id": prompt_id,
            "title":    entry.title,
            "events":   events,
            "count":    len(events),
        }

    # ── Edit flow ─────────────────────────────────────────────────────────────

    def stage_edit(
        self,
        prompt_id:   str,
        new_content: str,
        editor:      str = "chairman",
        reason:      str = "",
    ) -> Dict[str, Any]:
        """
        Stage a prompt edit.

        Tier 1: Applies immediately (direct write), no staging.
        Tier 2: Stages for up to 24h, notifies Kato, applies on approval.
        Tier 3: Stages for up to 72h, governed — must have explicit approval.

        Returns: {"ok": bool, "edit_id": str, "applied": bool, "message": str}
        """
        entry = self.get(prompt_id)
        if not entry:
            return {"ok": False, "error": f"Prompt '{prompt_id}' not found"}

        if entry.status == "archive":
            return {"ok": False, "error": f"Prompt '{prompt_id}' is archived. Restore it first."}

        # Enforce tier escalation for governed categories
        tier = entry.approval_tier
        if entry.category in GOVERNED_CATEGORIES and tier < 3:
            log.warning(
                "Prompt %s is in governed category '%s' but has tier %d — escalating to Tier 3",
                prompt_id, entry.category, tier
            )
            tier = 3

        # Tier 1: apply immediately
        if tier == 1:
            new_ver = self._apply_edit(prompt_id, new_content, editor, reason)
            return {
                "ok":      True,
                "applied": True,
                "tier":    1,
                "version": new_ver,
                "message": f"Applied immediately (Tier 1). Version is now v{new_ver}.",
            }

        # Phase 10: MSU session gate for protected prompts
        is_protected = entry.is_protected
        if is_protected:
            try:
                from backend.rex_session import SessionEngine
                eng   = SessionEngine()
                block = eng.require_unlocked()
                if block:
                    return {
                        **block,
                        "hint": (
                            "Protected prompt edits require an active MSU session. "
                            "Unlock via POST /api/chairman/session/unlock first."
                        ),
                    }
                eng.record_protected_activity()
            except ImportError:
                log.warning("rex_session not available — MSU gate bypassed with warning")
            except Exception as e:
                log.warning("MSU gate error: %s — proceeding (MSU degraded)", e)

        # Tier 2 / 3: stage it
        edit_id = self._store.submit(
            prompt_id, new_content, editor, reason, tier,
            protected=is_protected,    # PR-CF-3
        )
        self._write_audit(
            "edit_staged",
            edit_id      = edit_id,
            prompt_id    = prompt_id,
            title        = entry.title,
            tier         = tier,
            risk_level   = entry.risk_level,
            editor       = editor,
            reason       = reason[:200],
        )
        # Compute diff now so the Telegram notification can include a preview
        diff_result = self.diff(prompt_id, edit_id)
        self._notify_staged_edit(entry, edit_id, tier, reason, diff_result=diff_result)

        tier_msg = {
            2: "Staged for 24h. Reply 'approve prompt edit {eid}' to apply.",
            3: "Governed edit staged for 72h. Explicit approval required before any change lands.",
        }
        return {
            "ok":      True,
            "applied": False,
            "tier":    tier,
            "edit_id": edit_id,
            "message": tier_msg.get(tier, "Staged.").format(eid=edit_id),
        }

    def approve_edit(self, edit_id: str, approved_by: str = "chairman") -> Dict[str, Any]:
        """
        Apply a staged edit after approval.
        Returns a full payload: prompt metadata, diff preview, version change.

        PR-CF-3 — Protected prompt gates:
          1. Must have been staged for at least PROTECTED_MIN_HOURS (48h).
             If the minimum window has not passed, returns an error with time remaining.
          2. Must have been explicitly confirmed first via confirm_protected_edit().
             If not yet confirmed, returns an error and instructions.
        """
        rec = self._store.get(edit_id)
        if not rec:
            return {"ok": False, "error": f"Edit '{edit_id}' not found"}
        if rec["status"] != "pending":
            return {"ok": False, "error": f"Edit '{edit_id}' status={rec['status']} — cannot approve"}

        # Check expiry
        if _now_iso() > rec["expires_at"]:
            self._store.set_status(edit_id, "expired")
            self._write_audit("edit_expired", edit_id=edit_id, prompt_id=rec["prompt_id"])
            return {"ok": False, "error": f"Edit '{edit_id}' has expired"}

        # PR-CF-3: Protected prompt gates
        if rec.get("protected"):
            # Gate 1: 48h minimum staging window
            earliest = rec.get("earliest_apply")
            if earliest and _now_iso() < earliest:
                from datetime import datetime as _dt
                remaining = _dt.fromisoformat(earliest) - _now_dt()
                hours_left = int(remaining.total_seconds() / 3600)
                return {
                    "ok":    False,
                    "error": (
                        f"Protected prompt: minimum 48h staging window not yet elapsed. "
                        f"Earliest apply: {earliest[:16]} UTC (~{hours_left}h remaining). "
                        f"This is a safety hold — not a bug."
                    ),
                    "protected":     True,
                    "earliest_apply": earliest,
                    "hours_remaining": hours_left,
                }
            # Gate 2: second confirmation required
            if not rec.get("confirmed"):
                return {
                    "ok":    False,
                    "error": (
                        f"Protected prompt: second confirmation required before applying. "
                        f"Send: `confirm protected edit {edit_id}` to confirm, "
                        f"then approve again."
                    ),
                    "protected":      True,
                    "needs_confirm":  True,
                    "confirm_command": f"confirm protected edit {edit_id}",
                }

        entry = self.get(rec["prompt_id"])

        # Capture diff BEFORE applying (so old_content is still on disk)
        diff_result = self.diff(rec["prompt_id"], edit_id)
        diff_preview = diff_result.get("diff", [])[:20]  # first 20 diff lines for preview

        old_ver = entry.version if entry else 0
        new_ver = self._apply_edit(
            rec["prompt_id"],
            rec["new_content"],
            rec["editor"],
            rec["reason"],
        )
        self._store.set_status(edit_id, "approved", applied_version=new_ver)

        # Audit log
        self._write_audit(
            "edit_approved",
            edit_id      = edit_id,
            prompt_id    = rec["prompt_id"],
            title        = entry.title if entry else "",
            version_from = old_ver,
            version_to   = new_ver,
            approved_by  = approved_by,
            reason       = rec.get("reason", ""),
            risk_level   = entry.risk_level if entry else "",
            approval_tier = entry.approval_tier if entry else 0,
            diff_stats   = diff_result.get("stats", {}),
        )

        log.info(
            "Prompt edit approved: id=%s prompt=%s v%d→v%d by=%s",
            edit_id, rec["prompt_id"], old_ver, new_ver, approved_by
        )

        return {
            "ok":            True,
            "edit_id":       edit_id,
            "prompt_id":     rec["prompt_id"],
            "title":         entry.title if entry else "",
            "reason":        rec.get("reason", ""),
            "risk_level":    entry.risk_level if entry else "",
            "approval_tier": entry.approval_tier if entry else 0,
            "version_from":  old_ver,
            "version_to":    new_ver,
            "approved_by":   approved_by,
            "diff_preview":  diff_preview,
            "diff_stats":    diff_result.get("stats", {}),
            "message":       (
                f"✅ Edit applied. '{rec['prompt_id']}' v{old_ver} → v{new_ver}. "
                f"{diff_result.get('stats', {}).get('added', 0)} added, "
                f"{diff_result.get('stats', {}).get('removed', 0)} removed."
            ),
        }

    def reject_edit(self, edit_id: str, rejected_by: str = "chairman") -> Dict[str, Any]:
        """Reject a staged edit. No content change occurs. Writes audit entry."""
        rec = self._store.get(edit_id)
        if not rec:
            return {"ok": False, "error": f"Edit '{edit_id}' not found"}
        if rec["status"] != "pending":
            return {"ok": False, "error": f"Edit '{edit_id}' already decided"}
        self._store.set_status(edit_id, "rejected")
        self._write_audit(
            "edit_rejected",
            edit_id      = edit_id,
            prompt_id    = rec["prompt_id"],
            rejected_by  = rejected_by,
            reason       = rec.get("reason", ""),
        )
        log.info("Prompt edit rejected: id=%s prompt=%s", edit_id, rec["prompt_id"])
        return {"ok": True, "edit_id": edit_id, "status": "rejected",
                "message": f"Edit '{edit_id}' rejected. No change applied."}

    # ── Rollback ──────────────────────────────────────────────────────────────

    def rollback(self, prompt_id: str, version: int) -> Dict[str, Any]:
        """
        Restore a previous version of a prompt.
        Creates a new version snapshot of the restored content.
        This is itself a governed operation for Tier 3 prompts.
        """
        entry = self.get(prompt_id)
        if not entry:
            return {"ok": False, "error": f"Prompt '{prompt_id}' not found"}

        old_content = self.get_version_content(prompt_id, version)
        if old_content is None:
            return {"ok": False, "error": f"Version v{version} of '{prompt_id}' not found"}

        if entry.is_governed:
            # For governed prompts, rollback goes through the staging flow
            log.info(
                "Governed rollback staged: prompt=%s target_version=v%d",
                prompt_id, version
            )
            return self.stage_edit(
                prompt_id   = prompt_id,
                new_content = old_content,
                editor      = "chairman_rollback",
                reason      = f"Rollback to v{version}",
            )

        # Tier 1 prompts: apply directly
        new_ver = self._apply_edit(
            prompt_id,
            old_content,
            "chairman_rollback",
            f"Rollback to v{version}",
        )
        return {
            "ok":      True,
            "prompt":  prompt_id,
            "restored_version": version,
            "new_version":      new_ver,
            "message": f"'{prompt_id}' rolled back to v{version} content. New version is v{new_ver}.",
        }

    # ── Status management ─────────────────────────────────────────────────────

    def set_status(self, prompt_id: str, new_status: str) -> Dict[str, Any]:
        """Set prompt status: active | inactive | archive."""
        valid = {"active", "inactive", "archive"}
        if new_status not in valid:
            return {"ok": False, "error": f"Invalid status '{new_status}'. Valid: {valid}"}

        idx = self._find_index(prompt_id)
        if idx < 0:
            return {"ok": False, "error": f"Prompt '{prompt_id}' not found"}

        entry = self.get(prompt_id)
        if entry.is_governed and new_status == "archive":
            # Archiving a governed prompt requires staging through approve flow
            return self.stage_edit(
                prompt_id   = prompt_id,
                new_content = self.get_content(prompt_id) or "",
                editor      = "chairman",
                reason      = f"Request to archive governed prompt '{prompt_id}'",
            )

        old_status = self._data["prompts"][idx]["status"]
        self._data["prompts"][idx]["status"] = new_status
        self._data["prompts"][idx]["last_updated"] = _now_iso()
        self._save()

        log.info("Prompt status: %s → %s (%s)", prompt_id, new_status, old_status)
        return {"ok": True, "prompt": prompt_id, "old_status": old_status, "new_status": new_status}

    # ── Command parser (Telegram / REX chat) ──────────────────────────────────

    def confirm_protected_edit(self, edit_id: str) -> Dict[str, Any]:
        """
        PR-CF-3: Second-confirmation step for protected prompt edits.
        After calling this, approve_edit() will proceed (subject to 48h window).

        Kato command: "confirm protected edit <edit_id>"
        """
        rec = self._store.get(edit_id)
        if not rec:
            return {"ok": False, "error": f"Edit '{edit_id}' not found"}
        if rec["status"] != "pending":
            return {"ok": False, "error": f"Edit '{edit_id}' is not pending"}
        if not rec.get("protected"):
            return {"ok": False, "error": f"Edit '{edit_id}' is not a protected prompt edit"}
        if rec.get("confirmed"):
            return {"ok": True, "message": f"Edit '{edit_id}' already confirmed.", "confirmed": True}

        with self._store._conn() as conn:
            conn.execute(
                "UPDATE pending_edits SET confirmed = 1 WHERE edit_id = ?",
                (edit_id,)
            )

        earliest = rec.get("earliest_apply", "")
        self._write_audit(
            "protected_edit_confirmed",
            edit_id   = edit_id,
            prompt_id = rec["prompt_id"],
        )
        log.info("Protected edit confirmed: id=%s prompt=%s", edit_id, rec["prompt_id"])
        return {
            "ok":           True,
            "edit_id":      edit_id,
            "confirmed":    True,
            "earliest_apply": earliest,
            "message": (
                f"Confirmed. Edit '{edit_id}' is now approved once the 48h staging "
                f"window passes ({earliest[:16] if earliest else 'N/A'} UTC). "
                f"Then send: `approve prompt edit {edit_id}`"
            ),
        }

    def handle_kato_command(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse Kato's commands related to the Prompt Registry.

        Recognized:
          "approve prompt edit <edit_id>"
          "reject prompt edit <edit_id>"
          "rollback prompt <id> to v<n>"
          "prompt status <id>"
          "list prompts [category]"
          "list pending prompt edits"
        """
        t = text.strip().lower()

        if t.startswith("confirm protected edit "):
            eid = text.strip().split()[-1]
            return self.confirm_protected_edit(eid)

        if t.startswith("approve prompt edit "):
            eid = text.strip().split()[-1]
            return self.approve_edit(eid)

        if t.startswith("reject prompt edit "):
            eid = text.strip().split()[-1]
            return self.reject_edit(eid)

        if t.startswith("rollback prompt ") and " to v" in t:
            parts = text.strip().split()
            # "rollback prompt <id> to v<n>"
            try:
                prompt_id = parts[2]
                ver       = int(parts[-1].lstrip("vV"))
                return self.rollback(prompt_id, ver)
            except (IndexError, ValueError) as e:
                return {"ok": False, "error": f"Parse error: {e}. Usage: rollback prompt <id> to v<n>"}

        if t.startswith("prompt status "):
            pid   = text.strip().split(None, 2)[-1]
            entry = self.get(pid)
            if not entry:
                return {"ok": False, "error": f"Prompt '{pid}' not found"}
            return {
                "ok":    True,
                "entry": entry.to_dict(),
                "message": (
                    f"*{entry.title}* (v{entry.version})\n"
                    f"Status: {entry.status} | Tier: {entry.approval_tier} | Risk: {entry.risk_level}\n"
                    f"Path: {entry.path}\n"
                    f"Last updated: {entry.last_updated[:10]}"
                ),
            }

        if t.startswith("list prompts"):
            parts = t.split()
            cat   = parts[2] if len(parts) > 2 else None
            entries = self.list(category=cat, status="active")
            lines = [f"*Prompt Registry — {cat or 'all'} ({len(entries)} active)*\n"]
            for e in entries:
                lines.append(
                    f"• `{e.id}` [T{e.approval_tier}/{e.risk_level}] — {e.title}"
                )
            return {"ok": True, "message": "\n".join(lines)}

        if t in ("list pending prompt edits", "pending prompt edits", "prompt edits"):
            pending = self._store.list_pending()
            if not pending:
                return {"ok": True, "message": "No pending prompt edits."}
            lines = [f"*Pending prompt edits: {len(pending)}*\n"]
            for p in pending:
                lines.append(
                    f"• `{p['edit_id']}` → `{p['prompt_id']}` "
                    f"(T{p['approval_tier']}, expires {p['expires_at'][:10]})\n"
                    f"  Approve: `approve prompt edit {p['edit_id']}`"
                )
            return {"ok": True, "message": "\n".join(lines)}

        # PR-CF-2: usage commands (check specific forms first)
        if t in ("prompt usage summary", "usage summary", "prompt usage"):
            return {"ok": True, **self.usage_summary()}

        if t.startswith("prompt usage "):
            pid = text.strip().split(None, 2)[-1]
            return self.usage_for(pid)

        return None

    # ── Diff ─────────────────────────────────────────────────────────────────

    def diff(self, prompt_id: str, edit_id: str) -> Dict[str, Any]:
        """
        Return a line-by-line diff between the current prompt content and a
        staged edit. No files are modified.

        Output format:
          {
            "ok": true,
            "title": "REX Core Identity",
            "prompt_id": "rex-identity-v1",
            "edit_id": "abc123",
            "old_version": 4,
            "new_version": 5,          # current_version + 1 (not yet applied)
            "risk_level": "critical",
            "approval_tier": 3,
            "reason": "Clarify disclosure rule",
            "diff": [
              {"type": "context",  "line_no": 1,  "line": "# You are REX..."},
              {"type": "removed",  "line_no": 3,  "line": "REX may disclose..."},
              {"type": "added",    "line_no": 3,  "line": "REX must never disclose..."},
              ...
            ],
            "stats": {"added": 1, "removed": 1, "unchanged": 64}
          }
        """
        entry = self.get(prompt_id)
        if not entry:
            return {"ok": False, "error": f"Prompt '{prompt_id}' not found"}

        rec = self._store.get(edit_id)
        if not rec:
            return {"ok": False, "error": f"Edit '{edit_id}' not found"}
        if rec["prompt_id"] != prompt_id:
            return {"ok": False, "error": f"Edit '{edit_id}' belongs to '{rec['prompt_id']}', not '{prompt_id}'"}

        old_content = self.get_content(prompt_id) or ""
        new_content = rec["new_content"]

        diff_lines = _compute_diff(old_content, new_content)

        added    = sum(1 for d in diff_lines if d["type"] == "added")
        removed  = sum(1 for d in diff_lines if d["type"] == "removed")
        context  = sum(1 for d in diff_lines if d["type"] == "context")

        return {
            "ok":            True,
            "title":         entry.title,
            "prompt_id":     prompt_id,
            "edit_id":       edit_id,
            "old_version":   entry.version,
            "new_version":   entry.version + 1,
            "risk_level":    entry.risk_level,
            "approval_tier": entry.approval_tier,
            "reason":        rec.get("reason", ""),
            "editor":        rec.get("editor", ""),
            "submitted_at":  rec.get("submitted_at", ""),
            "expires_at":    rec.get("expires_at", ""),
            "diff":          diff_lines,
            "stats": {
                "added":     added,
                "removed":   removed,
                "unchanged": context,
                "total_lines": added + removed + context,
            },
        }

    # ── Audit log ─────────────────────────────────────────────────────────────

    def _write_audit(self, event: str, **kwargs) -> None:
        """
        Append one JSON line to state/prompt_audit.log.

        Every entry includes: event, timestamp, and any kwargs passed.
        This is append-only — never read by the engine, only by humans / tooling.
        """
        entry = {
            "event":     event,
            "timestamp": _now_iso(),
            **kwargs,
        }
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Audit log write failed: %s", e)

    def get_audit_log(self, limit: int = 50, prompt_id: Optional[str] = None) -> List[Dict]:
        """
        Read recent audit log entries. Most-recent-first.
        Optionally filter by prompt_id.
        """
        if not AUDIT_LOG.exists():
            return []
        try:
            lines = AUDIT_LOG.read_text().splitlines()
            entries = []
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if prompt_id and entry.get("prompt_id") != prompt_id:
                        continue
                    entries.append(entry)
                    if len(entries) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
            return entries
        except Exception as e:
            log.error("Audit log read failed: %s", e)
            return []

    # ── Internal ──────────────────────────────────────────────────────────────

    def _apply_edit(
        self,
        prompt_id:   str,
        new_content: str,
        editor:      str,
        reason:      str,
    ) -> int:
        """
        Write new content to disk, create version snapshot, update registry.
        Returns the new version number.
        """
        idx = self._find_index(prompt_id)
        if idx < 0:
            raise ValueError(f"Prompt '{prompt_id}' not found in registry")

        record       = self._data["prompts"][idx]
        current_ver  = record["version"]
        new_ver      = current_ver + 1
        full_path    = _BASE / record["path"]

        # 1. Snapshot current content BEFORE overwriting
        if full_path.exists():
            ver_dir = VERSIONS_DIR / prompt_id
            ver_dir.mkdir(parents=True, exist_ok=True)
            ts         = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            snap_name  = f"{ts}_v{current_ver}.md"
            shutil.copy2(full_path, ver_dir / snap_name)
            log.info("Snapshot: %s → %s", prompt_id, snap_name)

        # 2. Write new content with updated frontmatter
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # Strip any existing frontmatter from the incoming content,
        # then prepend a fresh frontmatter block with the new version number.
        body_content = strip_frontmatter(new_content)
        fresh_header = (
            f"---\n"
            f"id: {record['id']}\n"
            f"version: {new_ver}\n"
            f"approval_tier: {record['approval_tier']}\n"
            f"risk_level: {record['risk_level']}\n"
            f"category: {record['category']}\n"
            f"owner: {record['owner']}\n"
            f"last_updated: {_now_iso()[:10]}\n"
            f"---\n\n"
        )
        full_path.write_text(fresh_header + body_content)

        # 3. Update registry record
        new_hash = hashlib.sha256(new_content.encode()).hexdigest()[:16]
        record["version"]      = new_ver
        record["last_updated"] = _now_iso()
        record["content_hash"] = new_hash
        self._data["prompts"][idx] = record
        self._save()

        log.info(
            "Prompt edit applied: id=%s version=%d→%d editor=%s reason=%s",
            prompt_id, current_ver, new_ver, editor, reason[:60]
        )

        # ── Audit log ────────────────────────────────────────────────────────
        self._write_audit(
            "edit_applied",
            prompt_id    = prompt_id,
            version_from = current_ver,
            version_to   = new_ver,
            editor       = editor,
            reason       = reason[:200],
            snapshot     = snap_name if full_path.exists() else None,
        )

        return new_ver

    def _notify_staged_edit(
        self,
        entry:       PromptEntry,
        edit_id:     str,
        tier:        int,
        reason:      str,
        diff_result: Optional[Dict] = None,
    ) -> None:
        """
        Send Telegram notification to Kato about a staged prompt edit.
        Includes a compact diff preview so Kato can see what changed before approving.
        """
        try:
            import urllib.request
            if not TG_CONFIG.exists():
                log.warning("TG config missing — skipping prompt edit notification")
                return

            cfg     = json.loads(TG_CONFIG.read_text())
            token   = cfg.get("bot_token", "")
            chat_id = cfg.get("owner_chat_id") or cfg.get("chairman_chat_id") or ""

            if not token or not chat_id:
                return

            tier_label = {
                2: "⚠️ Medium-risk",
                3: "🔴 GOVERNED — explicit approval required",
            }.get(tier, "")

            # Build compact diff preview (removals and additions only, max 8 lines)
            diff_block = ""
            if diff_result and diff_result.get("ok"):
                stats  = diff_result.get("stats", {})
                lines  = diff_result.get("diff", [])
                changes = [d for d in lines if d["type"] in ("removed", "added")][:8]
                if changes:
                    diff_lines = []
                    for d in changes:
                        prefix = "−" if d["type"] == "removed" else "+"
                        diff_lines.append(f"`{prefix} {d['line'][:70]}`")
                    diff_block = (
                        f"\n\n*Changes preview* "
                        f"(+{stats.get('added',0)} −{stats.get('removed',0)}):\n"
                        + "\n".join(diff_lines)
                    )
                    if len([d for d in lines if d["type"] in ("removed","added")]) > 8:
                        diff_block += "\n_(and more...)_"

            msg = (
                f"📝 *Prompt Edit Staged*\n\n"
                f"*{entry.title}*\n"
                f"`{entry.id}` | v{entry.version} → v{entry.version + 1}\n"
                f"Category: {entry.category} | Risk: `{entry.risk_level}`\n"
                f"Tier: {tier} {tier_label}\n"
                f"Reason: _{reason or '(none given)'}_\n"
                f"Edit ID: `{edit_id}`"
                f"{diff_block}\n\n"
                f"✅ `approve prompt edit {edit_id}`\n"
                f"❌ `reject prompt edit {edit_id}`\n"
                f"🔍 `prompt diff {entry.id} {edit_id}`\n"
                f"_(No change applied yet)_"
            )

            payload = json.dumps({
                "chat_id":    chat_id,
                "text":       msg,
                "parse_mode": "Markdown",
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    log.info("Kato notified: staged edit %s for prompt %s", edit_id, entry.id)
        except Exception as e:
            log.error("Notification failed for staged edit %s: %s", edit_id, e)

    @staticmethod
    def _entry_from_dict(d: Dict) -> "PromptEntry":
        e = PromptEntry(
            id                = d["id"],
            title             = d["title"],
            short_description = d["short_description"],
            owner             = d["owner"],
            category          = d["category"],
            approval_tier     = d["approval_tier"],
            risk_level        = d["risk_level"],
            status            = d["status"],
            version           = d["version"],
            last_updated      = d["last_updated"],
            path              = d["path"],
            content_hash      = d.get("content_hash", ""),
            source_var        = d.get("source_var"),
            source_file       = d.get("source_file"),
            notes             = d.get("notes", ""),
        )
        # PR-CF-3: carry through the protected flag from the registry JSON
        object.__setattr__(e, "_protected", bool(d.get("protected", False)))
        return e

    # ── Maintenance ───────────────────────────────────────────────────────────

    def expire_stale_edits(self) -> List[str]:
        """Expire all overdue pending edits."""
        expired = self._store.expire_stale()
        if expired:
            log.info("Expired %d stale prompt edit(s): %s", len(expired), expired)
        return expired

    def integrity_check(self) -> Dict[str, Any]:
        """
        Verify content hashes for all active prompts match files on disk.
        Returns a report of any mismatches.
        """
        mismatches = []
        missing    = []
        ok         = []

        for entry in self.list(status="active"):
            full_path = _BASE / entry.path
            if not full_path.exists():
                missing.append(entry.id)
                continue
            # Hash body-only (ignore frontmatter) so version bumps don't create false mismatches
            body = strip_frontmatter(full_path.read_text())
            actual_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
            if actual_hash != entry.content_hash:
                mismatches.append({
                    "id":       entry.id,
                    "expected": entry.content_hash,
                    "actual":   actual_hash,
                })
            else:
                ok.append(entry.id)

        return {
            "checked_at":  _now_iso(),
            "total":       len(ok) + len(mismatches) + len(missing),
            "ok":          len(ok),
            "mismatches":  mismatches,
            "missing":     missing,
            "clean":       len(mismatches) == 0 and len(missing) == 0,
        }

    def summary(self) -> Dict[str, Any]:
        """Return a non-destructive dashboard summary including PR-CF-1 badge rollup."""
        all_entries   = self.list()
        by_cat        = {}
        by_tier       = {}
        by_risk       = {}
        by_status     = {}
        badge_rollup  = {}   # PR-CF-1: risk_color → count for dashboard heat map

        for e in all_entries:
            by_cat[e.category]           = by_cat.get(e.category, 0) + 1
            by_tier[e.approval_tier]     = by_tier.get(e.approval_tier, 0) + 1
            by_risk[e.risk_level]        = by_risk.get(e.risk_level, 0) + 1
            by_status[e.status]          = by_status.get(e.status, 0) + 1
            color = e.status_badge["risk_color"]
            badge_rollup[color]          = badge_rollup.get(color, 0) + 1

        pending_edits  = self._store.list_pending()
        protected_list = [e.id for e in all_entries if e.is_protected]

        return {
            "generated_at":    _now_iso(),
            "total_prompts":   len(all_entries),
            "by_category":     by_cat,
            "by_tier":         by_tier,
            "by_risk":         by_risk,
            "by_status":       by_status,
            "pending_edits":   len(pending_edits),
            "governed_count":  sum(1 for e in all_entries if e.is_governed),
            "protected_count": len(protected_list),          # PR-CF-3
            "protected_ids":   protected_list,               # PR-CF-3
            "badge_rollup":    badge_rollup,                 # PR-CF-1: {"red":4,"orange":3,...}
        }


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def strip_frontmatter(text: str) -> str:
    """
    Remove YAML frontmatter block (--- ... ---) from the top of a prompt file.
    Returns the body content only. Safe to call on files without frontmatter.
    This is used so that content diffs and comparisons ignore the metadata header.
    """
    if not text.startswith("---"):
        return text
    # Find the closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return text   # malformed frontmatter — return as-is
    # Skip past the closing --- and any trailing newline
    body_start = end + 4   # len("\n---") == 4
    while body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    return text[body_start:]


def read_frontmatter(text: str) -> Dict[str, str]:
    """
    Parse the YAML frontmatter block from a prompt file.
    Returns a dict of key: value pairs (all strings).
    Returns {} if no frontmatter found.
    Simple line-by-line parser — no PyYAML dependency needed.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    header = text[3:end].strip()
    result = {}
    for line in header.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result
