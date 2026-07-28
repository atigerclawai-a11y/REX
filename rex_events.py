"""
rex_events.py — REX Structured Event System
════════════════════════════════════════════════════════════
Rexonasence v4 · Event Foundation · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  Provides a structured, append-only event log that captures every
  meaningful action across the REX/Rexxie system.

  Events flow from:
    • Document intake (OCR, filing)
    • Receipt upload, processing, approval
    • Permission changes
    • Telegram interactions (Rexxie + REX bots)
    • Governance hits (RBAC blocks, policy flags)
    • Unresolved item lifecycle (create / resurface / resolve)
    • Clarification routing
    • Security override attempts
    • System health changes

  Events are consumed by:
    • Chairman Command Center (activity trail, red flags)
    • Daily digest (9 PM)
    • Friday review (Telegram summary)
    • Future live/video clients (poll-based or webhook)
    • Any module that needs to read what happened without coupling

VISIBILITY CLASSES:
  chairman   — Chairman/Kato only. Never exposed to executive interface.
  financial  — chairman + admin_financial + finance
  operational — chairman + all admin roles
  all        — all authenticated users (no PII, no financial data)

EVENT TYPES (exhaustive list):
  # Receipt flow
  receipt.submitted      receipt.ocr_complete   receipt.flagged
  receipt.approved       receipt.rejected       receipt.deleted
  receipt.exported

  # Document / OCR
  doc.received           doc.classified         doc.filed
  doc.ambiguous          doc.low_confidence     doc.sent_for_review
  doc.ocr_fallback       doc.russian_text_found

  # Permissions
  perm.role_changed      perm.grant             perm.revoke
  perm.scope_grant       perm.scope_remove      perm.reset

  # Governance / security
  gov.rbac_blocked       gov.rbac_passed        gov.policy_blocked
  gov.behavior_flag      gov.override_attempt   gov.override_success
  gov.override_failure

  # Unresolved / clarification
  unresolved.created     unresolved.resurfaced  unresolved.resolved
  unresolved.escalated   clarification.routed   clarification.answered

  # System
  system.startup         system.shutdown        system.health_check
  system.backup          system.error

USAGE:
    from rex_events import write_event, read_events, EventType

    # Write:
    write_event(
        actor="misha",
        role="admin_operations",
        action=EventType.RECEIPT_SUBMITTED,
        entity="receipt_id=42",
        metadata={"vendor": "Costco", "amount": 87.50},
        visibility="financial",
    )

    # Read (Chairman Command Center):
    events = read_events(days=1, visibility="financial")

    # Read (red flags — CRITICAL/HIGH only):
    flags = read_events(days=7, sensitivity="high")
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Path ───────────────────────────────────────────────────────────────────────
EVENTS_DB = Path.home() / "Desktop" / "REX" / "data" / "rex_events.db"

# ── Visibility classes ────────────────────────────────────────────────────────
VISIBILITY_CLASSES = ("chairman", "financial", "operational", "all")

# Roles that can see each visibility class:
VISIBILITY_ROLES: dict[str, set[str]] = {
    "chairman":    {"chairman"},
    "financial":   {"chairman", "admin_financial", "finance"},
    "operational": {"chairman", "admin_financial", "finance", "admin_operations"},
    "all":         {"chairman", "admin_financial", "finance", "admin_operations", "staff", "viewer"},
}

# ── Sensitivity levels ────────────────────────────────────────────────────────
SENSITIVITY_LEVELS = ("critical", "high", "medium", "low", "info")

# ── Event type constants ──────────────────────────────────────────────────────
class EventType:
    # Receipt
    RECEIPT_SUBMITTED   = "receipt.submitted"
    RECEIPT_OCR_DONE    = "receipt.ocr_complete"
    RECEIPT_FLAGGED     = "receipt.flagged"
    RECEIPT_APPROVED    = "receipt.approved"
    RECEIPT_REJECTED    = "receipt.rejected"
    RECEIPT_DELETED     = "receipt.deleted"
    RECEIPT_EXPORTED    = "receipt.exported"

    # Document / OCR
    DOC_RECEIVED        = "doc.received"
    DOC_CLASSIFIED      = "doc.classified"
    DOC_FILED           = "doc.filed"
    DOC_AMBIGUOUS       = "doc.ambiguous"
    DOC_LOW_CONFIDENCE  = "doc.low_confidence"
    DOC_REVIEW_NEEDED   = "doc.sent_for_review"
    DOC_OCR_FALLBACK    = "doc.ocr_fallback"
    DOC_RUSSIAN_FOUND   = "doc.russian_text_found"

    # Content update pipeline
    CONTENT_UPDATE_STAGED    = "content.update_staged"
    CONTENT_UPDATE_APPROVED  = "content.update_approved"
    CONTENT_UPDATE_REJECTED  = "content.update_rejected"
    CONTENT_UPDATE_PUBLISHED = "content.update_published"

    # Permissions
    PERM_ROLE_CHANGED   = "perm.role_changed"
    PERM_GRANT          = "perm.grant"
    PERM_REVOKE         = "perm.revoke"
    PERM_SCOPE_GRANT    = "perm.scope_grant"
    PERM_SCOPE_REMOVE   = "perm.scope_remove"
    PERM_RESET          = "perm.reset"

    # Governance / security
    GOV_RBAC_BLOCKED    = "gov.rbac_blocked"
    GOV_RBAC_PASSED     = "gov.rbac_passed"
    GOV_POLICY_BLOCKED  = "gov.policy_blocked"
    GOV_BEHAVIOR_FLAG   = "gov.behavior_flag"
    GOV_OVERRIDE_ATTEMPT  = "gov.override_attempt"
    GOV_OVERRIDE_SUCCESS  = "gov.override_success"
    GOV_OVERRIDE_FAILURE  = "gov.override_failure"

    # Unresolved / clarification
    UNRESOLVED_CREATED  = "unresolved.created"
    UNRESOLVED_SURFACED = "unresolved.resurfaced"
    UNRESOLVED_RESOLVED = "unresolved.resolved"
    UNRESOLVED_ESCALATED= "unresolved.escalated"
    CLARIFICATION_ROUTED  = "clarification.routed"
    CLARIFICATION_ANSWERED= "clarification.answered"

    # System
    SYSTEM_STARTUP      = "system.startup"
    SYSTEM_SHUTDOWN     = "system.shutdown"
    SYSTEM_HEALTH_CHECK = "system.health_check"
    SYSTEM_BACKUP       = "system.backup"
    SYSTEM_ERROR        = "system.error"


# ── Event record ──────────────────────────────────────────────────────────────
@dataclass
class Event:
    """A structured event record."""
    action:      str                         # EventType constant
    actor:       str                         # Who triggered it (user_label or "system")
    role:        str                         # Actor's role at time of event
    entity:      str = ""                   # What entity was acted on (receipt_id=42, doc=foo.pdf)
    metadata:    dict = field(default_factory=dict)  # Event-specific data
    visibility:  str = "operational"        # Who can see this event
    sensitivity: str = "info"              # criticality: critical/high/medium/low/info
    ts:          str = field(default_factory=lambda: datetime.now().isoformat())
    event_id:    Optional[int] = None       # Set after DB insert


# ──────────────────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_db() -> None:
    EVENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(EVENTS_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            actor       TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT '',
            action      TEXT NOT NULL,
            entity      TEXT DEFAULT '',
            metadata    TEXT DEFAULT '{}',
            visibility  TEXT NOT NULL DEFAULT 'operational',
            sensitivity TEXT NOT NULL DEFAULT 'info'
        );

        CREATE INDEX IF NOT EXISTS idx_ev_ts         ON events(ts);
        CREATE INDEX IF NOT EXISTS idx_ev_action     ON events(action);
        CREATE INDEX IF NOT EXISTS idx_ev_actor      ON events(actor);
        CREATE INDEX IF NOT EXISTS idx_ev_visibility ON events(visibility);
        CREATE INDEX IF NOT EXISTS idx_ev_sensitivity ON events(sensitivity);
        CREATE INDEX IF NOT EXISTS idx_ev_entity     ON events(entity);
    """)
    con.commit()
    con.close()


