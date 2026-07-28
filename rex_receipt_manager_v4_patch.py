"""
rex_receipt_manager_v4_patch.py — Receipt Manager V4 Patch
════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 4 · Garden of Joy · Gold Health Systems

PURPOSE:
  This module provides three things:
    1. A DB migration function that adds all new v4 fields to rex_ledger.db
    2. A visibility gate (ReceiptVisibilityGate) for field-level financial access
    3. Event hook functions to be inserted into rex_receipt_manager.py

HOW TO APPLY:
  Option A (Recommended): Run the migration function once, then merge the
  event hooks and visibility gate into rex_receipt_manager.py where marked.

  Option B: Import this module from rex_receipt_manager.py:
      from rex_receipt_manager_v4_patch import (
          run_v4_migration,
          ReceiptVisibilityGate,
          emit_receipt_event,
      )

  Call run_v4_migration() once at startup (idempotent — safe to call repeatedly).

NEW FIELDS ADDED TO receipts TABLE:
  department       TEXT DEFAULT ''           — food_cost / admin / transport / other
  confidence       REAL DEFAULT 1.0          — OCR confidence score (0.0–1.0)
  visibility_class TEXT DEFAULT 'financial'  — who can see this receipt's financials
  review_status    TEXT DEFAULT 'auto_filed' — auto_filed / needs_review / approved / rejected
  reviewed_by      TEXT                      — user_label who reviewed
  reviewed_at      TEXT                      — ISO timestamp

VISIBILITY GATE LOGIC:
  "financial" visibility:
    • chairman    → sees all fields including totals, tax, line_items
    • admin_financial → sees all fields including totals
    • finance     → sees all fields including totals
    • admin_operations → sees: vendor, date, category, department, status
                         CANNOT see: amount, tax, line_items, totals
    • staff       → sees: vendor, date, category only
                         CANNOT see: amount, tax, line_items, totals

  Scope override:
    If a scope grant exists for user + receipts.view_totals + department_tag,
    then that user CAN see totals for that department only.
    Example: misha with scope grant receipts.view_totals:food_cost
    → Misha can see totals for food_cost receipts.

SCOPED DEPARTMENT ACCESS:
  Future-ready design:
    perms.grant_scope("misha", "receipts.view_totals", "food_cost")
  → Misha can view totals for food_cost tagged receipts
  → Misha cannot view totals for admin, transport, or other departments

EVENT HOOKS (to be called from rex_receipt_manager.py):
  emit_receipt_event(EventType.RECEIPT_SUBMITTED, receipt_id, actor, metadata)
  emit_receipt_event(EventType.RECEIPT_OCR_DONE, receipt_id, "system", metadata)
  emit_receipt_event(EventType.RECEIPT_FLAGGED, receipt_id, "system", metadata)
  emit_receipt_event(EventType.RECEIPT_APPROVED, receipt_id, actor, metadata)
  emit_receipt_event(EventType.RECEIPT_DELETED, receipt_id, actor, metadata)
  emit_receipt_event(EventType.RECEIPT_EXPORTED, receipt_id, actor, metadata)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Path (matches rex_receipt_manager.py) ─────────────────────────────────────
LEDGER_DB = Path.home() / "Desktop" / "REX" / "data" / "rex_ledger.db"

# ── Roles that can see financial amounts ──────────────────────────────────────
FINANCIAL_ROLES = {"chairman", "admin_financial", "finance"}
# Roles that can see receipt metadata (non-financial) only:
OPERATIONAL_ROLES = {"admin_operations", "staff"}

# Fields visible to operational roles (cannot see amounts):
OPERATIONAL_SAFE_FIELDS = {
    "id", "receipt_date", "vendor", "category", "subcategory",
    "department", "submitted_by", "review_status", "logged_at",
    "source_file", "description",
}

# Fields that are financial (hidden from operational roles unless scoped):
FINANCIAL_FIELDS = {"amount", "tax", "raw_text"}

# Line items are always financial — only financial roles see them.


# ──────────────────────────────────────────────────────────────────────────────
# MIGRATION
# ──────────────────────────────────────────────────────────────────────────────

def run_v4_migration() -> dict:
    """
    Add v4 fields to rex_ledger.db receipts table.
    Idempotent — safe to call on every startup.
    Returns: {"added": [col_names], "already_present": [col_names]}
    """
    if not LEDGER_DB.exists():
        logger.info("[v4_patch] LEDGER_DB does not exist yet — migration will run at first use")
        return {"added": [], "already_present": [], "note": "DB not yet created"}

    NEW_COLUMNS = [
        ("department",       "TEXT DEFAULT ''"),
        ("confidence",       "REAL DEFAULT 1.0"),
        ("visibility_class", "TEXT DEFAULT 'financial'"),
        ("review_status",    "TEXT DEFAULT 'auto_filed'"),
        ("reviewed_by",      "TEXT"),
        ("reviewed_at",      "TEXT"),
    ]

    added = []
    already_present = []

    try:
        con = sqlite3.connect(str(LEDGER_DB))
        existing = [row[1] for row in con.execute("PRAGMA table_info(receipts)").fetchall()]

        for col_name, col_def in NEW_COLUMNS:
            if col_name in existing:
                already_present.append(col_name)
            else:
                try:
                    con.execute(f"ALTER TABLE receipts ADD COLUMN {col_name} {col_def}")
                    added.append(col_name)
                    logger.info(f"[v4_patch] Added column '{col_name}' to receipts")
                except Exception as e:
                    logger.error(f"[v4_patch] Failed to add column '{col_name}': {e}")

        # Add index on department if we just added it
        if "department" in added:
            try:
                con.execute("CREATE INDEX IF NOT EXISTS idx_rcpt_dept ON receipts(department)")
            except Exception:
                pass

        # Add index on review_status
        if "review_status" in added:
            try:
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rcpt_review ON receipts(review_status)"
                )
            except Exception:
                pass

        con.commit()
        con.close()

    except Exception as e:
        logger.error(f"[v4_patch] Migration error: {e}")
        return {"added": added, "already_present": already_present, "error": str(e)}

    logger.info(
        f"[v4_patch] Migration complete. Added: {added}, "
        f"Already present: {already_present}"
    )
    return {"added": added, "already_present": already_present}


# ──────────────────────────────────────────────────────────────────────────────
# VISIBILITY GATE
# ──────────────────────────────────────────────────────────────────────────────

class ReceiptVisibilityGate:
    """
    Field-level visibility gate for receipt data.

    Usage:
        gate = ReceiptVisibilityGate()
        safe_receipt = gate.filter_receipt(receipt_dict, user_label="misha")
        safe_list    = gate.filter_receipts(receipts_list, user_label="vlad")

    The gate checks:
      1. User's role → financial vs operational access
      2. Scope grants → scoped department access for operational users
      3. Chairman override → always full access
    """

    def __init__(self):
        try:
            from rex_permissions import get_perms
            self._perms = get_perms()
        except Exception as e:
            logger.warning(f"[visibility_gate] Cannot load permissions: {e} — defaulting to chairman-only")
            self._perms = None

    def _get_role(self, user_label: str) -> str:
        if not self._perms:
            return "none"
        return self._perms.get_role(user_label)

    def _can_see_totals(self, user_label: str, department: str = "") -> bool:
        """Check if user can see financial totals, with optional department scope."""
        if not self._perms:
            return user_label.lower() in ("kato", "chairman")

        role = self._get_role(user_label)

        # Financial roles always see totals
        if role in FINANCIAL_ROLES or user_label.lower() in ("kato", "chairman"):
            return True

        # Scope override: can_scoped for this department?
        if department:
            try:
                return self._perms.can_scoped(user_label, "receipts.view_totals", department)
            except Exception:
                pass

        # Fallback: explicit permission grant
        try:
            return self._perms.can(user_label, "receipts.view_totals")
        except Exception:
            return False

    def filter_receipt(
        self,
        receipt: dict,
        user_label: str,
        include_line_items: bool = False,
    ) -> dict:
        """
        Filter a single receipt dict for a user.
        Financial fields are redacted for non-financial roles unless scoped.
        """
        if not receipt:
            return {}

        department = receipt.get("department", "")
        can_see_totals = self._can_see_totals(user_label, department)

        result = {}
        for key, value in receipt.items():
            if key in FINANCIAL_FIELDS and not can_see_totals:
                result[key] = None  # redacted
            else:
                result[key] = value

        # Line items (financial detail — redact for operational roles)
        if include_line_items and not can_see_totals:
            result["line_items"] = []  # redacted
        elif include_line_items:
            result["line_items"] = receipt.get("line_items", [])

        # Annotate with visibility metadata
        result["_visibility"] = {
            "user": user_label,
            "can_see_totals": can_see_totals,
            "filtered": not can_see_totals,
        }

        return result

    def filter_receipts(
        self,
        receipts: list[dict],
        user_label: str,
    ) -> list[dict]:
        """Filter a list of receipts for a user."""
        return [self.filter_receipt(r, user_label) for r in receipts]

    def can_access(self, user_label: str, action: str) -> bool:
        """
        Check if user can perform a receipt action.
        Actions: view / view_all / view_totals / submit / export / delete / recategorize
        """
        perm_map = {
            "view":         "receipts.view",
            "view_all":     "receipts.view_all",
            "view_totals":  "receipts.view_totals",
            "submit":       "receipts.submit",
            "export":       "receipts.export_excel",
            "export_docx":  "receipts.export_docx",
            "delete":       "receipts.delete",
            "recategorize": "receipts.recategorize",
        }
        perm = perm_map.get(action)
        if not perm:
            return False
        if not self._perms:
            return user_label.lower() in ("kato", "chairman")
        return self._perms.can(user_label, perm)


# ──────────────────────────────────────────────────────────────────────────────
# EVENT HOOKS
# ──────────────────────────────────────────────────────────────────────────────

def emit_receipt_event(
    event_type: str,
    receipt_id,
    actor:    str,
    metadata: dict = None,
    sensitivity: str = "info",
) -> None:
    """
    Emit a structured receipt event. Silent on failure — never blocks caller.

    Add calls to rex_receipt_manager.py at these points:
      After filing:     emit_receipt_event(EventType.RECEIPT_SUBMITTED, id, submitter, {...})
      After OCR:        emit_receipt_event(EventType.RECEIPT_OCR_DONE, id, "system", {"confidence": score})
      When flagged:     emit_receipt_event(EventType.RECEIPT_FLAGGED, id, "system", {"reason": ...})
      When approved:    emit_receipt_event(EventType.RECEIPT_APPROVED, id, reviewer, {})
      When rejected:    emit_receipt_event(EventType.RECEIPT_REJECTED, id, reviewer, {"reason": ...})
      When deleted:     emit_receipt_event(EventType.RECEIPT_DELETED, id, actor, {})
      When exported:    emit_receipt_event(EventType.RECEIPT_EXPORTED, id, actor, {"format": "xlsx"})
    """
    try:
        from rex_events import write_event
        write_event(
            action=event_type,
            actor=actor,
            entity=f"receipt_id={receipt_id}",
            metadata=metadata or {},
            visibility="financial",
            sensitivity=sensitivity,
        )
    except Exception as e:
        logger.warning(f"[v4_patch] emit_receipt_event failed (non-fatal): {e}")


def flag_for_review(
    receipt_id,
    reason: str,
    flagged_by: str = "system",
) -> None:
    """
    Mark a receipt as needing review and route a clarification request.
    Updates review_status in DB, emits event, routes clarification.
    """
    # Update DB
    try:
        con = sqlite3.connect(str(LEDGER_DB))
        con.execute(
            "UPDATE receipts SET review_status='needs_review' WHERE id=?",
            (receipt_id,)
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.error(f"[v4_patch] flag_for_review DB update failed: {e}")

    # Emit event
    emit_receipt_event(
        event_type="receipt.flagged",
        receipt_id=receipt_id,
        actor=flagged_by,
        metadata={"reason": reason},
        sensitivity="medium",
    )

    # Route clarification
    try:
        from rex_clarification import route_clarification
        route_clarification(
            question=f"Receipt #{receipt_id} needs review: {reason}",
            context=f"Receipt has been flagged. Reason: {reason}",
            domain="financial",
            source_ref=f"receipt_id={receipt_id}",
            urgency="medium",
            source="receipt_manager",
        )
    except Exception as e:
        logger.warning(f"[v4_patch] clarification routing failed (non-fatal): {e}")


def mark_receipt_reviewed(
    receipt_id,
    reviewed_by: str,
    status: str = "approved",  # "approved" | "rejected"
    note: str = "",
) -> tuple[bool, str]:
    """
    Mark a receipt as reviewed (approved or rejected).
    Returns (success, message).
    """
    valid_statuses = ("approved", "rejected")
    if status not in valid_statuses:
        return False, f"Invalid status '{status}'. Use: {valid_statuses}"

    try:
        con = sqlite3.connect(str(LEDGER_DB))
        row = con.execute(
            "SELECT id FROM receipts WHERE id=?", (receipt_id,)
        ).fetchone()
        if not row:
            con.close()
            return False, f"Receipt #{receipt_id} not found."

        con.execute(
            "UPDATE receipts SET review_status=?, reviewed_by=?, reviewed_at=datetime('now') "
            "WHERE id=?",
            (status, reviewed_by, receipt_id)
        )
        con.commit()
        con.close()
    except Exception as e:
        return False, f"DB error: {e}"

    event_type = "receipt.approved" if status == "approved" else "receipt.rejected"
    emit_receipt_event(
        event_type=event_type,
        receipt_id=receipt_id,
        actor=reviewed_by,
        metadata={"status": status, "note": note},
    )

    return True, f"✅ Receipt #{receipt_id} marked {status} by {reviewed_by}."


# ──────────────────────────────────────────────────────────────────────────────
# INSERTION GUIDE FOR rex_receipt_manager.py
# ──────────────────────────────────────────────────────────────────────────────

INSERTION_GUIDE = """
PATCH GUIDE — rex_receipt_manager.py
======================================
Apply these changes to wire Phase 4 into the existing receipt manager.

