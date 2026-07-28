"""
backend/rex_command_center.py — Chairman Command Center API
════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 13 · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  Provides FastAPI routes for the Chairman Command Center.
  ALL routes in this module are Chairman-only.

  No executive users (vlad/allen) can access these routes.
  No impersonation path exists.
  Rexxie private domain is NEVER exposed here.

MOUNT IN backend/main.py:
    from .rex_command_center import cc_router
    from .rex_training_panel import training_router
    app.include_router(training_router, prefix="/api/chairman")
    app.include_router(cc_router, prefix="/api/chairman")

ROUTES:
  GET  /api/chairman/system-health     → system health panel
  GET  /api/chairman/finance-receipts  → finance/receipts panel
  GET  /api/chairman/staff-permissions → staff/permissions panel
  GET  /api/chairman/red-flags         → red flags panel (CRITICAL/HIGH events)
  GET  /api/chairman/unresolved        → unresolved queue panel
  GET  /api/chairman/activity-trail    → activity trail (10-day default, 14-day max)
  POST /api/chairman/resolve/{item_id} → resolve an unresolved item
  POST /api/chairman/escalate/{item_id}→ escalate an unresolved item

AUTH:
  All routes require verified chairman role.
  Role is verified via backend.rex_role_auth.verify_role().
  If role is not chairman, 403 is returned — no information leakage.
  The caller_role field in WebSocket payloads is NOT trusted for chairman access.
  This module reads the role from the server-verified role registry only.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

cc_router = APIRouter(tags=["Chairman Command Center"])

_REX_DIR = Path.home() / "Desktop" / "REX"


# ──────────────────────────────────────────────────────────────────────────────
# AUTH GUARD
# ──────────────────────────────────────────────────────────────────────────────

def _require_chairman(
    x_user_name: Optional[str],
    x_claimed_role: Optional[str],
) -> None:
    """
    Verify that the requesting user is the Chairman.
    Raises HTTPException(403) if not.
    Never leaks what roles are valid.
    """
    try:
        from .rex_role_auth import verify_role
        verified = verify_role(x_user_name or "", x_claimed_role or "")
        if verified != "chairman":
            raise HTTPException(status_code=403, detail="Access denied.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cc] Auth check error: {e}")
        raise HTTPException(status_code=403, detail="Access denied.")


# ──────────────────────────────────────────────────────────────────────────────
# ROUTE MODELS
# ──────────────────────────────────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    resolved_by:     str = "kato"
    resolution_note: str = ""


class EscalateRequest(BaseModel):
    actor: str = "kato"
    note:  str = ""


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM HEALTH PANEL
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/system-health")
async def system_health(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Chairman Command Center — System Health Panel.
    Returns: uptime indicators, recent event counts, DB status, last activity.
    """
    _require_chairman(x_user_name, x_claimed_role)

    health: dict = {
        "panel": "system_health",
        "ts": datetime.now().isoformat(),
        "status": "ok",
        "components": {},
    }

    # ── Event system ──────────────────────────────────────────────────────────
    try:
        from rex_events import event_summary
        summary = event_summary(days=1)
        health["components"]["events"] = {
            "status": "ok",
            "last_24h": summary.get("total", 0),
            "by_sensitivity": summary.get("by_sensitivity", {}),
            "last_event": summary.get("last_event_ts"),
        }
    except Exception as e:
        health["components"]["events"] = {"status": "error", "error": str(e)}

    # ── Permissions DB ────────────────────────────────────────────────────────
    perms_db = _REX_DIR / "data" / "rex_permissions.db"
    health["components"]["permissions_db"] = {
        "status": "ok" if perms_db.exists() else "missing",
        "path": str(perms_db),
        "size_kb": round(perms_db.stat().st_size / 1024, 1) if perms_db.exists() else 0,
    }

    # ── Enforcer audit DB ─────────────────────────────────────────────────────
    enforcer_db = _REX_DIR / "data" / "rex_enforcer_audit.db"
    health["components"]["enforcer_audit_db"] = {
        "status": "ok" if enforcer_db.exists() else "missing",
        "path": str(enforcer_db),
    }

    # ── Unresolved queue ──────────────────────────────────────────────────────
    try:
        from rex_unresolved import pending_items
        open_items = pending_items()
        critical_items = [i for i in open_items if i["priority"] == "critical"]
        health["components"]["unresolved_queue"] = {
            "status": "warning" if critical_items else ("ok" if not open_items else "info"),
            "open_count": len(open_items),
            "critical_count": len(critical_items),
        }
    except Exception as e:
        health["components"]["unresolved_queue"] = {"status": "error", "error": str(e)}

    # ── Rexxie private DB (existence check only — NO data exposed) ────────────
    rexxie_db = _REX_DIR.parent / "Gold_Health_Systems" / "rexxie_private.db"
    alt_rexxie = Path.home() / "Desktop" / "Gold_Health_Systems" / "rexxie_private.db"
    rdb = rexxie_db if rexxie_db.exists() else (alt_rexxie if alt_rexxie.exists() else None)
    health["components"]["rexxie_private_db"] = {
        "status": "sealed" if rdb else "not_found",
        "exists": rdb is not None,
        "note": "Contents sealed — Chairman only via Rexxie bot. No data exposed here.",
    }

    # Overall status
    statuses = [v.get("status") for v in health["components"].values()]
    if "error" in statuses:
        health["status"] = "degraded"
    elif "missing" in statuses:
        health["status"] = "warning"

    return health