_db_ready = False

def _db() -> None:
    global _db_ready
    if not _db_ready:
        _ensure_db()
        _db_ready = True


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def write_event(
    action:      str,
    actor:       str       = "system",
    role:        str       = "",
    entity:      str       = "",
    metadata:    dict      = None,
    visibility:  str       = "operational",
    sensitivity: str       = "info",
    ts:          str       = None,
) -> Optional[int]:
    """
    Write a structured event to the event log.
    Returns the inserted event ID, or None on failure (never raises).

    Args:
        action:      EventType constant (e.g. EventType.RECEIPT_SUBMITTED)
        actor:       Who triggered it (user_label: kato/vlad/misha/allen/system/rexxie)
        role:        Actor's role at time of event (auto-looked up if empty)
        entity:      What entity was acted on (e.g. "receipt_id=42", "doc=foo.pdf")
        metadata:    Dict of event-specific data (serialised to JSON)
        visibility:  "chairman" | "financial" | "operational" | "all"
        sensitivity: "critical" | "high" | "medium" | "low" | "info"
        ts:          ISO timestamp override (default: now)
    """
    _db()

    if metadata is None:
        metadata = {}

    # Validate visibility
    if visibility not in VISIBILITY_CLASSES:
        visibility = "operational"

    # Validate sensitivity
    if sensitivity not in SENSITIVITY_LEVELS:
        sensitivity = "info"

    # Auto-look up role if not provided
    if not role and actor not in ("system", "rexxie", "rex"):
        try:
            from rex_permissions import get_perms
            role = get_perms().get_role(actor)
        except Exception:
            role = ""

    try:
        con = sqlite3.connect(str(EVENTS_DB))
        cur = con.execute(
            "INSERT INTO events (ts, actor, role, action, entity, metadata, visibility, sensitivity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts or datetime.now().isoformat(),
                actor,
                role,
                action,
                entity,
                json.dumps(metadata, default=str),
                visibility,
                sensitivity,
            )
        )
        event_id = cur.lastrowid
        con.commit()
        con.close()
        return event_id
    except Exception as e:
        logger.error(f"[rex_events] write_event failed: {e}")
        return None


