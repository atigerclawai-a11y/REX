"""
rex_unresolved.py — REX Unresolved Item Queue
════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 3 · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  Provides a formal, persistent queue for items that:
    • Could not be answered or filed deterministically
    • Need clarification from a specific person before proceeding
    • Are ambiguous documents, unclear instructions, or open questions
    • Were escalated from the OCR/filing pipeline
    • Are pending decisions that must not be silently dropped

  Items resurface automatically:
    • Every day at 9 PM (daily check)
    • Every Friday at 9 PM (weekly digest — includes age-sorted list)

  Items track their full lifecycle:
    created → pending → clarification_routed → resolved / escalated

LIFECYCLE:
  create_item()  → stores item, emits unresolved.created event
  resurface()    → sends Telegram reminder, emits unresolved.resurfaced event
  resolve_item() → marks resolved, emits unresolved.resolved event
  escalate_item()→ marks escalated (urgent), emits unresolved.escalated event
  pending_items()→ returns all open items (for resurfacing + dashboard)
  get_item()     → fetch single item by ID

ITEM SCHEMA:
  id               INTEGER PRIMARY KEY
  created_at       TEXT (ISO)
  title            TEXT (short description)
  description      TEXT (full context)
  source           TEXT (who/what created it: "ocr", "telegram", "manual", etc.)
  source_ref       TEXT (file path, receipt_id, doc name, etc.)
  priority         TEXT (critical / high / medium / low)
  clarify_target   TEXT (kato / allen / vlad / misha — who needs to answer)
  status           TEXT (pending / clarification_routed / resolved / escalated)
  resolved_at      TEXT (ISO or NULL)
  resolved_by      TEXT (user_label or NULL)
  resolution_note  TEXT (how it was resolved)
  resurface_count  INTEGER (how many times it's been shown)
  last_resurfaced  TEXT (ISO or NULL)
  event_id         INTEGER (FK to rex_events if available)

RESURFACING LOGIC:
  Run check_resurfacing() from a scheduler (daily at 21:00).
  It sends Telegram messages to the appropriate clarify_target.
  The scheduler can be cron, launchd, or the daily_scheduler in this repo.
  On Friday, it also generates a weekly digest.

TELEGRAM OUTPUT:
  Daily (if there are open items):
    "⏳ 3 unresolved items need your attention:
     1. [HIGH] Menu scan from April 12 — ambiguous shift (2 days old)
     2. [MED] Receipt from Misha — vendor unreadable (5 days old)
     3. [LOW] Staff schedule change — waiting for Vlad confirmation (1 day old)"

  Weekly (Friday, all open items regardless of count):
    Full list sorted by age (oldest first).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
UNRESOLVED_DB = Path.home() / "Desktop" / "REX" / "data" / "rex_unresolved.db"
_TG_CONFIG    = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"

# ── Constants ──────────────────────────────────────────────────────────────────
PRIORITY_LEVELS = ("critical", "high", "medium", "low")
STATUS_PENDING   = "pending"
STATUS_CLARIFY   = "clarification_routed"
STATUS_RESOLVED  = "resolved"
STATUS_ESCALATED = "escalated"

OPEN_STATUSES = (STATUS_PENDING, STATUS_CLARIFY)

# Default Telegram routing per target (matched against rex_rexxie_telegram_config.json)
# These are user_label names; actual chat_ids are looked up from config.
CLARIFY_TARGETS = ("kato", "allen", "vlad", "misha")


# ──────────────────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_db() -> None:
    UNRESOLVED_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(UNRESOLVED_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS unresolved_items (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            title            TEXT NOT NULL,
            description      TEXT DEFAULT '',
            source           TEXT DEFAULT 'system',
            source_ref       TEXT DEFAULT '',
            priority         TEXT NOT NULL DEFAULT 'medium',
            clarify_target   TEXT NOT NULL DEFAULT 'kato',
            status           TEXT NOT NULL DEFAULT 'pending',
            resolved_at      TEXT,
            resolved_by      TEXT,
            resolution_note  TEXT DEFAULT '',
            resurface_count  INTEGER NOT NULL DEFAULT 0,
            last_resurfaced  TEXT,
            event_id         INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_ur_status   ON unresolved_items(status);
        CREATE INDEX IF NOT EXISTS idx_ur_priority ON unresolved_items(priority);
        CREATE INDEX IF NOT EXISTS idx_ur_target   ON unresolved_items(clarify_target);
        CREATE INDEX IF NOT EXISTS idx_ur_created  ON unresolved_items(created_at);
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
# CORE OPERATIONS
# ──────────────────────────────────────────────────────────────────────────────

def create_item(
    title:           str,
    description:     str  = "",
    source:          str  = "system",
    source_ref:      str  = "",
    priority:        str  = "medium",
    clarify_target:  str  = "kato",
) -> int:
    """
    Create a new unresolved item. Returns the item ID.
    Emits unresolved.created event via rex_events.
    """
    _db()

    if priority not in PRIORITY_LEVELS:
        priority = "medium"
    if clarify_target not in CLARIFY_TARGETS:
        clarify_target = "kato"

    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        cur = con.execute(
            "INSERT INTO unresolved_items "
            "(title, description, source, source_ref, priority, clarify_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, description, source, source_ref, priority, clarify_target, STATUS_PENDING)
        )
        item_id = cur.lastrowid
        con.commit()
        con.close()
    except Exception as e:
        logger.error(f"[unresolved] create_item failed: {e}")
        return -1

    # Emit event
    try:
        from rex_events import write_event, EventType
        event_id = write_event(
            action=EventType.UNRESOLVED_CREATED,
            actor=source,
            entity=f"unresolved_id={item_id}",
            metadata={
                "title": title,
                "priority": priority,
                "clarify_target": clarify_target,
                "source_ref": source_ref,
            },
            visibility="operational",
            sensitivity=_priority_to_sensitivity(priority),
        )
        # Store event_id back
        if event_id:
            con = sqlite3.connect(str(UNRESOLVED_DB))
            con.execute("UPDATE unresolved_items SET event_id=? WHERE id=?", (event_id, item_id))
            con.commit()
            con.close()
    except Exception as e:
        logger.warning(f"[unresolved] event emit failed (non-fatal): {e}")

    logger.info(f"[unresolved] Created item #{item_id}: [{priority}] {title} → {clarify_target}")
    return item_id


def resolve_item(
    item_id:        int,
    resolved_by:    str,
    resolution_note: str = "",
) -> tuple[bool, str]:
    """Mark an item as resolved. Returns (success, message)."""
    _db()
    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        row = con.execute(
            "SELECT status, title FROM unresolved_items WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            con.close()
            return False, f"Item #{item_id} not found."
        if row[0] == STATUS_RESOLVED:
            con.close()
            return False, f"Item #{item_id} is already resolved."

        con.execute(
            "UPDATE unresolved_items SET status=?, resolved_at=datetime('now'), "
            "resolved_by=?, resolution_note=? WHERE id=?",
            (STATUS_RESOLVED, resolved_by, resolution_note, item_id)
        )
        con.commit()
        con.close()
    except Exception as e:
        return False, f"DB error: {e}"

    try:
        from rex_events import write_event, EventType
        write_event(
            action=EventType.UNRESOLVED_RESOLVED,
            actor=resolved_by,
            entity=f"unresolved_id={item_id}",
            metadata={"note": resolution_note, "title": row[1]},
            visibility="operational",
            sensitivity="info",
        )
    except Exception:
        pass

    return True, f"✅ Item #{item_id} resolved by {resolved_by}."


def escalate_item(
    item_id:  int,
    actor:    str,
    note:     str = "",
) -> tuple[bool, str]:
    """Escalate an item to critical + route to Chairman."""
    _db()
    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        row = con.execute(
            "SELECT status, title FROM unresolved_items WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            con.close()
            return False, f"Item #{item_id} not found."

        con.execute(
            "UPDATE unresolved_items "
            "SET status=?, priority='critical', clarify_target='kato' WHERE id=?",
            (STATUS_ESCALATED, item_id)
        )
        con.commit()
        con.close()
    except Exception as e:
        return False, f"DB error: {e}"

    try:
        from rex_events import write_event, EventType
        write_event(
            action=EventType.UNRESOLVED_ESCALATED,
            actor=actor,
            entity=f"unresolved_id={item_id}",
            metadata={"note": note, "title": row[1]},
            visibility="chairman",
            sensitivity="high",
        )
    except Exception:
        pass

    # Alert Chairman via Telegram
    _tg_send(
        "kato",
        f"🚨 <b>ESCALATED</b> — Unresolved Item #{item_id}\n"
        f"<b>{row[1]}</b>\n"
        f"Escalated by: {actor}\n"
        f"{note if note else 'No note provided.'}"
    )

    return True, f"✅ Item #{item_id} escalated to Chairman."


def get_item(item_id: int) -> Optional[dict]:
    """Fetch a single unresolved item by ID."""
    _db()
    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM unresolved_items WHERE id=?", (item_id,)
        ).fetchone()
        con.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"[unresolved] get_item error: {e}")
        return None


def pending_items(
    clarify_target: str = "",
    priority: str = "",
    include_escalated: bool = True,
) -> list[dict]:
    """
    Return all open unresolved items.
    Optional filters: clarify_target, priority.
    """
    _db()
    statuses = list(OPEN_STATUSES)
    if include_escalated:
        statuses.append(STATUS_ESCALATED)

    placeholders = ",".join("?" * len(statuses))
    clauses = [f"status IN ({placeholders})"]
    params = list(statuses)

    if clarify_target:
        clauses.append("clarify_target = ?")
        params.append(clarify_target)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)

    where = " AND ".join(clauses)
    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"SELECT * FROM unresolved_items WHERE {where} ORDER BY "
            "CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC",
            params
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[unresolved] pending_items error: {e}")
        return []


def all_items(limit: int = 100) -> list[dict]:
    """Return all items (including resolved), newest first."""
    _db()
    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM unresolved_items ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[unresolved] all_items error: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# RESURFACING ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def check_resurfacing(force: bool = False) -> dict:
    """
    Check if it's time to resurface unresolved items.
    Call this every hour from a scheduler. It will:
      - At 21:00 daily: send targeted reminders to each clarify_target
      - At 21:00 Friday: also send weekly digest to Chairman

    Args:
        force: If True, resurface regardless of time (for testing / manual trigger)

    Returns:
        {"sent": n, "targets": [...], "weekly": bool}
    """
    now = datetime.now()
    is_resurface_time = force or (now.hour == 21 and now.minute < 5)
    is_friday = now.weekday() == 4  # 0=Monday, 4=Friday

    if not is_resurface_time:
        return {"sent": 0, "targets": [], "weekly": False}

    items = pending_items(include_escalated=False)
    if not items:
        return {"sent": 0, "targets": [], "weekly": False}

    # Group by clarify_target
    by_target: dict[str, list[dict]] = {}
    for item in items:
        t = item["clarify_target"]
        by_target.setdefault(t, []).append(item)

    sent = 0
    targets_notified = []

    for target, target_items in by_target.items():
        msg = _format_resurface_message(target_items, target, weekly=False)
        _tg_send(target, msg)
        _mark_resurfaced([i["id"] for i in target_items])
        targets_notified.append(target)
        sent += len(target_items)

        # Log event
        try:
            from rex_events import write_event, EventType
            for item in target_items:
                write_event(
                    action=EventType.UNRESOLVED_SURFACED,
                    actor="system",
                    entity=f"unresolved_id={item['id']}",
                    metadata={"target": target, "title": item["title"]},
                    visibility="operational",
                    sensitivity="info",
                )
        except Exception:
            pass

    # Weekly digest on Friday
    weekly_sent = False
    if is_friday:
        all_open = pending_items(include_escalated=True)
        if all_open:
            weekly_msg = _format_weekly_digest(all_open)
            _tg_send("kato", weekly_msg)
            weekly_sent = True

    return {"sent": sent, "targets": targets_notified, "weekly": weekly_sent}


def _format_resurface_message(items: list[dict], target: str, weekly: bool = False) -> str:
    """Format a Telegram resurfacing message."""
    count = len(items)
    header = (
        f"⏳ <b>{count} unresolved item{'s' if count > 1 else ''}</b> need your attention, "
        f"{target.title()}:"
    )
    lines = [header, ""]
    for i, item in enumerate(items[:10], 1):
        age = _age_str(item["created_at"])
        prio = item["priority"].upper()
        lines.append(f"{i}. [{prio}] {item['title']} <i>({age})</i>")
        if item.get("source_ref"):
            lines.append(f"   Source: {item['source_ref']}")
    if count > 10:
        lines.append(f"   … and {count - 10} more")
    lines += ["", "Reply to resolve or escalate any item."]
    return "\n".join(lines)


def _format_weekly_digest(items: list[dict]) -> str:
    """Format Friday weekly digest for Chairman."""
    count = len(items)
    lines = [
        f"📋 <b>WEEKLY UNRESOLVED DIGEST — {datetime.now().strftime('%A %B %d')}</b>",
        f"Total open: <b>{count}</b>",
        "",
    ]
    # Sort by age (oldest first)
    sorted_items = sorted(items, key=lambda x: x["created_at"])
    for item in sorted_items:
        age  = _age_str(item["created_at"])
        prio = item["priority"].upper()
        tgt  = item["clarify_target"].title()
        lines.append(f"• [{prio}] #{item['id']} — {item['title']}")
        lines.append(f"  Target: {tgt} | Age: {age} | Status: {item['status']}")
    return "\n".join(lines)


def _mark_resurfaced(item_ids: list[int]) -> None:
    """Update resurface_count and last_resurfaced for a list of item IDs."""
    if not item_ids:
        return
    try:
        con = sqlite3.connect(str(UNRESOLVED_DB))
        placeholders = ",".join("?" * len(item_ids))
        con.execute(
            f"UPDATE unresolved_items "
            f"SET resurface_count = resurface_count + 1, last_resurfaced = datetime('now') "
            f"WHERE id IN ({placeholders})",
            item_ids
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.error(f"[unresolved] _mark_resurfaced error: {e}")


def _age_str(created_at: str) -> str:
    """Human-readable age from ISO timestamp."""
    try:
        dt = datetime.fromisoformat(created_at)
        delta = datetime.now() - dt
        days = delta.days
        hours = delta.seconds // 3600
        if days == 0:
            return f"{hours}h ago" if hours > 0 else "just now"
        elif days == 1:
            return "1 day ago"
        else:
            return f"{days} days ago"
    except Exception:
        return "unknown age"


def _priority_to_sensitivity(priority: str) -> str:
    return {
        "critical": "critical",
        "high":     "high",
        "medium":   "medium",
        "low":      "low",
    }.get(priority, "info")


# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM BRIDGE
# ──────────────────────────────────────────────────────────────────────────────

# Chat ID map — extended from rex_rexxie_telegram_config.json
# chairman/kato use the Rexxie bot chat_id (ALLOWED_CHAT_IDS).
# Other users get direct Telegram notifications when their IDs are configured.
_CHAT_ID_MAP: dict[str, Optional[int]] = {}

def _load_chat_map() -> None:
    """Load known chat IDs from config file."""
    global _CHAT_ID_MAP
    if _CHAT_ID_MAP:
        return  # already loaded
    try:
        if _TG_CONFIG.exists():
            cfg = json.loads(_TG_CONFIG.read_text())
            _CHAT_ID_MAP["kato"]  = int(cfg.get("owner_chat_id", 0)) or None
            _CHAT_ID_MAP["allen"] = int(cfg.get("allen_chat_id", 0)) or None
            _CHAT_ID_MAP["vlad"]  = int(cfg.get("vlad_chat_id", 0)) or None
            _CHAT_ID_MAP["misha"] = int(cfg.get("misha_chat_id", 0)) or None
    except Exception as e:
        logger.warning(f"[unresolved] chat map load: {e}")


def _tg_send(target: str, text: str) -> bool:
    """Send a Telegram message to a named target. Returns True on success."""
    _load_chat_map()
    chat_id = _CHAT_ID_MAP.get(target)
    if not chat_id:
        logger.warning(f"[unresolved] No chat_id for target '{target}' — Telegram not sent")
        return False
    try:
        cfg   = json.loads(_TG_CONFIG.read_text()) if _TG_CONFIG.exists() else {}
        token = cfg.get("bot_token", "")
        if not token:
            return False
        import urllib.request
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True
    except Exception as e:
        logger.error(f"[unresolved] Telegram send to {target} failed: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os

    _tmp = tempfile.mktemp(suffix=".db")
    UNRESOLVED_DB = Path(_tmp)
    _db_ready = False
    _db()

    print("=" * 60)
    print("REX UNRESOLVED — SELF-TEST")
    print("=" * 60)

    # 1. Create items
    id1 = create_item("Menu scan ambiguous", "Could not determine shift",
                       source="ocr", source_ref="menu_2026-04-13.pdf",
                       priority="high", clarify_target="kato")
    id2 = create_item("Receipt vendor unreadable", "Photo quality too low",
                       source="receipt", source_ref="receipt_id=42",
                       priority="medium", clarify_target="kato")
    id3 = create_item("Staff schedule question", "Vlad needs to confirm Tuesday",
                       source="manual", priority="low", clarify_target="vlad")
    assert id1 > 0 and id2 > 0 and id3 > 0
    print(f"✓ Test 1: create_item OK (IDs: {id1}, {id2}, {id3})")

    # 2. Pending items
    items = pending_items()
    assert len(items) == 3
    assert items[0]["priority"] == "high"  # sorted critical/high first
    print("✓ Test 2: pending_items (sorted by priority) OK")

    # 3. Filter by target
    vlad_items = pending_items(clarify_target="vlad")
    assert len(vlad_items) == 1
    assert vlad_items[0]["title"] == "Staff schedule question"
    print("✓ Test 3: pending_items (target filter) OK")

    # 4. Resolve
    ok, msg = resolve_item(id2, "kato", "Vendor identified as Costco")
    assert ok, msg
    items = pending_items()
    assert len(items) == 2
    print("✓ Test 4: resolve_item OK")

    # 5. Get item
    item = get_item(id2)
    assert item["status"] == "resolved"
    assert item["resolved_by"] == "kato"
    print("✓ Test 5: get_item + resolved status OK")

    # 6. Escalate
    ok, msg = escalate_item(id3, "system", "Deadline approaching")
    assert ok, msg
    item3 = get_item(id3)
    assert item3["status"] == "escalated"
    assert item3["priority"] == "critical"
    assert item3["clarify_target"] == "kato"
    print("✓ Test 6: escalate_item OK (priority→critical, target→kato)")

    # 7. Age string
    age = _age_str(datetime.now().isoformat())
    assert "just now" in age or "0h" in age or "ago" in age
    print(f"✓ Test 7: _age_str OK ('{age}')")

    # 8. Resurface message format
    msg_text = _format_resurface_message([get_item(id1)], "kato")
    assert "UNRESOLVED" in msg_text.upper() or "ATTENTION" in msg_text.upper() or "need" in msg_text.lower()
    print("✓ Test 8: _format_resurface_message OK")

    os.unlink(_tmp)
    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_unresolved.py ready")
    print()
    print("  Wire into scheduler: check_resurfacing() at 21:00 daily")
    print("  Friday 21:00 also triggers weekly digest to Chairman")
    print("=" * 60)