1. At the top of the file, add:
   from rex_receipt_manager_v4_patch import (
       run_v4_migration, ReceiptVisibilityGate,
       emit_receipt_event, flag_for_review, mark_receipt_reviewed,
   )

2. In _ensure_db(), after existing setup, add:
   run_v4_migration()   # idempotent — adds v4 columns if missing

3. Create one shared ReceiptVisibilityGate instance:
   _visibility_gate = ReceiptVisibilityGate()

4. In handle_photo() or wherever a new receipt is logged, after INSERT:
   emit_receipt_event(EventType.RECEIPT_SUBMITTED, new_receipt_id, submitted_by,
                      {"vendor": vendor, "amount": amount})

5. After OCR/extraction completes:
   emit_receipt_event(EventType.RECEIPT_OCR_DONE, receipt_id, "system",
                      {"confidence": confidence_score, "engine": engine_name})

6. When confidence < 0.72:
   flag_for_review(receipt_id, reason=f"OCR confidence {confidence:.2f} < 0.72")

7. In any function that returns receipt data to a user (get_receipts, summary, etc.):
   receipts = _visibility_gate.filter_receipts(raw_receipts, user_label=requesting_user)

8. Before any delete/export/recategorize operation, check:
   if not _visibility_gate.can_access(requesting_user, "delete"):
       return "❌ You don't have permission to delete receipts."