def read_events(
    days:        int       = 1,
    action:      str       = "",
    actor:       str       = "",
    entity:      str       = "",
    visibility:  str       = "",
    min_visibility_role: str = "",
    sensitivity: str       = "",
    limit:       int       = 500,
    offset:      int       = 0,
) -> list[dict]:
    """
    Read events from the log with optional filters.

    Args:
        days:               How many days back to look (default: 1)
        action:             Filter to specific action (or prefix, e.g. "receipt.")
        actor:              Filter to specific actor
        entity:             Filter to specific entity string
        visibility:         Exact visibility class to filter
        min_visibility_role: Show events visible to this role and above
                            (chairman sees all, staff sees only 'all')
        sensitivity:        Filter to specific sensitivity level
        limit:              Max rows (default: 500)
        offset:             Pagination offset

    Returns:
        List of event dicts, newest first.
    """
    _db()

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    clauses = ["ts >= ?"]
    params: list = [cutoff]

    if action:
        if action.endswith("."):
            clauses.append("action LIKE ?")
            params.append(f"{action}%")
        else:
            clauses.append("action = ?")
            params.append(action)

    if actor:
        clauses.append("actor = ?")
        params.append(actor)

    if entity:
        clauses.append("entity LIKE ?")
        params.append(f"%{entity}%")

    if visibility:
        clauses.append("visibility = ?")
        params.append(visibility)
    elif min_visibility_role:
        # Determine which visibility classes this role can see
        allowed_vis = [v for v, roles in VISIBILITY_ROLES.items()
                       if min_visibility_role in roles]
        if allowed_vis:
            placeholders = ",".join("?" * len(allowed_vis))
            clauses.append(f"visibility IN ({placeholders})")
            params.extend(allowed_vis)

    if sensitivity:
        clauses.append("sensitivity = ?")
        params.append(sensitivity)

    where = " AND ".join(clauses)

    try:
        con = sqlite3.connect(str(EVENTS_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"SELECT * FROM events WHERE {where} "
            f"ORDER BY ts DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()
        con.close()
    except Exception as e:
        logger.error(f"[rex_events] read_events failed: {e}")
        return []

    result = []
    for row in rows:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.get("metadata", "{}") or "{}")
        except Exception:
            d["metadata"] = {}
        result.append(d)
    return result


def read_red_flags(days: int = 7, limit: int = 100) -> list[dict]:
    """
    Return CRITICAL and HIGH sensitivity events from the last N days.
    Used by Chairman Command Center red-flags panel.
    """
    _db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        con = sqlite3.connect(str(EVENTS_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM events "
            "WHERE ts >= ? AND sensitivity IN ('critical', 'high') "
            "ORDER BY ts DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        con.close()
    except Exception as e:
        logger.error(f"[rex_events] read_red_flags failed: {e}")
        return []
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.get("metadata", "{}") or "{}")
        except Exception:
            d["metadata"] = {}
        result.append(d)
    return result


def read_activity_trail(
    days: int = 10,
    role: str = "chairman",
    limit: int = 200,
) -> list[dict]:
    """
    Return activity trail visible to a given role.
    Default: 10-day trail for Chairman (sees everything).
    """
    return read_events(days=days, min_visibility_role=role, limit=limit)


def event_summary(days: int = 1) -> dict:
    """
    Return a summary dict for the Chairman Command Center system health panel.
    {total, by_action_prefix, by_sensitivity, by_visibility, last_event_ts}
    """
    _db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        con = sqlite3.connect(str(EVENTS_DB))
        total = con.execute(
            "SELECT COUNT(*) FROM events WHERE ts >= ?", (cutoff,)
        ).fetchone()[0]

        by_sensitivity = {}
        for sev, in con.execute(
            "SELECT sensitivity, COUNT(*) FROM events WHERE ts >= ? GROUP BY sensitivity",
            (cutoff,)
        ).fetchall():
            pass
        by_sensitivity = dict(con.execute(
            "SELECT sensitivity, COUNT(*) FROM events WHERE ts >= ? GROUP BY sensitivity",
            (cutoff,)
        ).fetchall())

        by_action_prefix = dict(con.execute(
            "SELECT SUBSTR(action, 1, INSTR(action, '.')), COUNT(*) "
            "FROM events WHERE ts >= ? GROUP BY SUBSTR(action, 1, INSTR(action, '.'))",
            (cutoff,)
        ).fetchall())

        last_ts = con.execute(
            "SELECT MAX(ts) FROM events"
        ).fetchone()[0]

        con.close()
        return {
            "days": days,
            "total": total,
            "by_sensitivity": by_sensitivity,
            "by_action_prefix": by_action_prefix,
            "last_event_ts": last_ts,
        }
    except Exception as e:
        logger.error(f"[rex_events] event_summary failed: {e}")
        return {"days": days, "total": 0, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE WRAPPERS (thin helpers for common patterns)
# ──────────────────────────────────────────────────────────────────────────────

def gov_event(
    event_type: str,
    actor: str,
    detail: str = "",
    sensitivity: str = "high",
) -> None:
    """Write a governance event. Used to bridge governance_log into the event system."""
    write_event(
        action=event_type,
        actor=actor,
        entity=detail[:200],
        visibility="chairman",
        sensitivity=sensitivity,
    )


def doc_event(
    event_type: str,
    filename: str,
    actor: str = "system",
    metadata: dict = None,
    sensitivity: str = "info",
) -> None:
    """Write a document/OCR event."""
    write_event(
        action=event_type,
        actor=actor,
        entity=f"doc={filename}",
        metadata=metadata or {},
        visibility="operational",
        sensitivity=sensitivity,
    )


def receipt_event(
    event_type: str,
    receipt_id,
    actor: str,
    metadata: dict = None,
    sensitivity: str = "info",
) -> None:
    """Write a receipt lifecycle event."""
    write_event(
        action=event_type,
        actor=actor,
        entity=f"receipt_id={receipt_id}",
        metadata=metadata or {},
        visibility="financial",
        sensitivity=sensitivity,
    )


def perm_event(
    event_type: str,
    performed_by: str,
    target_user: str,
    detail: str = "",
) -> None:
    """Write a permission change event."""
    write_event(
        action=event_type,
        actor=performed_by,
        entity=f"user={target_user}",
        metadata={"detail": detail},
        visibility="chairman",
        sensitivity="medium",
    )


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os

    # Use temp DB for test
    _tmp = tempfile.mktemp(suffix=".db")
    EVENTS_DB = Path(_tmp)
    _db_ready = False
    _db()

    print("=" * 60)
    print("REX EVENTS — SELF-TEST")
    print("=" * 60)

    # 1. Write events
    id1 = write_event(EventType.RECEIPT_SUBMITTED, actor="misha", role="admin_operations",
                      entity="receipt_id=1", metadata={"vendor":"Costco"}, visibility="financial")
    id2 = write_event(EventType.GOV_RBAC_BLOCKED, actor="unknown", visibility="chairman",
                      sensitivity="high", entity="chat_id=999")
    id3 = write_event(EventType.DOC_FILED, actor="system", entity="doc=menu_2026-04-13.pdf",
                      visibility="operational")
    assert id1 and id2 and id3, "Event IDs must be set"
    print(f"✓ Test 1: write_event OK (IDs: {id1}, {id2}, {id3})")

    # 2. Read all events (1-day window)
    events = read_events(days=1)
    assert len(events) == 3, f"Expected 3 events, got {len(events)}"
    assert events[0]["action"] == EventType.DOC_FILED  # newest first
    print("✓ Test 2: read_events (all) OK")

    # 3. Filter by visibility
    fin_events = read_events(days=1, visibility="financial")
    assert len(fin_events) == 1
    assert fin_events[0]["actor"] == "misha"
    print("✓ Test 3: read_events (visibility filter) OK")

    # 4. Filter by min_visibility_role
    # admin_financial can see: financial + operational + all
    role_events = read_events(days=1, min_visibility_role="admin_financial")
    # Should see financial + operational (not chairman)
    assert len(role_events) == 2, f"Expected 2, got {len(role_events)}"
    print("✓ Test 4: read_events (role filter) OK")

    # 5. Red flags
    flags = read_red_flags(days=1)
    assert len(flags) == 1
    assert flags[0]["action"] == EventType.GOV_RBAC_BLOCKED
    print("✓ Test 5: read_red_flags OK")

    # 6. Metadata round-trip
    assert events[2]["metadata"].get("vendor") == "Costco"
    print("✓ Test 6: metadata JSON round-trip OK")

    # 7. Convenience wrappers
    gov_event(EventType.GOV_RBAC_BLOCKED, "system", "test-gov-event")
    receipt_event(EventType.RECEIPT_SUBMITTED, 42, "kato", {"vendor":"Walmart"})
    doc_event(EventType.DOC_RECEIVED, "signin.pdf", "system")
    all_events = read_events(days=1)
    assert len(all_events) == 6
    print("✓ Test 7: convenience wrappers OK")

    # 8. event_summary
    summary = event_summary(days=1)
    assert summary["total"] == 6
    print(f"✓ Test 8: event_summary OK — {summary['total']} events, "
          f"by_sensitivity: {summary['by_sensitivity']}")

    os.unlink(_tmp)
    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_events.py ready")
    print("=" * 60)
