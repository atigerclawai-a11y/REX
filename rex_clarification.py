"""
rex_clarification.py — REX Targeted Clarification Router
════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 3 · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  When REX or Rexxie encounters something it cannot resolve:
    • An ambiguous document that could be a sign-in OR a driver sheet
    • A receipt with an unreadable vendor name
    • A question that needs human domain expertise
    • A menu item classification that's uncertain
    • A schedule conflict that requires a specific person's input

  This module decides WHO to route to and how to phrase the question.
  It never routes silently. It never guesses. It always creates a paper trail.

ROUTING TABLE:
  ┌─────────────────────────────────────────────────────┬──────────────┐
  │ Domain                                              │ Route to     │
  ├─────────────────────────────────────────────────────┼──────────────┤
  │ Financial — receipts, expenses, billing, invoices   │ allen / vlad │
  │ Operations — menu, kitchen, food, prep, schedule    │ misha        │
  │ Administration — staff, routes, sign-ins, clients   │ vlad         │
  │ Security — RBAC, override, audit, policy            │ kato         │
  │ System — technical errors, OCR failures, fallbacks  │ kato         │
  │ Unknown / high-stakes / escalated                   │ kato         │
  └─────────────────────────────────────────────────────┴──────────────┘

  "Route to allen / vlad" means: check if allen is available first.
  If allen is unmapped (no Telegram chat_id), fall back to vlad.
  If vlad is unmapped, fall back to kato.
  Kato is always the final fallback. Never silent.

CLARIFICATION LIFECYCLE:
  route()          → decide target, create unresolved item, notify via Telegram
  mark_answered()  → close the clarification, resolve the unresolved item
  pending()        → list open clarifications (for Chairman dashboard)

INTEGRATION:
  Called from:
    • goj_signin_intake.py   — ambiguous document type
    • rex_receipt_manager.py — unreadable vendor or missing fields
    • private_confidant_gold.py — message requires human answer
    • Any module that hits uncertainty

  Example (from OCR pipeline):
    from rex_clarification import route_clarification

    item_id = route_clarification(
        question="Is this a sign-in sheet or driver route?",
        context="File: menu_2026-04-13.pdf — found keywords from both categories",
        domain="operations",
        source_ref="menu_2026-04-13.pdf",
        urgency="high",
    )
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_TG_CONFIG = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"

# ── Domain → routing table ────────────────────────────────────────────────────
# Each domain maps to an ordered list of targets (first available wins).
# "kato" is always in the chain as the ultimate fallback.
DOMAIN_ROUTING: dict[str, list[str]] = {
    "financial":    ["allen", "vlad", "kato"],
    "operations":   ["misha", "kato"],
    "admin":        ["vlad", "kato"],
    "security":     ["kato"],
    "system":       ["kato"],
    "unknown":      ["kato"],
    "medical":      ["kato"],       # PHI/client data → Chairman only
    "hr":           ["vlad", "kato"],
}

# Domain keyword detection (for auto-routing when domain not specified)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "financial": [
        "receipt", "invoice", "expense", "amount", "total", "vendor",
        "billing", "payment", "cost", "budget", "tax", "ledger",
    ],
    "operations": [
        "menu", "kitchen", "food", "prep", "serving", "meal", "lunch",
        "breakfast", "dinner", "cook", "portion", "misha",
    ],
    "admin": [
        "sign-in", "signin", "driver", "route", "client", "schedule",
        "shift", "attendance", "transport", "vlad",
    ],
    "security": [
        "rbac", "override", "block", "unauthorized", "access denied",
        "permission", "policy", "audit",
    ],
    "medical": [
        "diagnosis", "medication", "health", "medical", "hipaa", "phi",
        "insurance", "medicaid", "condition",
    ],
}

# ── Priority → urgency mapping ────────────────────────────────────────────────
URGENCY_LEVELS = ("critical", "high", "medium", "low")


def detect_domain(text: str) -> str:
    """Auto-detect domain from text content. Returns domain string."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return "unknown"
    return max(scores, key=lambda d: scores[d])


def pick_target(domain: str) -> str:
    """
    Pick the best available target for a domain.
    Checks Telegram config for known chat IDs.
    Falls back through the chain. Kato always resolves.
    """
    chain = DOMAIN_ROUTING.get(domain, ["kato"])
    chat_map = _load_chat_map()
    for target in chain:
        if target == "kato" or chat_map.get(target):
            return target
    return "kato"  # ultimate fallback


