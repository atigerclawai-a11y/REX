"""
backend/rex_executive.py — Executive Interface API
════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 7 · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  Provides FastAPI routes for the Executive Interface.
  Accessible to admin_financial (Vlad) and finance (Allen) roles.

  This is NOT the Chairman Command Center.
  This surface does NOT include:
    • Chairman-only controls
    • Security override capabilities
    • Rexxie private data
    • Command-center-only powers (red-flag panel, full unresolved queue)
    • Other users' permission management

  This surface DOES include:
    • Finance/admin oversight within their scope
    • Receipt views filtered by role and scope
    • Reports within scope
    • Operational summaries within scope
    • Limited clarification response (can answer clarifications directed to them)

MOUNT IN backend/main.py:
    from .rex_executive import exec_router
    app.include_router(exec_router, prefix="/api/executive")

ROLES WITH ACCESS:
  • admin_financial (Vlad) — receipts, reports, staff summaries, activity
  • finance (Allen) — receipts, financial reports, bookkeeping summaries
  • chairman (Kato) — always has access (but typically uses Command Center instead)

ACCESS DENIED (403) FOR:
  • staff, admin_operations, viewer, guest, none
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

exec_router = APIRouter(tags=["Executive Interface"])

_REX_DIR = Path.home() / "Desktop" / "REX"

EXEC_ROLES = {"chairman", "admin_financial", "finance"}


# ──────────────────────────────────────────────────────────────────────────────
# AUTH GUARD
# ──────────────────────────────────────────────────────────────────────────────

def _require_executive(
    x_user_name: Optional[str],
    x_claimed_role: Optional[str],
) -> str:
    """
    Verify executive access. Returns verified user_name on success.
    Raises HTTPException(403) if not executive-level or above.
    """
    try:
        from .rex_role_auth import verify_role
        verified = verify_role(x_user_name or "", x_claimed_role or "")
        if verified not in EXEC_ROLES:
            raise HTTPException(status_code=403, detail="Access denied.")
        return x_user_name or ""
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[exec] Auth check error: {e}")
        raise HTTPException(status_code=403, detail="Access denied.")


def _get_role(user_name: str) -> str:
    """Get the user's normalised role."""
    try:
        from rex_permissions import get_perms
        return get_perms().get_role(user_name)
    except Exception:
        return "none"


# ──────────────────────────────────────────────────────────────────────────────
# RECEIPTS (SCOPED BY ROLE)
# ──────────────────────────────────────────────────────────────────────────────