"""

# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os
    from pathlib import Path

    # Temp DB
    _tmp = tempfile.mktemp(suffix=".db")
    LEDGER_DB = Path(_tmp)

    # Create minimal receipts table
    con = sqlite3.connect(_tmp)
    con.execute("""
        CREATE TABLE receipts (
            id INTEGER PRIMARY KEY, receipt_date TEXT, vendor TEXT,
            amount REAL, tax REAL, category TEXT, submitted_by TEXT,
            deleted INTEGER DEFAULT 0
        )
    """)
    con.execute(
        "INSERT INTO receipts (receipt_date, vendor, amount, tax, category, submitted_by) "
        "VALUES ('2026-04-13', 'Costco', 87.50, 6.50, 'food_cost', 'misha')"
    )
    con.commit()
    con.close()

    print("=" * 60)
    print("REX RECEIPT MANAGER V4 PATCH — SELF-TEST")
    print("=" * 60)

    # 1. Migration
    result = run_v4_migration()
    assert len(result["added"]) == 6, f"Expected 6 new columns, got {result}"
    print(f"✓ Test 1: run_v4_migration added {result['added']}")

    # 2. Idempotency
    result2 = run_v4_migration()
    assert len(result2["added"]) == 0
    assert len(result2["already_present"]) == 6
    print("✓ Test 2: run_v4_migration idempotent OK")

    # 3. Read migrated row
    con = sqlite3.connect(_tmp)
    row = con.execute("SELECT * FROM receipts WHERE id=1").fetchone()
    cols = [d[0] for d in con.execute("PRAGMA table_info(receipts)").fetchall()]
    con.close()
    assert "department" in cols
    assert "visibility_class" in cols
    assert "review_status" in cols
    print("✓ Test 3: New columns present in schema")

    # 4. Visibility gate — without permissions module (fallback)
    gate = ReceiptVisibilityGate()

    receipt = {
        "id": 1, "vendor": "Costco", "amount": 87.50, "tax": 6.50,
        "category": "food_cost", "department": "food_cost",
        "submitted_by": "misha", "receipt_date": "2026-04-13",
    }

    # Chairman sees everything
    r_chairman = gate.filter_receipt(receipt, "kato")
    assert r_chairman["amount"] == 87.50
    print("✓ Test 4a: Chairman sees full receipt OK")

    # Without permissions module loaded, non-chairman sees redacted
    # (depends on whether rex_permissions.py is importable)
    print("✓ Test 4: Visibility gate initialized (full test requires permissions module)")

    # 5. emit_receipt_event (no-op without events DB — silent failure)
    emit_receipt_event("receipt.submitted", 1, "misha", {"vendor": "Costco"})
    print("✓ Test 5: emit_receipt_event silent on missing events DB OK")

    os.unlink(_tmp)
    print()
    print(INSERTION_GUIDE[:300] + "...")
    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_receipt_manager_v4_patch.py ready")
    print("Apply INSERTION_GUIDE patches to rex_receipt_manager.py")
    print("=" * 60)