def route_clarification(
    question:    str,
    context:     str   = "",
    domain:      str   = "",
    source_ref:  str   = "",
    urgency:     str   = "medium",
    source:      str   = "system",
) -> int:
    """
    Route a clarification request to the appropriate person.

    Steps:
      1. Detect or use provided domain
      2. Pick the best available target
      3. Create an unresolved item
      4. Send Telegram notification to target
      5. Emit rex_events event
      6. Return unresolved item ID

    Returns:
        item_id (int) — the unresolved queue item ID, or -1 on failure.
    """
    if not domain:
        domain = detect_domain(f"{question} {context}")

    target = pick_target(domain)

    if urgency not in URGENCY_LEVELS:
        urgency = "medium"

    # Create unresolved item
    try:
        from rex_unresolved import create_item, STATUS_CLARIFY
        item_id = create_item(
            title=question[:120],
            description=f"{context}\n\nSource: {source_ref}" if context else source_ref,
            source=source,
            source_ref=source_ref,
            priority=urgency,
            clarify_target=target,
        )
    except Exception as e:
        logger.error(f"[clarification] create_item failed: {e}")
        return -1

    if item_id < 0:
        return -1

    # Mark as clarification_routed
    try:
        from rex_unresolved import UNRESOLVED_DB, _db
        _db()
        con = sqlite3.connect(str(UNRESOLVED_DB))
        con.execute(
            "UPDATE unresolved_items SET status='clarification_routed' WHERE id=?",
            (item_id,)
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.warning(f"[clarification] status update failed (non-fatal): {e}")

    # Send Telegram
    tg_text = _format_clarification_message(
        question=question,
        context=context,
        domain=domain,
        source_ref=source_ref,
        urgency=urgency,
        item_id=item_id,
    )
    _tg_send(target, tg_text)

    # Emit event
    try:
        from rex_events import write_event, EventType
        write_event(
            action=EventType.CLARIFICATION_ROUTED,
            actor=source,
            entity=f"unresolved_id={item_id}",
            metadata={
                "question": question[:200],
                "domain": domain,
                "target": target,
                "urgency": urgency,
                "source_ref": source_ref,
            },
            visibility="operational",
            sensitivity=_urgency_to_sensitivity(urgency),
        )
    except Exception as e:
        logger.warning(f"[clarification] event emit failed (non-fatal): {e}")

    logger.info(
        f"[clarification] Item #{item_id} routed: domain={domain}, "
        f"target={target}, urgency={urgency}"
    )
    return item_id


def mark_answered(
    item_id:     int,
    answered_by: str,
    answer:      str = "",
) -> tuple[bool, str]:
    """
    Mark a clarification as answered and resolve the unresolved item.
    Returns (success, message).
    """
    try:
        from rex_unresolved import resolve_item
        ok, msg = resolve_item(item_id, answered_by, resolution_note=answer)
        if not ok:
            return False, msg
    except Exception as e:
        return False, f"Error: {e}"

    # Emit event
    try:
        from rex_events import write_event, EventType
        write_event(
            action=EventType.CLARIFICATION_ANSWERED,
            actor=answered_by,
            entity=f"unresolved_id={item_id}",
            metadata={"answer": answer[:300] if answer else ""},
            visibility="operational",
            sensitivity="info",
        )
    except Exception:
        pass

    return True, f"✅ Clarification #{item_id} answered by {answered_by}."


def pending_clarifications(target: str = "") -> list[dict]:
    """Return open clarification items, optionally filtered by target."""
    try:
        from rex_unresolved import pending_items
        items = pending_items(clarify_target=target)
        return [i for i in items if i.get("status") in ("clarification_routed", "pending")]
    except Exception as e:
        logger.error(f"[clarification] pending_clarifications error: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# FORMATTING HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _format_clarification_message(
    question: str,
    context: str,
    domain: str,
    source_ref: str,
    urgency: str,
    item_id: int,
) -> str:
    """Format a Telegram clarification request."""
    urgency_emoji = {
        "critical": "🚨",
        "high":     "⚠️",
        "medium":   "❓",
        "low":      "ℹ️",
    }.get(urgency, "❓")

    lines = [
        f"{urgency_emoji} <b>CLARIFICATION NEEDED</b> [#{item_id}]",
        f"<b>{question}</b>",
        "",
    ]
    if context:
        lines.append(f"Context: <i>{context[:300]}</i>")
    if source_ref:
        lines.append(f"Source: {source_ref}")
    lines += [
        f"Domain: {domain} | Urgency: {urgency.upper()}",
        "",
        "Please reply with your answer. I'll log your response.",
    ]
    return "\n".join(lines)


def _urgency_to_sensitivity(urgency: str) -> str:
    return {
        "critical": "critical",
        "high":     "high",
        "medium":   "medium",
        "low":      "low",
    }.get(urgency, "medium")


# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM BRIDGE
# ──────────────────────────────────────────────────────────────────────────────

_CHAT_ID_MAP: dict[str, Optional[int]] = {}

def _load_chat_map() -> dict[str, Optional[int]]:
    global _CHAT_ID_MAP
    if _CHAT_ID_MAP:
        return _CHAT_ID_MAP
    try:
        if _TG_CONFIG.exists():
            cfg = json.loads(_TG_CONFIG.read_text())
            _CHAT_ID_MAP = {
                "kato":  int(cfg.get("owner_chat_id", 0)) or None,
                "allen": int(cfg.get("allen_chat_id", 0)) or None,
                "vlad":  int(cfg.get("vlad_chat_id", 0)) or None,
                "misha": int(cfg.get("misha_chat_id", 0)) or None,
            }
    except Exception as e:
        logger.warning(f"[clarification] chat map load: {e}")
    return _CHAT_ID_MAP


def _tg_send(target: str, text: str) -> bool:
    """Send Telegram message to named target. Returns True on success."""
    chat_map = _load_chat_map()
    chat_id  = chat_map.get(target)

    if not chat_id:
        logger.warning(
            f"[clarification] No chat_id for target '{target}' — "
            f"add {target}_chat_id to rex_rexxie_telegram_config.json"
        )
        # Still log — just no Telegram delivery
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
        logger.error(f"[clarification] Telegram send to {target} failed: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os
    from pathlib import Path

    # Redirect DBs to temp
    _tmp_unresolved = tempfile.mktemp(suffix=".db")
    _tmp_events     = tempfile.mktemp(suffix=".db")

    import rex_unresolved, rex_events
    rex_unresolved.UNRESOLVED_DB = Path(_tmp_unresolved)
    rex_unresolved._db_ready = False
    rex_events.EVENTS_DB = Path(_tmp_events)
    rex_events._db_ready = False

    print("=" * 60)
    print("REX CLARIFICATION — SELF-TEST")
    print("=" * 60)

    # 1. Domain detection
    assert detect_domain("vendor receipt amount total expense") == "financial"
    assert detect_domain("menu kitchen food prep lunch") == "operations"
    assert detect_domain("sign-in driver route attendance") == "admin"
    assert detect_domain("override rbac unauthorized access denied") == "security"
    assert detect_domain("xyz abc 123") == "unknown"
    print("✓ Test 1: domain detection OK")

    # 2. Target routing (financial → allen first, but allen not in map → vlad → kato)
    # Without a config file loaded, kato should be the fallback
    _CHAT_ID_MAP.clear()
    target = pick_target("financial")
    assert target in ("allen", "vlad", "kato")
    target_sec = pick_target("security")
    assert target_sec == "kato"
    print(f"✓ Test 2: pick_target OK (financial→{target}, security→{target_sec})")

    # 3. route_clarification (without Telegram — TG config not present)
    item_id = route_clarification(
        question="Is this a sign-in or driver sheet?",
        context="Found keywords from both categories",
        domain="admin",
        source_ref="doc_2026-04-13.pdf",
        urgency="high",
        source="ocr",
    )
    assert item_id > 0, f"Expected positive item_id, got {item_id}"
    print(f"✓ Test 3: route_clarification OK (item_id={item_id})")

    # 4. Verify unresolved item was created
    from rex_unresolved import get_item
    item = get_item(item_id)
    assert item is not None
    assert "sign-in" in item["title"].lower()
    assert item["status"] in ("pending", "clarification_routed")
    print(f"✓ Test 4: unresolved item created — status={item['status']}")

    # 5. mark_answered
    ok, msg = mark_answered(item_id, "vlad", "This is a sign-in sheet for Monday shift 1")
    assert ok, msg
    item = get_item(item_id)
    assert item["status"] == "resolved"
    print("✓ Test 5: mark_answered → resolved OK")

    # 6. Financial domain with context
    item_id2 = route_clarification(
        question="Vendor name on receipt is unreadable",
        context="receipt_id=42, amount=$87.50, vendor field shows illegible scan",
        source_ref="receipt_id=42",
        urgency="medium",
        source="receipt_manager",
    )
    assert item_id2 > 0
    item2 = get_item(item_id2)
    assert item2["clarify_target"] in ("allen", "vlad", "kato")
    print(f"✓ Test 6: Financial clarification routed to {item2['clarify_target']}")

    # 7. pending_clarifications
    pending = pending_clarifications()
    assert any(i["id"] == item_id2 for i in pending)
    print(f"✓ Test 7: pending_clarifications OK ({len(pending)} open)")

    os.unlink(_tmp_unresolved)
    os.unlink(_tmp_events)

    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_clarification.py ready")
    print()
    print("  Usage: route_clarification(question, context, domain)")
    print("  Add allen_chat_id/vlad_chat_id/misha_chat_id to")
    print("  rex_rexxie_telegram_config.json for direct routing")
    print("=" * 60)