@exec_router.get("/receipts")
async def executive_receipts(
    days: int = Query(default=30, ge=1, le=365),
    submitter: str = Query(default=""),
    category:  str = Query(default=""),
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Executive receipt view — filtered by role and scope.
    Financial totals visible to admin_financial and finance only.
    """
    user_name = _require_executive(x_user_name, x_claimed_role)
    role = _get_role(user_name)

    result: dict = {
        "panel": "receipts",
        "ts": datetime.now().isoformat(),
        "user": user_name,
        "role": role,
        "days": days,
    }

    ledger_db = _REX_DIR / "data" / "rex_ledger.db"
    if not ledger_db.exists():
        result["receipts"] = []
        result["note"] = "Receipt ledger not found"
        return result

    try:
        con = sqlite3.connect(str(ledger_db))
        con.row_factory = sqlite3.Row
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        clauses = ["receipt_date >= ?", "deleted = 0"]
        params: list = [cutoff]
        if submitter:
            clauses.append("submitted_by = ?")
            params.append(submitter)
        if category:
            clauses.append("LOWER(category) = ?")
            params.append(category.lower())

        where = " AND ".join(clauses)
        rows = con.execute(
            f"SELECT * FROM receipts WHERE {where} ORDER BY receipt_date DESC LIMIT 200",
            params
        ).fetchall()
        con.close()

        # Apply visibility gate
        try:
            from rex_receipt_manager_v4_patch import ReceiptVisibilityGate
            gate = ReceiptVisibilityGate()
            receipts = gate.filter_receipts(
                [dict(r) for r in rows],
                user_label=user_name,
            )
        except Exception:
            # Fallback: manual field filtering
            receipts = _manual_filter_receipts(rows, role)

        result["receipts"] = receipts
        result["receipt_count"] = len(receipts)

        # Totals only for financial roles
        if role in ("chairman", "admin_financial", "finance"):
            total = sum(r.get("amount") or 0 for r in receipts if r.get("amount") is not None)
            result["total_amount"] = round(total, 2)

    except Exception as e:
        result["error"] = str(e)
        result["receipts"] = []

    return result


def _manual_filter_receipts(rows, role: str) -> list[dict]:
    """Simple field filter without full visibility gate."""
    financial_roles = {"chairman", "admin_financial", "finance"}
    safe_fields = {
        "id", "receipt_date", "vendor", "category", "submitted_by",
        "description", "logged_at", "review_status",
    }
    result = []
    for row in rows:
        d = dict(row)
        if role not in financial_roles:
            d = {k: v for k, v in d.items() if k in safe_fields}
        result.append(d)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# REPORTS / SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

@exec_router.get("/summary")
async def executive_summary(
    days: int = Query(default=30, ge=1, le=365),
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Executive operational summary.
    Returns spending overview, category breakdown, pending approvals.
    """
    user_name = _require_executive(x_user_name, x_claimed_role)
    role = _get_role(user_name)

    result: dict = {
        "panel": "summary",
        "ts": datetime.now().isoformat(),
        "user": user_name,
        "role": role,
        "days": days,
    }

    ledger_db = _REX_DIR / "data" / "rex_ledger.db"
    if ledger_db.exists():
        try:
            con = sqlite3.connect(str(ledger_db))
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            if role in ("chairman", "admin_financial", "finance"):
                # Full financial summary
                total_row = con.execute(
                    "SELECT COUNT(*), SUM(amount) FROM receipts "
                    "WHERE receipt_date >= ? AND deleted=0",
                    (cutoff,)
                ).fetchone()
                result["receipt_count"] = total_row[0]
                result["total_spend"]   = round(total_row[1] or 0, 2)

                by_cat = con.execute(
                    "SELECT category, COUNT(*), SUM(amount) FROM receipts "
                    "WHERE receipt_date >= ? AND deleted=0 "
                    "GROUP BY category ORDER BY SUM(amount) DESC",
                    (cutoff,)
                ).fetchall()
                result["by_category"] = [
                    {"category": r[0], "count": r[1], "total": round(r[2] or 0, 2)}
                    for r in by_cat
                ]

                # Pending reviews
                try:
                    needs_review = con.execute(
                        "SELECT COUNT(*) FROM receipts "
                        "WHERE review_status='needs_review' AND deleted=0",
                    ).fetchone()[0]
                    result["pending_review_count"] = needs_review
                except Exception:
                    pass

            con.close()
        except Exception as e:
            result["ledger_error"] = str(e)

    # Recent events visible to this role
    try:
        from rex_events import read_events
        result["recent_events"] = read_events(
            days=min(days, 7),
            min_visibility_role=role,
            limit=30,
        )
    except Exception:
        result["recent_events"] = []

    return result


# ──────────────────────────────────────────────────────────────────────────────
# CLARIFICATION RESPONSES (Vlad/Allen can answer their own)
# ──────────────────────────────────────────────────────────────────────────────

@exec_router.get("/my-clarifications")
async def my_clarifications(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Return open clarifications directed to this user."""
    user_name = _require_executive(x_user_name, x_claimed_role)

    try:
        from rex_clarification import pending_clarifications
        items = pending_clarifications(target=user_name)
        return {
            "user": user_name,
            "open_clarifications": items,
            "count": len(items),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ClarificationAnswerRequest(BaseModel):
    answer: str


@exec_router.post("/answer-clarification/{item_id}")
async def answer_clarification(
    item_id: int,
    body: ClarificationAnswerRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Executive user answers a clarification directed to them."""
    user_name = _require_executive(x_user_name, x_claimed_role)

    try:
        # Verify the item is actually for this user (no cross-target access)
        from rex_unresolved import get_item
        from rex_clarification import mark_answered
        item = get_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Item #{item_id} not found.")

        role = _get_role(user_name)
        if item.get("clarify_target") != user_name and role != "chairman":
            raise HTTPException(
                status_code=403,
                detail=f"This clarification is not directed to you."
            )

        ok, msg = mark_answered(item_id, user_name, body.answer)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
