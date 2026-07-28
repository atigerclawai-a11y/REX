#!/usr/bin/env python3
"""
rex_coordinator.py — Build Coordinator
=======================================
Reads master_list.json and provides:
  1. Component status queries
  2. Idea → component linking (which component does this idea belong to?)
  3. Adding progress notes to components
  4. Build health summary

Used by Rexxie to give Kato visibility into the full system build.
"""

import json
import sqlite3
import difflib
from pathlib import Path
from datetime import datetime

REX_DIR        = Path.home() / "Desktop" / "REX"
MASTER_LIST    = REX_DIR / "master_list.json"
GOJ_AUTH_DB    = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
COORDINATOR_DB = REX_DIR / "rex_coordinator.db"

# ── Load master list ──────────────────────────────────────────────────────────

def load_master_list() -> dict:
    if not MASTER_LIST.exists():
        return {}
    try:
        return json.loads(MASTER_LIST.read_text())
    except Exception:
        return {}


def get_components() -> list[dict]:
    return load_master_list().get("components", [])


def get_north_star() -> list[str]:
    return load_master_list().get("north_star", [])


def get_milestone() -> str:
    return load_master_list().get("current_milestone", "Unknown")

# ── Component matching ────────────────────────────────────────────────────────

def match_component(idea_text: str) -> dict | None:
    """
    Fuzzy-match an idea/message to the most relevant master list component.
    Uses keywords first, then falls back to name similarity.
    Returns the best matching component dict, or None.
    """
    components = get_components()
    if not components:
        return None

    idea_lower = idea_text.lower()
    best       = None
    best_score = 0

    for comp in components:
        score = 0
        # Keyword match (strongest signal)
        for kw in comp.get("keywords", []):
            if kw.lower() in idea_lower:
                score += 3
        # Name match
        name_sim = difflib.SequenceMatcher(None, idea_lower, comp["name"].lower()).ratio()
        score += name_sim * 2
        # Description match
        desc = comp.get("description", "")
        if any(w in idea_lower for w in desc.lower().split() if len(w) > 4):
            score += 1

        if score > best_score:
            best_score = score
            best = comp

    return best if best_score > 1 else None


# ── Coordinator DB ────────────────────────────────────────────────────────────

def _init_coordinator_db():
    """Create coordinator tables if not present."""
    con = sqlite3.connect(str(COORDINATOR_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS component_notes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            component_name TEXT NOT NULL,
            note           TEXT NOT NULL,
            source         TEXT DEFAULT 'rexxie',
            created_at     TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS idea_links (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_content   TEXT NOT NULL,
            component_name TEXT,
            match_score    REAL,
            linked_at      TEXT DEFAULT (datetime('now'))
        );
    """)
    con.commit()
    con.close()


def add_component_note(component_name: str, note: str, source: str = "rexxie"):
    """Add a progress note to a component."""
    _init_coordinator_db()
    con = sqlite3.connect(str(COORDINATOR_DB))
    con.execute(
        "INSERT INTO component_notes (component_name, note, source) VALUES (?, ?, ?)",
        (component_name, note[:500], source)
    )
    con.commit()
    con.close()


def link_idea_to_component(idea_content: str, component_name: str, score: float = 0.0):
    """Record that an idea was linked to a master list component."""
    _init_coordinator_db()
    con = sqlite3.connect(str(COORDINATOR_DB))
    con.execute(
        "INSERT INTO idea_links (idea_content, component_name, match_score) VALUES (?, ?, ?)",
        (idea_content[:500], component_name, score)
    )
    con.commit()
    con.close()


def get_component_notes(component_name: str = None) -> list[dict]:
    """Get recent notes for a component (or all components)."""
    _init_coordinator_db()
    con = sqlite3.connect(str(COORDINATOR_DB))
    if component_name:
        rows = con.execute(
            "SELECT component_name, note, source, created_at FROM component_notes WHERE component_name=? ORDER BY created_at DESC LIMIT 10",
            (component_name,)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT component_name, note, source, created_at FROM component_notes ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    con.close()
    return [{"component": r[0], "note": r[1], "source": r[2], "at": r[3]} for r in rows]


# ── Build status summaries ─────────────────────────────────────────────────────

STATUS_ICONS = {
    "working":  "🟢",
    "building": "🔨",
    "planned":  "📋",
    "paused":   "⏸",
    "blocked":  "🔴",
}

def build_status_summary(filter_status: str = None) -> str:
    """Return a formatted build status report."""
    components = get_components()
    if not components:
        return "⚠ master_list.json not found or empty."

    milestone = get_milestone()
    lines = [f"*Build Status — {milestone}*\n"]

    by_status = {}
    for comp in components:
        st = comp.get("status", "unknown")
        by_status.setdefault(st, []).append(comp)

    # Show in priority order
    for status_key in ("blocked", "building", "planned", "working", "paused"):
        if status_key not in by_status:
            continue
        if filter_status and status_key != filter_status:
            continue
        icon = STATUS_ICONS.get(status_key, "•")
        lines.append(f"\n*{icon} {status_key.upper()}*")
        for comp in by_status[status_key]:
            pct = comp.get("stage_percent", 0)
            name = comp["name"]
            cat  = comp.get("category", "")
            lines.append(f"  • {name}  [{pct}%] _{cat}_")
            if comp.get("next_missing_layer"):
                lines.append(f"    _→ {comp['next_missing_layer']}_")

    north_star = get_north_star()
    if north_star:
        lines.append(f"\n*🧭 North Star:*")
        for ns in north_star[:4]:
            lines.append(f"  • {ns}")

    return "\n".join(lines)


def what_needs_work() -> str:
    """Return components that are building or planned — the active work queue."""
    components = get_components()
    active = [c for c in components if c.get("status") in ("building", "planned")]
    if not active:
        return "✅ All components are working or complete."

    lines = ["*What still needs work:*\n"]
    for comp in active:
        icon = STATUS_ICONS.get(comp.get("status", ""), "•")
        lines.append(f"{icon} *{comp['name']}* [{comp.get('stage_percent', 0)}%]")
        if comp.get("build_goal"):
            lines.append(f"  Goal: {comp['build_goal']}")
        if comp.get("next_missing_layer"):
            lines.append(f"  Next: _{comp['next_missing_layer']}_")
    return "\n".join(lines)


def process_idea_through_coordinator(idea_content: str, idea_type: str) -> str | None:
    """
    Match an idea to the master build, link it, and return a brief summary.
    Returns None if no strong match found.
    """
    comp = match_component(idea_content)
    if not comp:
        return None
    link_idea_to_component(idea_content, comp["name"])
    return comp["name"]


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(build_status_summary())
    elif cmd == "todo":
        print(what_needs_work())
    elif cmd == "match" and len(sys.argv) > 2:
        idea = " ".join(sys.argv[2:])
        comp = match_component(idea)
        print(f"Best match: {comp['name'] if comp else 'no match'}")