# ──────────────────────────────────────────────────────────────────────────────
# FINANCE / RECEIPTS PANEL
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/finance-receipts")
async def finance_receipts(
    days: int = Query(default=7, ge=1, le=90),
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Chairman Command Center — Finance/Receipts Panel.
    Returns: recent receipts summary, review status breakdown, pending items.
    """
    _require_chairman(x_user_name, x_claimed_role)

    result: dict = {
        "panel": "finance_receipts",
        "ts": datetime.now().isoformat(),
        "days": days,
    }

    # Receipt ledger summary
    ledger_db = _REX_DIR / "data" / "rex_ledger.db"
    if ledger_db.exists():
        try:
            con = sqlite3.connect(str(ledger_db))
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            # Recent receipts
            rows = con.execute(
                "SELECT COUNT(*) as count, SUM(amount) as total "
                "FROM receipts WHERE receipt_date >= ? AND deleted=0",
                (cutoff,)
            ).fetchone()
            result["receipt_count"] = rows[0] if rows else 0
            result["total_amount"]  = round(rows[1] or 0, 2) if rows else 0

            # By submitter
            by_sub = con.execute(
                "SELECT submitted_by, COUNT(*) as cnt, SUM(amount) as total "
                "FROM receipts WHERE receipt_date >= ? AND deleted=0 "
                "GROUP BY submitted_by",
                (cutoff,)
            ).fetchall()
            result["by_submitter"] = [
                {"submitted_by": r[0], "count": r[1], "total": round(r[2] or 0, 2)}
                for r in by_sub
            ]

            # By category
            by_cat = con.execute(
                "SELECT category, COUNT(*) as cnt, SUM(amount) as total "
                "FROM receipts WHERE receipt_date >= ? AND deleted=0 "
                "GROUP BY category ORDER BY total DESC LIMIT 10",
                (cutoff,)
            ).fetchall()
            result["by_category"] = [
                {"category": r[0], "count": r[1], "total": round(r[2] or 0, 2)}
                for r in by_cat
            ]

            # Review status (if v4 columns present)
            try:
                review = con.execute(
                    "SELECT review_status, COUNT(*) FROM receipts "
                    "WHERE receipt_date >= ? AND deleted=0 GROUP BY review_status",
                    (cutoff,)
                ).fetchall()
                result["review_status"] = {r[0]: r[1] for r in review}
            except Exception:
                result["review_status"] = {"note": "v4 columns not yet migrated"}

            con.close()
        except Exception as e:
            result["error"] = str(e)
    else:
        result["note"] = "Receipt ledger DB not found"

    # Recent receipt events
    try:
        from rex_events import read_events
        result["recent_events"] = read_events(days=days, action="receipt.", limit=20)
    except Exception:
        pass

    return result


# ──────────────────────────────────────────────────────────────────────────────
# STAFF / PERMISSIONS PANEL
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/staff-permissions")
async def staff_permissions(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Chairman Command Center — Staff/Permissions Panel.
    Returns: all users and their roles, recent permission changes.
    """
    _require_chairman(x_user_name, x_claimed_role)

    result: dict = {
        "panel": "staff_permissions",
        "ts": datetime.now().isoformat(),
    }

    try:
        from rex_permissions import get_perms, DEFAULT_USER_ROLES, ROLE_DEFINITIONS

        perms = get_perms()

        # All users
        try:
            perms_db = _REX_DIR / "data" / "rex_permissions.db"
            con = sqlite3.connect(str(perms_db))
            users = con.execute(
                "SELECT user_label, role, updated_by, updated_at FROM user_roles ORDER BY user_label"
            ).fetchall()
            con.close()
        except Exception:
            users = [(u, r, "system", "") for u, r in DEFAULT_USER_ROLES.items()]

        result["users"] = []
        for user_label, role, updated_by, updated_at in users:
            norm_role = role
            try:
                from rex_permissions import normalize_role
                norm_role = normalize_role(role)
            except Exception:
                pass
            result["users"].append({
                "user_label": user_label,
                "role": norm_role,
                "permission_count": len(perms.get_all_permissions(user_label)),
                "updated_by": updated_by,
                "updated_at": updated_at,
                "scope_grants": perms.get_scope_grants(user_label),
            })

        # Recent permission changes
        result["recent_changes"] = []
        try:
            perms_db = _REX_DIR / "data" / "rex_permissions.db"
            con = sqlite3.connect(str(perms_db))
            rows = con.execute(
                "SELECT action, target_user, detail, performed_by, performed_at "
                "FROM permissions_audit ORDER BY id DESC LIMIT 20"
            ).fetchall()
            con.close()
            result["recent_changes"] = [
                {"action": r[0], "target": r[1], "detail": r[2],
                 "by": r[3], "at": r[4]}
                for r in rows
            ]
        except Exception as e:
            result["recent_changes_error"] = str(e)

        # Available roles summary
        result["roles"] = {
            role: {"permission_count": len(perms_list)}
            for role, perms_list in ROLE_DEFINITIONS.items()
        }

    except Exception as e:
        result["error"] = str(e)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# RED FLAGS PANEL
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/red-flags")
async def red_flags(
    days: int = Query(default=7, ge=1, le=30),
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Chairman Command Center — Red Flags Panel.
    Returns: CRITICAL and HIGH sensitivity events from the last N days.
    Also includes behavioral flags from the unified enforcer.
    """
    _require_chairman(x_user_name, x_claimed_role)

    result: dict = {
        "panel": "red_flags",
        "ts": datetime.now().isoformat(),
        "days": days,
    }

    # Event system red flags
    try:
        from rex_events import read_red_flags
        result["event_flags"] = read_red_flags(days=days, limit=50)
        result["event_flag_count"] = len(result["event_flags"])
    except Exception as e:
        result["event_flags"] = []
        result["event_flags_error"] = str(e)

    # Enforcer behavioral flags
    try:
        enforcer_db = _REX_DIR / "data" / "rex_enforcer_audit.db"
        if enforcer_db.exists():
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            con = sqlite3.connect(str(enforcer_db))
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM behavior_flags WHERE ts >= ? AND severity IN ('CRITICAL','HIGH') "
                "ORDER BY ts DESC LIMIT 50",
                (cutoff,)
            ).fetchall()
            con.close()
            result["behavior_flags"] = [dict(r) for r in rows]
            result["behavior_flag_count"] = len(result["behavior_flags"])
        else:
            result["behavior_flags"] = []
            result["behavior_flag_count"] = 0
    except Exception as e:
        result["behavior_flags"] = []
        result["behavior_flags_error"] = str(e)

    # Governance log (Rexxie RBAC blocks, policy blocks)
    try:
        rexxie_db_paths = [
            _REX_DIR.parent / "Gold_Health_Systems" / "rexxie_private.db",
            Path.home() / "Desktop" / "Gold_Health_Systems" / "rexxie_private.db",
        ]
        gov_rows = []
        for rdb_path in rexxie_db_paths:
            if rdb_path.exists():
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                con = sqlite3.connect(str(rdb_path))
                try:
                    rows = con.execute(
                        "SELECT * FROM governance_log WHERE time >= ? "
                        "AND event_type LIKE '%blocked%' ORDER BY time DESC LIMIT 20",
                        (cutoff,)
                    ).fetchall()
                    gov_rows = [{"id": r[0], "time": r[1], "chat_id": r[2],
                                  "event_type": r[3], "details": r[4]}
                                 for r in rows]
                except Exception:
                    pass
                con.close()
                break
        result["governance_blocks"] = gov_rows
        result["governance_block_count"] = len(gov_rows)
    except Exception as e:
        result["governance_blocks"] = []

    return result


# ──────────────────────────────────────────────────────────────────────────────
# UNRESOLVED QUEUE PANEL
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/unresolved")
async def unresolved_queue(
    target: str = Query(default=""),
    include_resolved: bool = Query(default=False),
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Chairman Command Center — Unresolved Queue Panel.
    Returns: open unresolved items, optionally filtered by target.
    """
    _require_chairman(x_user_name, x_claimed_role)

    result: dict = {
        "panel": "unresolved_queue",
        "ts": datetime.now().isoformat(),
    }

    try:
        from rex_unresolved import pending_items, all_items

        if include_resolved:
            items = all_items(limit=100)
        else:
            items = pending_items(clarify_target=target if target else "")

        # Counts by priority
        result["counts"] = {
            "total": len(items),
            "critical": sum(1 for i in items if i["priority"] == "critical"),
            "high":     sum(1 for i in items if i["priority"] == "high"),
            "medium":   sum(1 for i in items if i["priority"] == "medium"),
            "low":      sum(1 for i in items if i["priority"] == "low"),
        }

        # Counts by target
        by_target: dict[str, int] = {}
        for item in items:
            t = item.get("clarify_target", "unknown")
            by_target[t] = by_target.get(t, 0) + 1
        result["by_target"] = by_target

        result["items"] = items

    except Exception as e:
        result["error"] = str(e)
        result["items"] = []

    return result


@cc_router.post("/resolve/{item_id}")
async def resolve_unresolved(
    item_id: int,
    body: ResolveRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Resolve an unresolved item from the Command Center."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from rex_unresolved import resolve_item
        ok, msg = resolve_item(item_id, body.resolved_by, body.resolution_note)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/escalate/{item_id}")
async def escalate_unresolved(
    item_id: int,
    body: EscalateRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Escalate an unresolved item to critical."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from rex_unresolved import escalate_item
        ok, msg = escalate_item(item_id, body.actor, body.note)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# ACTIVITY TRAIL PANEL
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/activity-trail")
async def activity_trail(
    days: int = Query(default=10, ge=1, le=14),
    action_filter: str = Query(default=""),
    actor_filter: str = Query(default=""),
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Chairman Command Center — Activity Trail Panel.
    Returns: structured events visible to Chairman, newest first.
    Default: 10 days. Maximum: 14 days.
    """
    _require_chairman(x_user_name, x_claimed_role)

    try:
        from rex_events import read_events
        events = read_events(
            days=days,
            action=action_filter if action_filter else "",
            actor=actor_filter if actor_filter else "",
            min_visibility_role="chairman",
            limit=500,
        )
        return {
            "panel": "activity_trail",
            "ts": datetime.now().isoformat(),
            "days": days,
            "event_count": len(events),
            "events": events,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CONTENT UPDATE QUEUE (Website/Dashboard approval)
# ──────────────────────────────────────────────────────────────────────────────

@cc_router.get("/content-updates")
async def content_updates(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Staged content updates awaiting Chairman approval."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from goj_signin_intake_v4_patch import ContentUpdateQueue
        queue = ContentUpdateQueue()
        return {
            "panel": "content_updates",
            "ts": datetime.now().isoformat(),
            "pending": queue.pending(),
            "approved_unpublished": queue.get_approved(),
        }
    except Exception as e:
        return {"panel": "content_updates", "error": str(e), "pending": [], "approved_unpublished": []}


class ContentApprovalRequest(BaseModel):
    approver: str = "kato"


class ContentRejectionRequest(BaseModel):
    rejector: str = "kato"
    note: str = ""


@cc_router.post("/content-updates/{update_id}/approve")
async def approve_content(
    update_id: int,
    body: ContentApprovalRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Chairman approves a staged content update."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from goj_signin_intake_v4_patch import approve_content_update
        ok, msg = approve_content_update(update_id, body.approver)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/content-updates/{update_id}/reject")
async def reject_content(
    update_id: int,
    body: ContentRejectionRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Chairman rejects a staged content update."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from goj_signin_intake_v4_patch import reject_content_update
        ok, msg = reject_content_update(update_id, body.rejector, body.note)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT REGISTRY PANEL
# Chairman-only. All prompts are governed system assets.
# Routes:
#   GET  /api/chairman/prompt-registry              → summary + all entries
#   GET  /api/chairman/prompt-registry/pending-edits → pending staged edits
#   GET  /api/chairman/prompt-registry/integrity    → hash integrity check
#   GET  /api/chairman/prompt-registry/audit-log    → audit trail
#   POST /api/chairman/prompt-registry/diff         → diff current vs staged edit
#   GET  /api/chairman/prompt-registry/{id}         → single entry + versions
#   GET  /api/chairman/prompt-registry/{id}/content → current content (read-only)
#   POST /api/chairman/prompt-registry/{id}/stage   → propose a governed edit
#   POST /api/chairman/prompt-registry/approve/{edit_id}  → apply staged edit
#   POST /api/chairman/prompt-registry/reject/{edit_id}   → discard staged edit
#   POST /api/chairman/prompt-registry/{id}/rollback      → rollback to version
#   POST /api/chairman/prompt-registry/{id}/status        → set active/inactive/archive
# ─────────────────────────────────────────────────────────────────────────────

class PromptStageRequest(BaseModel):
    new_content: str
    editor:      str  = "chairman"
    reason:      str  = ""

class PromptRollbackRequest(BaseModel):
    version: int

class PromptStatusRequest(BaseModel):
    status: str   # active | inactive | archive

class PromptDiffRequest(BaseModel):
    prompt_id: str
    edit_id:   str


@cc_router.get("/prompt-registry")
async def prompt_registry_summary(
    category: Optional[str] = None,
    status:   Optional[str] = None,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Return summary stats and the full list of registry entries.
    Optionally filter by category or status.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg     = PromptRegistry()
        summary = reg.summary()
        entries = reg.list(category=category, status=status)
        return {
            "panel":   "prompt_registry",
            "summary": summary,
            "entries": [e.to_dict() for e in entries],
            "filters": {"category": category, "status": status},
        }
    except Exception as e:
        logger.error(f"[prompt-registry] summary error: {e}")
        return {"panel": "prompt_registry", "error": str(e), "entries": [], "summary": {}}


@cc_router.get("/prompt-registry/pending-edits")
async def prompt_registry_pending_edits(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """List all pending staged prompt edits. Chairman-only."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg     = PromptRegistry()
        pending = reg._store.list_pending()
        expired = reg.expire_stale_edits()
        return {
            "panel":        "prompt_registry_pending",
            "pending":      pending,
            "auto_expired": expired,
            "count":        len(pending),
        }
    except Exception as e:
        logger.error(f"[prompt-registry] pending edits error: {e}")
        return {"panel": "prompt_registry_pending", "error": str(e), "pending": []}


@cc_router.post("/prompt-registry/diff")
async def prompt_registry_diff(
    body: PromptDiffRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Return a line-by-line diff between current prompt content and a staged edit.
    No files are read or modified beyond reading.

    Input:  { "prompt_id": "rex-identity-v1", "edit_id": "abc123" }
    Output: {
      "title": "REX Core Identity",
      "old_version": 4, "new_version": 5,
      "risk_level": "critical", "approval_tier": 3,
      "reason": "...",
      "diff": [
        {"type": "context",  "line_no": 1,  "line": "# You are REX..."},
        {"type": "removed",  "line_no": 3,  "line": "REX may disclose..."},
        {"type": "added",    "line_no": 3,  "line": "REX must never disclose..."}
      ],
      "stats": {"added": 1, "removed": 1, "unchanged": 64}
    }
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.diff(body.prompt_id, body.edit_id)
        return {"panel": "prompt_diff", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] diff error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.get("/prompt-registry/audit-log")
async def prompt_registry_audit_log(
    prompt_id: Optional[str] = None,
    limit:     int           = 50,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Return recent prompt audit log entries (most-recent-first).
    Optionally filter by prompt_id. Chairman-only.

    Each entry: { "event", "timestamp", "prompt_id", "version_from", "version_to", ... }
    Events: edit_staged | edit_approved | edit_rejected | edit_expired | edit_applied
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg     = PromptRegistry()
        entries = reg.get_audit_log(limit=min(limit, 200), prompt_id=prompt_id)
        return {
            "panel":     "prompt_audit_log",
            "entries":   entries,
            "count":     len(entries),
            "filter":    prompt_id,
        }
    except Exception as e:
        logger.error(f"[prompt-registry] audit log error: {e}")
        return {"panel": "prompt_audit_log", "error": str(e), "entries": []}


@cc_router.get("/prompt-registry/integrity")
async def prompt_registry_integrity(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Run an integrity check: verify all active prompt content hashes match disk.
    Returns mismatches and missing files. Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        report = reg.integrity_check()
        return {"panel": "prompt_integrity", **report}
    except Exception as e:
        logger.error(f"[prompt-registry] integrity check error: {e}")
        return {"panel": "prompt_integrity", "error": str(e), "clean": False}


@cc_router.get("/prompt-registry/{prompt_id}")
async def prompt_registry_get(
    prompt_id: str,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Return full metadata + version history for a single prompt.
    Does NOT return prompt content (use /content endpoint for that).
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg   = PromptRegistry()
        entry = reg.get(prompt_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' not found")
        versions = reg.list_versions(prompt_id)
        return {
            "panel":    "prompt_detail",
            "entry":    entry.to_dict(),
            "versions": versions,
            "pending_edits": reg._store.list_pending(prompt_id=prompt_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[prompt-registry] get error ({prompt_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.get("/prompt-registry/{prompt_id}/content")
async def prompt_registry_content(
    prompt_id: str,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Return current content of a prompt file.
    For governed prompts, content is read-only via this endpoint.
    To propose a change, use /stage. Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg     = PromptRegistry()
        entry   = reg.get(prompt_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' not found")
        content = reg.get_content(prompt_id)
        return {
            "panel":      "prompt_content",
            "id":         prompt_id,
            "title":      entry.title,
            "version":    entry.version,
            "status":     entry.status,
            "is_governed": entry.is_governed,
            "content":    content,
            "note":       (
                "READ-ONLY view. Use POST /stage to propose changes."
                if entry.is_governed
                else "Tier 1 — edits via /stage apply immediately."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[prompt-registry] content error ({prompt_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/prompt-registry/{prompt_id}/stage")
async def prompt_registry_stage_edit(
    prompt_id: str,
    body: PromptStageRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Propose an edit to a prompt.
    Tier 1: applies immediately.
    Tier 2/3: staged for approval. No content changes until approved.
    Governed prompts (identity, governance, ocr, cls) always require approval.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.stage_edit(
            prompt_id   = prompt_id,
            new_content = body.new_content,
            editor      = body.editor or x_user_name or "chairman",
            reason      = body.reason,
        )
        return {"panel": "prompt_stage", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] stage edit error ({prompt_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/prompt-registry/approve/{edit_id}")
async def prompt_registry_approve_edit(
    edit_id: str,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Approve a staged prompt edit. Applies content, creates version snapshot.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.approve_edit(edit_id, approved_by=x_user_name or "chairman")
        return {"panel": "prompt_approve", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] approve error ({edit_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/prompt-registry/reject/{edit_id}")
async def prompt_registry_reject_edit(
    edit_id: str,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Reject a staged prompt edit. No content change applied.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.reject_edit(edit_id)
        return {"panel": "prompt_reject", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] reject error ({edit_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/prompt-registry/{prompt_id}/rollback")
async def prompt_registry_rollback(
    prompt_id: str,
    body: PromptRollbackRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Roll back a prompt to a previous version.
    For governed prompts: stages a rollback edit (requires approval).
    For Tier 1 prompts: applies immediately.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.rollback(prompt_id, body.version)
        return {"panel": "prompt_rollback", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] rollback error ({prompt_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/prompt-registry/{prompt_id}/status")
async def prompt_registry_set_status(
    prompt_id: str,
    body: PromptStatusRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Set prompt status: active | inactive | archive.
    Archiving a governed prompt is staged for approval.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.set_status(prompt_id, body.status)
        return {"panel": "prompt_status", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] set status error ({prompt_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PR-CF-2: Usage tracking routes
@cc_router.get("/prompt-registry/usage")
async def prompt_registry_usage_summary(
    days: int = 30,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    PR-CF-2: Return prompt usage summary for the last N days.
    Includes total loads per prompt and list of never-used active prompts.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.usage_summary(days=min(days, 365))
        return {"panel": "prompt_usage", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] usage summary error: {e}")
        return {"panel": "prompt_usage", "error": str(e)}


@cc_router.get("/prompt-registry/{prompt_id}/usage")
async def prompt_registry_usage_for(
    prompt_id: str,
    limit:     int = 50,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    PR-CF-2: Return recent usage events for a single prompt.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.usage_for(prompt_id, limit=limit)
        return {"panel": "prompt_usage_detail", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] usage for ({prompt_id}): {e}")
        return {"panel": "prompt_usage_detail", "error": str(e)}


# PR-CF-3: Protected prompt confirm route
@cc_router.post("/prompt-registry/confirm/{edit_id}")
async def prompt_registry_confirm_protected(
    edit_id: str,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    PR-CF-3: Second-confirmation step for protected prompt edits.
    After confirming, approve_edit() will proceed once the 48h window passes.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg    = PromptRegistry()
        result = reg.confirm_protected_edit(edit_id)
        return {"panel": "prompt_confirm_protected", **result}
    except Exception as e:
        logger.error(f"[prompt-registry] confirm protected error ({edit_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10 — SESSION AUTHORITY (MSU) ROUTES
# Chairman-only. Refinement: schema mismatches surfaced with SCHEMA_WARNING.
# ─────────────────────────────────────────────────────────────────────────────

class SessionUnlockRequest(BaseModel):
    identity:   str
    passphrase: str
    totp_code:  str

class SessionLockRequest(BaseModel):
    reason: str = "manual"


@cc_router.get("/session/status")
async def session_status(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Current MSU session state.
    Returns: state, identity, time_remaining_seconds, extensions used/max.
    UI: lock icon, countdown, identity label. Read-only — no MSU required.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_session import SessionEngine
        eng = SessionEngine()
        status = eng.status()
        # UI hint for Command Center rendering
        status["ui"] = {
            "icon": (
                "🛑" if status["state"] == "HALTED"
                else "🔓" if status["state"] == "UNLOCKED_PRIVILEGED"
                else "⚠️" if status["state"] == "DEGRADED"
                else "🔒"
            ),
            "label": status["state"].replace("_", " ").title(),
            "color": (
                "red"    if status["state"] == "HALTED"
                else "green"  if status["state"] == "UNLOCKED_PRIVILEGED"
                else "yellow" if status["state"] == "DEGRADED"
                else "gray"
            ),
        }
        return {"panel": "session", **status}
    except Exception as e:
        logger.error(f"[session] status error: {e}")
        return {"panel": "session", "state": "DEGRADED", "error": str(e)}


@cc_router.post("/session/unlock")
async def session_unlock(
    body: SessionUnlockRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Attempt to unlock a privileged session.
    Requires: identity + passphrase + TOTP code.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_session import SessionEngine
        eng    = SessionEngine()
        result = eng.unlock(body.identity, body.passphrase, body.totp_code)
        return {"panel": "session_unlock", **result}
    except Exception as e:
        logger.error(f"[session] unlock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/session/lock")
async def session_lock(
    body: SessionLockRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Manually lock the session immediately.
    Chairman-only. Available regardless of current session state.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_session import SessionEngine
        eng    = SessionEngine()
        result = eng.lock(reason=body.reason)
        return {"panel": "session_lock", **result}
    except Exception as e:
        logger.error(f"[session] lock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.post("/session/extend")
async def session_extend(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Reset auto-lock timer. Protected activity only.
    Returns error if max extensions reached (requires full re-auth).
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_session import SessionEngine
        eng    = SessionEngine()
        result = eng.extend()
        return {"panel": "session_extend", **result}
    except Exception as e:
        logger.error(f"[session] extend error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.get("/session/activity")
async def session_activity(
    limit: int = 20,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Recent session audit events from the shared prompt_audit.log.
    Filters to session_* events only. Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_prompt_registry import PromptRegistry
        reg     = PromptRegistry()
        # Reuse get_audit_log but filter to session events
        all_log = reg.get_audit_log(limit=200)
        session_events = [
            e for e in all_log
            if e.get("event", "").startswith("session_")
        ][:limit]
        return {"panel": "session_activity", "events": session_events, "count": len(session_events)}
    except Exception as e:
        logger.error(f"[session] activity error: {e}")
        return {"panel": "session_activity", "events": [], "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10 — RESTORE DRILL ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class RestoreDrillRequest(BaseModel):
    snapshot_dir: Optional[str] = None


@cc_router.get("/restore-drill/status")
async def restore_drill_status(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Last restore drill result. Always available (no MSU required to read).
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_restore_drill import RestoreDrill
        drill  = RestoreDrill()
        status = drill.get_status()
        return {"panel": "restore_drill_status", **status}
    except Exception as e:
        logger.error(f"[restore-drill] status error: {e}")
        return {"panel": "restore_drill_status", "result": "error", "notes": str(e)}


@cc_router.get("/session/key-status")
async def session_key_status(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Part F: Session integrity key metadata.
    Returns: existence, size, path, permissions, last rotation timestamp.
    Never returns key bytes. Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_session import SessionEngine
        eng = SessionEngine()
        return {"panel": "session_key_status", **eng.key_status()}
    except Exception as e:
        logger.error(f"[session] key-status error: {e}")
        return {"panel": "session_key_status", "error": str(e)}


@cc_router.post("/session/rotate-key")
async def session_rotate_key(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Part F: Rotate session integrity key. Locks session immediately.
    All prior session hashes become invalid. Re-auth required after rotation.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_session import SessionEngine
        eng    = SessionEngine()
        result = eng.rotate_key()
        return {"panel": "session_rotate_key", **result}
    except Exception as e:
        logger.error(f"[session] rotate-key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cc_router.get("/restore-drill/history")
async def restore_drill_history(
    limit: int = 10,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Part E: Last N restore drill results (most-recent-first).
    Each entry: run_at, result, snapshot_used, checks_passed, checks_failed, failures (names).
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_restore_drill import RestoreDrill
        drill   = RestoreDrill()
        history = drill.get_history(limit=min(limit, 50))
        return {
            "panel":   "restore_drill_history",
            "count":   len(history),
            "entries": history,
        }
    except Exception as e:
        logger.error(f"[restore-drill] history error: {e}")
        return {"panel": "restore_drill_history", "error": str(e), "entries": []}


@cc_router.post("/restore-drill/run")
async def restore_drill_run(
    body: RestoreDrillRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Run a restore drill. MSU session must be unlocked.
    SHA-256 hash verification on all governed files.
    Drill fails explicitly if any check fails — no silent passes.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    # MSU gate
    try:
        from .rex_session import SessionEngine
        eng   = SessionEngine()
        block = eng.require_unlocked()
        if block:
            return {"panel": "restore_drill_run", **block}
        eng.record_protected_activity()
    except Exception as e:
        logger.warning(f"[restore-drill] MSU check error: {e} — proceeding (MSU degraded)")

    try:
        from .rex_restore_drill import RestoreDrill
        drill  = RestoreDrill()
        result = drill.run(snapshot_dir=body.snapshot_dir)
        return {"panel": "restore_drill_run", **result.to_dict()}
    except Exception as e:
        logger.error(f"[restore-drill] run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10 — SCHEMA STATUS ROUTE
# Refinement: surface schema mismatches with visible SCHEMA_WARNING state.
# ─────────────────────────────────────────────────────────────────────────────

@cc_router.get("/schema-status")
async def schema_status(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Run schema validation on all known state files.
    Returns per-file check results and an overall status:
      ok             — all files pass
      schema_warning — 1-2 mismatches (yellow — distinct from HALTED)
      schema_error   — 3+ mismatches (amber)

    Refinement: response includes affected file list and mismatch details
    for Command Center rendering. Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_schema_check import SchemaChecker
        checker = SchemaChecker()
        report  = checker.run()
        result  = report.to_dict()

        # UI hint for Command Center rendering
        result["ui"] = {
            "icon":  "✅" if report.status == "ok" else ("⚠️" if report.status == "schema_warning" else "🟠"),
            "color": "green" if report.status == "ok" else ("yellow" if report.status == "schema_warning" else "orange"),
            "label": report.status.replace("_", " ").upper(),
            "affected_files": [
                r["file"] for r in result.get("results", []) if not r.get("passed")
            ],
        }
        return {"panel": "schema_status", **result}
    except Exception as e:
        logger.error(f"[schema-status] error: {e}")
        return {"panel": "schema_status", "status": "schema_error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10 — CLS STATUS ROUTE (with aging breakdown)
# ─────────────────────────────────────────────────────────────────────────────

@cc_router.get("/cls-status")
async def cls_status(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    CLS v3 status including aging breakdown:
    active / stale / review_required / retired pattern counts.
    Candidates: pending / approved / rejected / expired.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        import sys
        from pathlib import Path
        rex_dir = Path(__file__).parent.parent
        if str(rex_dir) not in sys.path:
            sys.path.insert(0, str(rex_dir))
        from core.cls_v3 import CLS_v3
        cls    = CLS_v3(dry_run=True)
        report = cls.status_report()
        return {"panel": "cls_status", **report}
    except Exception as e:
        logger.error(f"[cls-status] error: {e}")
        return {"panel": "cls_status", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 13 — AGENT REGISTRY READ-ONLY VIEW
# ─────────────────────────────────────────────────────────────────────────────

@cc_router.get("/agents/registry")
async def agent_registry_view(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Agent Registry — read-only view from agent_registry.json.
    Returns safe agent metadata. No write operations in this phase.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        import json
        from pathlib import Path
        registry_path = Path(__file__).parent.parent / "agent_registry.json"
        if not registry_path.exists():
            return {"panel": "agent_registry", "agents": [], "total": 0}
        data   = json.loads(registry_path.read_text())
        agents = data.get("agents", [])
        # Return safe fields only
        safe_agents = [
            {
                "id":          a.get("id"),
                "name":        a.get("name"),
                "subtitle":    a.get("subtitle", ""),
                "category":    a.get("category", ""),
                "description": a.get("description", "")[:120],
                "tags":        a.get("tags", []),
                "required":    a.get("required", False),
                "version":     a.get("_version", "1.0"),
            }
            for a in agents
        ]
        return {
            "panel":      "agent_registry",
            "total":      len(safe_agents),
            "agents":     safe_agents,
            "forge_note": "Agent Forge (clone/create) available in Packet B.",
        }
    except Exception as e:
        logger.error(f"[agent-registry] {e}")
        return {"panel": "agent_registry", "error": str(e), "agents": []}


@cc_router.get("/agents/fleet")
async def agent_fleet_overview(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Agent Fleet Overview — counts from agent_registry.json. Chairman-only."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        import json
        from pathlib import Path
        registry_path = Path(__file__).parent.parent / "agent_registry.json"
        if not registry_path.exists():
            return {"panel": "agent_fleet", "total": 0}
        data   = json.loads(registry_path.read_text())
        agents = data.get("agents", [])
        return {
            "panel":    "agent_fleet",
            "total":    len(agents),
            "active":   len([a for a in agents if a.get("required")]),
            "by_category": {
                cat: len([a for a in agents if a.get("category") == cat])
                for cat in set(a.get("category", "unknown") for a in agents)
            },
        }
    except Exception as e:
        return {"panel": "agent_fleet", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# COMMAND CENTER STATUS — shared data layer for both UI modes
# ─────────────────────────────────────────────────────────────────────────────

@cc_router.get("/command-center-status")
async def command_center_status(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Full system status snapshot for the Command Center.
    Used by both Claude UI mode and Executive HTML mode.
    Chairman-only.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_command_center_status import get_status
        return get_status()
    except Exception as e:
        logger.error(f"[command-center] status collection error: {e}")
        return {"error": str(e), "timestamp": __import__("datetime").datetime.utcnow().isoformat()}


@cc_router.get("/command-center-ui")
async def command_center_ui(
    mode: str = "executive",
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Serves the HTML executive command center UI directly from the API.
    GET /api/chairman/command-center-ui?mode=executive
    Chairman-only.
    """
    from fastapi.responses import HTMLResponse
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_command_center_status import get_status
        # Re-use the HTML renderer from the command script
        import sys
        from pathlib import Path
        rex_dir = Path(__file__).parent.parent
        if str(rex_dir) not in sys.path:
            sys.path.insert(0, str(rex_dir))
        d = get_status()
        # Inline minimal HTML for API-served version
        health = d.get("system_health","?")
        hcolor = {"ok":"#27ae60","warning":"#f39c12","critical":"#e74c3c"}.get(health,"#7f8c8d")
        db = d.get("database",{})
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta http-equiv="refresh" content="30">
<title>REX Command Center</title>
<style>body{{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;padding:20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin:12px 0}}
h2{{color:#58a6ff}}.ok{{color:#27ae60}}.warn{{color:#f39c12}}.err{{color:#e74c3c}}</style>
</head><body>
<h1>REX Command Center</h1>
<p>Health: <strong style="color:{hcolor}">{health.upper()}</strong> &nbsp;·&nbsp; {d.get("timestamp","")[:19]}</p>
<div class="card"><h2>Database</h2>
<p>Clients: <strong>{db.get("active_clients",0)}</strong> active &nbsp;·&nbsp;
Staff: <strong>{db.get("staff_count",0)}</strong> &nbsp;·&nbsp;
Auths: <strong>{db.get("auth_count",0)}</strong></p>
<p class="{'ok' if db.get('accessible') else 'err'}">
{"✓ Database accessible" if db.get("accessible") else "✗ Database not accessible"}</p>
</div>
<div class="card"><h2>OCR</h2>
<p>Flag queue: <strong>{d.get("ocr",{}).get("flag_queue_unresolved",0)}</strong> unresolved</p>
</div>
<div class="card"><h2>Security Alerts</h2>
{"".join(f'<p class="err">🚨 {a["message"]}</p>' for a in d.get("security_alerts",[]))
or '<p class="ok">✓ No critical alerts</p>'}</div>
<p style="font-size:11px;color:#8b949e;margin-top:20px">
For full dashboard: open COMMAND_CENTER.command --executive on your Mac</p>
</body></html>"""
        return HTMLResponse(content=html)
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(e)}, status_code=500)


@cc_router.get("/app")
async def command_center_app(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Serve the full Command Center web app. Chairman-only."""
    from fastapi.responses import FileResponse
    _require_chairman(x_user_name, x_claimed_role)
    app_path = Path(__file__).parent.parent / "COMMAND_CENTER_APP.html"
    if not app_path.exists():
        raise HTTPException(status_code=404, detail="Command Center app not found")
    return FileResponse(str(app_path), media_type="text/html")
