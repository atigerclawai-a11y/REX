"""
rex_permissions.py — REX Permissions, Roles & Scope System
════════════════════════════════════════════════════════════
Rexonasence v4 · Chairman Doctrine · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  • Defines what every user (role or individual) can and cannot do
  • Kato (Chairman) can change permissions live via Telegram command
  • Changes persist in rex_permissions.db
  • Checked by all REX modules before any operation
  • Three-dimensional access: role + permission + scope

ARCHITECTURE:
  • Three-tier: Role permissions + individual overrides + scope grants
  • Scope grants narrow permission to specific domains (e.g. food_cost only)
  • Roles: chairman, admin_financial, finance, admin_operations, staff, viewer, none
  • Legacy aliases: manager→admin_financial, kitchen→admin_operations (backward compat)

DOCTRINE ROLES (Rexonasence v4):
  ┌──────────────────┬────────────────────────────────────────────────────────┐
  │ chairman         │ All permissions. Absolute authority. Kato/Chairman     │
  │                  │ are one identity. Can modify anyone's permissions.      │
  ├──────────────────┼────────────────────────────────────────────────────────┤
  │ admin_financial  │ View receipts, reports, financials, dashboard,         │
  │                  │ staff chats. Cannot delete, cannot modify permissions.  │
  │                  │ → Vlad                                                 │
  ├──────────────────┼────────────────────────────────────────────────────────┤
  │ finance          │ Financial data, bookkeeping, receipts, billing.        │
  │                  │ No permission control. No staff management.            │
  │                  │ → Allen (NEW — was unmapped)                           │
  ├──────────────────┼────────────────────────────────────────────────────────┤
  │ admin_operations │ Submit receipts, receive menu blast, limited ops view. │
  │                  │ No access to financial totals or others' data.         │
  │                  │ → Misha                                                │
  ├──────────────────┼────────────────────────────────────────────────────────┤
  │ staff            │ Submit receipts, view own submissions, basic Q&A.      │
  │                  │ Cannot see financial data or other staff submissions.  │
  ├──────────────────┼────────────────────────────────────────────────────────┤
  │ viewer           │ Read-only: see reports that are explicitly shared.     │
  │                  │ No submit, no modify.                                  │
  ├──────────────────┼────────────────────────────────────────────────────────┤
  │ none             │ Blocked. Silently ignored by all bots.                 │
  └──────────────────┴────────────────────────────────────────────────────────┘

BACKWARD COMPATIBILITY:
  manager  → alias for admin_financial (Vlad)
  kitchen  → alias for admin_operations (Misha)
  Both are accepted as role names and normalized to doctrine names.

USER ASSIGNMENTS (defaults, Kato can change):
  • kato  → chairman
  • vlad  → admin_financial
  • misha → admin_operations
  • allen → finance           ← NEW

SCOPE SYSTEM:
  A scope grant narrows a permission to a specific domain tag.
  Examples:
    misha + receipts.view + scope:["food_cost"]
    → Misha can view receipts, but ONLY those tagged food_cost
  Scope tags are freeform strings. Special value "*" means unrestricted.
  Scope is checked via can_scoped(user, perm, tag).
  If no scope grant exists for a user+permission, falls back to can().

TELEGRAM COMMANDS (Chairman only):
  permissions                             → show all current permissions
  permissions [user] role [role]          → assign role to user
  permissions [user] grant [perm]         → grant specific permission
  permissions [user] revoke [perm]        → revoke specific permission
  permissions [user] scope [perm] [tag]   → grant scoped permission
  permissions [user] scope-remove [perm] [tag] → remove scope grant
  permissions [user] show                 → show a user's permissions
  permissions reset [user]                → reset to role defaults
  permissions roles                       → list all available roles
  permissions perms                       → list all available permissions
  permissions history                     → recent changes audit log

PERMISSION KEYS:
  receipts.submit          Submit receipt photos
  receipts.view            View receipt list and details
  receipts.view_all        View all users' receipts (not just own)
  receipts.view_totals     View financial totals/amounts (financial roles only)
  receipts.export_excel    Generate and receive Excel files
  receipts.export_docx     Generate and receive Word reports
  receipts.recategorize    Change a receipt's category
  receipts.delete          Soft-delete receipts (chairman only by default)
  reports.view             View financial/expense reports
  reports.generate         Generate on-demand reports
  dashboard.access         Access the GOJ web dashboard
  staff.view_chats         See staff conversation logs
  staff.send_blast         Send MENU BLAST to kitchen staff
  admin.change_permissions Edit other users' permissions (chairman only)
  admin.manage_tasks       Create/assign/close tasks
  admin.view_briefing      Receive daily admin briefing
  command_center.access    Access Chairman Command Center (chairman only)
  executive.access         Access Executive Interface (admin_financial, finance)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Path ───────────────────────────────────────────────────────────────────────
PERMS_DB = Path.home() / "Desktop" / "REX" / "data" / "rex_permissions.db"

# ── Role normalization (backward compat) ───────────────────────────────────────
ROLE_ALIASES: dict[str, str] = {
    "manager":  "admin_financial",   # Vlad's old role name
    "kitchen":  "admin_operations",  # Misha's old role name
    "admin":    "admin_financial",   # generic alias
    "director": "admin_financial",   # generic alias
}

def normalize_role(role: str) -> str:
    """Normalize old/alias role names to doctrine names."""
    return ROLE_ALIASES.get(role.lower(), role.lower())


# ── All available permission keys ─────────────────────────────────────────────
ALL_PERMISSIONS = {
    # Receipts
    "receipts.submit":          "Submit receipt photos",
    "receipts.view":            "View own receipts",
    "receipts.view_all":        "View all users' receipts",
    "receipts.view_totals":     "View financial totals and amounts",
    "receipts.export_excel":    "Generate Excel receipt reports",
    "receipts.export_docx":     "Generate Word expense reports",
    "receipts.recategorize":    "Change a receipt's category",
    "receipts.delete":          "Soft-delete receipts",
    # Reports
    "reports.view":             "View financial/expense reports",
    "reports.generate":         "Generate on-demand reports",
    # Dashboard
    "dashboard.access":         "Access the GOJ dashboard section",
    # Staff management
    "staff.view_chats":         "View staff conversation logs",
    "staff.send_blast":         "Send MENU BLAST",
    # Admin
    "admin.change_permissions": "Modify other users' permissions",
    "admin.manage_tasks":       "Create/assign/close tasks",
    "admin.view_briefing":      "Receive daily admin briefing",
    # Surfaces (Chairman Doctrine)
    "command_center.access":    "Access Chairman Command Center",
    "executive.access":         "Access Executive Interface",
}

# ── Role definitions (baseline permission sets) ────────────────────────────────
ROLE_DEFINITIONS: dict[str, list[str]] = {
    "chairman": list(ALL_PERMISSIONS.keys()),   # all permissions

    "admin_financial": [
        "receipts.view",
        "receipts.view_all",
        "receipts.view_totals",
        "receipts.export_excel",
        "receipts.export_docx",
        "reports.view",
        "reports.generate",
        "dashboard.access",
        "staff.view_chats",
        "admin.view_briefing",
        "executive.access",
    ],

    "finance": [
        "receipts.view",
        "receipts.view_all",
        "receipts.view_totals",
        "receipts.export_excel",
        "receipts.export_docx",
        "receipts.recategorize",
        "reports.view",
        "reports.generate",
        "executive.access",
    ],

    "admin_operations": [
        "receipts.submit",
        "staff.send_blast",
    ],

    "staff": [
        "receipts.submit",
        "receipts.view",
        "dashboard.access",
    ],

    "viewer": [
        "reports.view",
        "receipts.view",
    ],

    "none": [],
}

# ── Default user→role assignments ─────────────────────────────────────────────
DEFAULT_USER_ROLES: dict[str, str] = {
    "kato":  "chairman",
    "vlad":  "admin_financial",
    "misha": "admin_operations",
    "allen": "finance",           # NEW — Allen was unmapped
}


# ──────────────────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_db() -> None:
    PERMS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(PERMS_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS user_roles (
            user_label  TEXT PRIMARY KEY,
            role        TEXT NOT NULL DEFAULT 'none',
            updated_at  TEXT DEFAULT (datetime('now')),
            updated_by  TEXT DEFAULT 'system'
        );

        CREATE TABLE IF NOT EXISTS permission_overrides (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_label  TEXT NOT NULL,
            permission  TEXT NOT NULL,
            granted     INTEGER NOT NULL DEFAULT 1,
            set_by      TEXT DEFAULT 'chairman',
            set_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(user_label, permission)
        );

        CREATE TABLE IF NOT EXISTS permissions_audit (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            action      TEXT NOT NULL,
            target_user TEXT,
            detail      TEXT,
            performed_by TEXT,
            performed_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS scope_grants (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_label  TEXT NOT NULL,
            permission  TEXT NOT NULL,
            scope_tag   TEXT NOT NULL,
            granted_by  TEXT DEFAULT 'chairman',
            granted_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(user_label, permission, scope_tag)
        );

        CREATE INDEX IF NOT EXISTS idx_scope_user ON scope_grants(user_label);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON permissions_audit(target_user);
    """)

    # Migrate existing DB: normalise old role names to doctrine names
    try:
        rows = con.execute("SELECT user_label, role FROM user_roles").fetchall()
        for user_label, role in rows:
            normalised = normalize_role(role)
            if normalised != role:
                con.execute(
                    "UPDATE user_roles SET role=?, updated_at=datetime('now'), updated_by='migration_v4' "
                    "WHERE user_label=?",
                    (normalised, user_label)
                )
                logger.info(f"[perms] Migrated {user_label}: {role} → {normalised}")
    except Exception as e:
        logger.warning(f"[perms] Role migration scan: {e}")

    # Insert default roles if not present (including allen)
    for user, role in DEFAULT_USER_ROLES.items():
        con.execute(
            "INSERT OR IGNORE INTO user_roles (user_label, role) VALUES (?, ?)",
            (user, role)
        )
    con.commit()
    con.close()


# ──────────────────────────────────────────────────────────────────────────────
# PERMISSIONS CLASS
# ──────────────────────────────────────────────────────────────────────────────

class PermissionsManager:
    """
    Chairman-controlled permissions system for REX — Rexonasence v4.

    Usage:
        perms = PermissionsManager()
        perms.can("vlad", "receipts.view_all")         # True
        perms.can("misha", "receipts.view_all")        # False
        perms.can("misha", "receipts.submit")          # True
        perms.can_scoped("misha", "receipts.view", "food_cost")   # True if scope granted

    Kato can modify from Telegram:
        "permissions misha grant receipts.view"
        "permissions vlad role admin_financial"
        "permissions misha scope receipts.view food_cost"
    """

    def __init__(self):
        _ensure_db()

    # ── Core check ─────────────────────────────────────────────────────────────

    def can(self, user_label: str, permission: str) -> bool:
        """
        Check if a user has a specific permission.
        Chairman override: chairman always returns True regardless of DB state.
        Checks: individual overrides first, then role defaults.
        """
        # Chairman override — absolute authority
        if user_label.lower() in ("kato", "chairman"):
            return True

        try:
            con = sqlite3.connect(str(PERMS_DB))

            # 1. Check individual override
            override = con.execute(
                "SELECT granted FROM permission_overrides "
                "WHERE user_label=? AND permission=?",
                (user_label, permission)
            ).fetchone()

            if override is not None:
                con.close()
                return bool(override[0])

            # 2. Check role
            role_row = con.execute(
                "SELECT role FROM user_roles WHERE user_label=?",
                (user_label,)
            ).fetchone()
            con.close()

            raw_role = role_row[0] if role_row else DEFAULT_USER_ROLES.get(user_label, "none")
            role = normalize_role(raw_role)
            return permission in ROLE_DEFINITIONS.get(role, [])

        except Exception as e:
            logger.error(f"[perms] can() error for {user_label}/{permission}: {e}")
            return False

    def can_scoped(self, user_label: str, permission: str, scope_tag: str) -> bool:
        """
        Check if a user has a scoped permission.
        Rules:
          1. If user has unrestricted permission (no scope rows for this user+permission):
             falls through to can() — scope grants are additive restrictions, not baseline
          2. If scope grants exist for user+permission: user must match one of them
          3. Chairman always passes (absolute authority)
          4. Special tag "*" in scope_grants means unrestricted

        Use case: Misha granted receipts.view scoped to food_cost only.
        """
        if user_label.lower() in ("kato", "chairman"):
            return True

        # Check if any scope grants exist for this user+permission
        try:
            con = sqlite3.connect(str(PERMS_DB))
            scope_rows = con.execute(
                "SELECT scope_tag FROM scope_grants WHERE user_label=? AND permission=?",
                (user_label, permission)
            ).fetchall()
            con.close()
        except Exception as e:
            logger.error(f"[perms] can_scoped() DB error: {e}")
            return False

        if not scope_rows:
            # No scope restrictions — fall through to regular can()
            return self.can(user_label, permission)

        allowed_tags = {row[0] for row in scope_rows}
        # Wildcard grant = unrestricted
        if "*" in allowed_tags:
            return self.can(user_label, permission)

        return scope_tag in allowed_tags and self.can(user_label, permission)

    def get_role(self, user_label: str) -> str:
        """Return the normalised doctrine role assigned to this user."""
        try:
            con = sqlite3.connect(str(PERMS_DB))
            row = con.execute(
                "SELECT role FROM user_roles WHERE user_label=?",
                (user_label,)
            ).fetchone()
            con.close()
            if row:
                return normalize_role(row[0])
        except Exception:
            pass
        raw = DEFAULT_USER_ROLES.get(user_label, "none")
        return normalize_role(raw)

    def is_chairman(self, user_label: str) -> bool:
        """True only if user is the Chairman."""
        return self.get_role(user_label) == "chairman" or user_label.lower() in ("kato", "chairman")

    def get_all_permissions(self, user_label: str) -> list[str]:
        """Return a user's effective permissions (role + overrides)."""
        role = self.get_role(user_label)
        effective = set(ROLE_DEFINITIONS.get(role, []))

        try:
            con = sqlite3.connect(str(PERMS_DB))
            overrides = con.execute(
                "SELECT permission, granted FROM permission_overrides "
                "WHERE user_label=?",
                (user_label,)
            ).fetchall()
            con.close()
            for perm, granted in overrides:
                if granted:
                    effective.add(perm)
                else:
                    effective.discard(perm)
        except Exception:
            pass

        return sorted(effective)

    def get_scope_grants(self, user_label: str) -> dict[str, list[str]]:
        """Return a map of permission → [scope_tags] for this user."""
        try:
            con = sqlite3.connect(str(PERMS_DB))
            rows = con.execute(
                "SELECT permission, scope_tag FROM scope_grants WHERE user_label=? ORDER BY permission",
                (user_label,)
            ).fetchall()
            con.close()
            result: dict[str, list[str]] = {}
            for perm, tag in rows:
                result.setdefault(perm, []).append(tag)
            return result
        except Exception as e:
            logger.error(f"[perms] get_scope_grants error: {e}")
            return {}

    # ── Modification (Chairman only) ───────────────────────────────────────────

    def set_role(
        self, user_label: str, role: str, performed_by: str = "chairman"
    ) -> tuple[bool, str]:
        """Assign a role to a user. Normalises aliases. Returns (success, message)."""
        norm = normalize_role(role)
        if norm not in ROLE_DEFINITIONS:
            valid = ", ".join(list(ROLE_DEFINITIONS.keys()) + list(ROLE_ALIASES.keys()))
            return False, f"Unknown role '{role}'. Valid roles: {valid}"

        # Protect Chairman — no one can change Kato's role
        if user_label.lower() in ("kato", "chairman") and norm != "chairman":
            return False, "⚠️ Cannot demote Chairman/Kato. This is a Doctrine protection."

        try:
            con = sqlite3.connect(str(PERMS_DB))
            con.execute(
                "INSERT INTO user_roles (user_label, role, updated_by, updated_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(user_label) DO UPDATE SET "
                "role=excluded.role, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (user_label, norm, performed_by)
            )
            con.execute(
                "INSERT INTO permissions_audit (action, target_user, detail, performed_by) "
                "VALUES ('set_role', ?, ?, ?)",
                (user_label, f"role → {norm}" + (f" (alias: {role})" if role != norm else ""), performed_by)
            )
            con.commit()
            con.close()

            role_perms = ROLE_DEFINITIONS.get(norm, [])
            return True, (
                f"✅ *{user_label.title()}* → role set to *{norm}*\n"
                f"Permissions ({len(role_perms)}): "
                + (", ".join(role_perms[:6]) + ("..." if len(role_perms) > 6 else ""))
            )
        except Exception as e:
            return False, f"Error setting role: {e}"

    def grant_permission(
        self, user_label: str, permission: str, performed_by: str = "chairman"
    ) -> tuple[bool, str]:
        """Grant a specific permission to a user (overrides role)."""
        if permission not in ALL_PERMISSIONS:
            close_matches = [p for p in ALL_PERMISSIONS if permission.split(".")[0] in p]
            hint = f"\nDid you mean: {', '.join(close_matches[:5])}" if close_matches else ""
            return False, f"Unknown permission '{permission}'.{hint}"

        try:
            con = sqlite3.connect(str(PERMS_DB))
            con.execute(
                "INSERT INTO permission_overrides "
                "(user_label, permission, granted, set_by, set_at) "
                "VALUES (?, ?, 1, ?, datetime('now')) "
                "ON CONFLICT(user_label, permission) DO UPDATE SET "
                "granted=1, set_by=excluded.set_by, set_at=excluded.set_at",
                (user_label, permission, performed_by)
            )
            con.execute(
                "INSERT INTO permissions_audit (action, target_user, detail, performed_by) "
                "VALUES ('grant', ?, ?, ?)",
                (user_label, permission, performed_by)
            )
            con.commit()
            con.close()
            desc = ALL_PERMISSIONS.get(permission, permission)
            return True, f"✅ *{user_label.title()}* granted: `{permission}`\n_{desc}_"
        except Exception as e:
            return False, f"Error granting permission: {e}"

    def revoke_permission(
        self, user_label: str, permission: str, performed_by: str = "chairman"
    ) -> tuple[bool, str]:
        """Explicitly revoke a permission (overrides role, even if role would grant it)."""
        if permission not in ALL_PERMISSIONS:
            return False, f"Unknown permission '{permission}'."

        # Protect Chairman — never revoke from kato
        if user_label.lower() in ("kato", "chairman"):
            return False, "⚠️ Cannot revoke permissions from Chairman/Kato. Doctrine protection."

        try:
            con = sqlite3.connect(str(PERMS_DB))
            con.execute(
                "INSERT INTO permission_overrides "
                "(user_label, permission, granted, set_by, set_at) "
                "VALUES (?, ?, 0, ?, datetime('now')) "
                "ON CONFLICT(user_label, permission) DO UPDATE SET "
                "granted=0, set_by=excluded.set_by, set_at=excluded.set_at",
                (user_label, permission, performed_by)
            )
            con.execute(
                "INSERT INTO permissions_audit (action, target_user, detail, performed_by) "
                "VALUES ('revoke', ?, ?, ?)",
                (user_label, permission, performed_by)
            )
            con.commit()
            con.close()
            return True, f"✅ *{user_label.title()}* revoked: `{permission}`"
        except Exception as e:
            return False, f"Error revoking permission: {e}"

    def grant_scope(
        self,
        user_label: str,
        permission: str,
        scope_tag: str,
        performed_by: str = "chairman",
    ) -> tuple[bool, str]:
        """Add a scope grant for user+permission+tag."""
        if permission not in ALL_PERMISSIONS:
            return False, f"Unknown permission '{permission}'."
        try:
            con = sqlite3.connect(str(PERMS_DB))
            con.execute(
                "INSERT OR IGNORE INTO scope_grants "
                "(user_label, permission, scope_tag, granted_by, granted_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (user_label, permission, scope_tag, performed_by)
            )
            con.execute(
                "INSERT INTO permissions_audit (action, target_user, detail, performed_by) "
                "VALUES ('grant_scope', ?, ?, ?)",
                (user_label, f"{permission} scope:{scope_tag}", performed_by)
            )
            con.commit()
            con.close()
            return True, (
                f"✅ *{user_label.title()}* scope grant: `{permission}` → tag `{scope_tag}`\n"
                f"They can now access {permission} restricted to `{scope_tag}` data only."
            )
        except Exception as e:
            return False, f"Error granting scope: {e}"

    def remove_scope(
        self,
        user_label: str,
        permission: str,
        scope_tag: str,
        performed_by: str = "chairman",
    ) -> tuple[bool, str]:
        """Remove a scope grant."""
        try:
            con = sqlite3.connect(str(PERMS_DB))
            con.execute(
                "DELETE FROM scope_grants WHERE user_label=? AND permission=? AND scope_tag=?",
                (user_label, permission, scope_tag)
            )
            con.execute(
                "INSERT INTO permissions_audit (action, target_user, detail, performed_by) "
                "VALUES ('remove_scope', ?, ?, ?)",
                (user_label, f"{permission} scope:{scope_tag}", performed_by)
            )
            con.commit()
            con.close()
            return True, f"✅ Scope removed: *{user_label.title()}* `{permission}` tag `{scope_tag}`"
        except Exception as e:
            return False, f"Error removing scope: {e}"

    def reset_to_role(
        self, user_label: str, performed_by: str = "chairman"
    ) -> tuple[bool, str]:
        """Remove all individual overrides and scope grants — return user to pure role defaults."""
        if user_label.lower() in ("kato", "chairman"):
            return False, "⚠️ Cannot reset Chairman/Kato. Doctrine protection."
        try:
            con = sqlite3.connect(str(PERMS_DB))
            n_ovr = con.execute(
                "SELECT COUNT(*) FROM permission_overrides WHERE user_label=?",
                (user_label,)
            ).fetchone()[0]
            n_scope = con.execute(
                "SELECT COUNT(*) FROM scope_grants WHERE user_label=?",
                (user_label,)
            ).fetchone()[0]
            con.execute("DELETE FROM permission_overrides WHERE user_label=?", (user_label,))
            con.execute("DELETE FROM scope_grants WHERE user_label=?", (user_label,))
            con.execute(
                "INSERT INTO permissions_audit (action, target_user, detail, performed_by) "
                "VALUES ('reset', ?, ?, ?)",
                (user_label, f"cleared {n_ovr} overrides, {n_scope} scope grants", performed_by)
            )
            con.commit()
            con.close()
            role = self.get_role(user_label)
            return True, (
                f"✅ *{user_label.title()}* reset to pure *{role}* role. "
                f"{n_ovr} override(s) and {n_scope} scope grant(s) removed."
            )
        except Exception as e:
            return False, f"Error resetting permissions: {e}"

    # ── Display helpers ────────────────────────────────────────────────────────

    def show_user(self, user_label: str) -> str:
        """Return a formatted summary of a user's permissions."""
        role    = self.get_role(user_label)
        perms   = self.get_all_permissions(user_label)
        scopes  = self.get_scope_grants(user_label)
        role_ps = set(ROLE_DEFINITIONS.get(role, []))

        lines = [f"*{user_label.title()}* — role: *{role}*\n"]

        # Individual overrides
        try:
            con = sqlite3.connect(str(PERMS_DB))
            overrides = con.execute(
                "SELECT permission, granted, set_by, set_at "
                "FROM permission_overrides WHERE user_label=? ORDER BY permission",
                (user_label,)
            ).fetchall()
            con.close()
        except Exception:
            overrides = []

        if overrides:
            lines.append("*Individual overrides:*")
            for perm, granted, set_by, set_at in overrides:
                symbol = "✅" if granted else "❌"
                lines.append(f"  {symbol} `{perm}` (by {set_by})")
            lines.append("")

        if scopes:
            lines.append("*Scope grants:*")
            for perm, tags in scopes.items():
                lines.append(f"  🔍 `{perm}` → tags: {', '.join(tags)}")
            lines.append("")

        lines.append(f"*Effective permissions ({len(perms)}):*")
        for p in perms:
            extra = " ⬆️" if p not in role_ps else ""
            lines.append(f"  ✓ `{p}`{extra}")

        if not perms:
            lines.append("  _(none)_")

        return "\n".join(lines)

    def show_all(self) -> str:
        """Return all users and their roles."""
        try:
            con = sqlite3.connect(str(PERMS_DB))
            users = con.execute(
                "SELECT user_label, role, updated_by, updated_at "
                "FROM user_roles ORDER BY user_label"
            ).fetchall()
            con.close()
        except Exception:
            users = []

        if not users:
            lines = ["*REX Permissions — Default Assignments (v4 Doctrine):*\n"]
            for user, role in DEFAULT_USER_ROLES.items():
                n_perms = len(ROLE_DEFINITIONS.get(role, []))
                lines.append(f"  *{user.title()}* → {role} ({n_perms} permissions)")
        else:
            lines = ["*REX Permissions — Current Assignments (v4 Doctrine):*\n"]
            for user_label, role, updated_by, updated_at in users:
                n_perms = len(self.get_all_permissions(user_label))
                date_str = updated_at[:10] if updated_at else "default"
                lines.append(
                    f"  *{user_label.title()}* → *{normalize_role(role)}*  "
                    f"({n_perms} effective permissions)  [{date_str}]"
                )

        lines += [
            "",
            "_Commands:_",
            "`permissions [user] role [role]`        — change role",
            "`permissions [user] grant [perm]`        — add permission",
            "`permissions [user] revoke [perm]`       — remove permission",
            "`permissions [user] scope [perm] [tag]`  — add scope grant",
            "`permissions [user] show`                — detail view",
            "`permissions roles`                      — list all roles",
            "`permissions perms`                      — list all permissions",
        ]
        return "\n".join(lines)

    def show_roles(self) -> str:
        """List all doctrine roles and their permission counts."""
        lines = ["*REX Doctrine Roles (Rexonasence v4):*\n"]
        for role, perms in ROLE_DEFINITIONS.items():
            alias_note = ""
            rev_aliases = [k for k, v in ROLE_ALIASES.items() if v == role]
            if rev_aliases:
                alias_note = f" _(also: {', '.join(rev_aliases)})_"
            lines.append(f"*{role}*{alias_note}  —  {len(perms)} permissions")
            for p in perms[:5]:
                lines.append(f"   • {p}")
            if len(perms) > 5:
                lines.append(f"   … and {len(perms) - 5} more")
            lines.append("")
        return "\n".join(lines)

    def show_permissions_list(self) -> str:
        """List all available permission keys with descriptions."""
        lines = ["*All Available Permissions (v4):*\n"]
        current_prefix = ""
        for key, desc in sorted(ALL_PERMISSIONS.items()):
            prefix = key.split(".")[0]
            if prefix != current_prefix:
                lines.append(f"\n*{prefix.upper()}*")
                current_prefix = prefix
            lines.append(f"  `{key}` — {desc}")
        return "\n".join(lines)

    def show_audit_log(self, n: int = 20) -> str:
        """Show recent permission changes audit log."""
        try:
            con = sqlite3.connect(str(PERMS_DB))
            rows = con.execute(
                "SELECT action, target_user, detail, performed_by, performed_at "
                "FROM permissions_audit ORDER BY id DESC LIMIT ?",
                (n,)
            ).fetchall()
            con.close()
        except Exception:
            rows = []

        if not rows:
            return "No permission changes on record."

        lines = [f"*Permission Audit Log (last {n}):*\n"]
        for action, target, detail, by, at in rows:
            lines.append(f"  [{at[:16]}]  {action.upper()}  {target}  —  {detail}  (by {by})")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM COMMAND HANDLER
# ──────────────────────────────────────────────────────────────────────────────

_perms_instance: Optional[PermissionsManager] = None

def get_perms() -> PermissionsManager:
    global _perms_instance
    if _perms_instance is None:
        _perms_instance = PermissionsManager()
    return _perms_instance


def handle_permissions_command(text: str, requesting_user: str = "kato") -> str:
    """
    Parse and handle a permissions command from Telegram.
    Only the Chairman can modify permissions.
    """
    import re
    perms    = get_perms()
    lower    = text.lower().strip()
    is_chair = perms.can(requesting_user, "admin.change_permissions")

    # ── permissions history ───────────────────────────────────────────────────
    if "history" in lower or "audit" in lower or "log" in lower:
        return perms.show_audit_log()

    # ── permissions roles ─────────────────────────────────────────────────────
    if re.match(r'^permissions?\s+roles?$', lower):
        return perms.show_roles()

    # ── permissions perms ─────────────────────────────────────────────────────
    if re.match(r'^permissions?\s+(perms?|permissions?|list)$', lower):
        return perms.show_permissions_list()

    # ── permissions (bare) ────────────────────────────────────────────────────
    if re.match(r'^permissions?$', lower):
        return perms.show_all()

    # ── permissions [user] show ───────────────────────────────────────────────
    m = re.match(r'^permissions?\s+(\w+)\s+show$', lower)
    if m:
        return perms.show_user(m.group(1))

    # ── Modification commands (Chairman only) ─────────────────────────────────
    if not is_chair:
        return "❌ Only the Chairman can modify permissions."

    # permissions [user] role [role]
    m = re.match(r'^permissions?\s+(\w+)\s+role\s+(\w+)$', lower)
    if m:
        user, new_role = m.group(1), m.group(2)
        ok, msg = perms.set_role(user, new_role, performed_by=requesting_user)
        return msg

    # permissions [user] grant [perm]
    m = re.match(r'^permissions?\s+(\w+)\s+grant\s+([\w.]+)$', lower)
    if m:
        user, perm = m.group(1), m.group(2)
        ok, msg = perms.grant_permission(user, perm, performed_by=requesting_user)
        return msg

    # permissions [user] revoke [perm]
    m = re.match(r'^permissions?\s+(\w+)\s+revoke\s+([\w.]+)$', lower)
    if m:
        user, perm = m.group(1), m.group(2)
        ok, msg = perms.revoke_permission(user, perm, performed_by=requesting_user)
        return msg

    # permissions [user] scope [perm] [tag]
    m = re.match(r'^permissions?\s+(\w+)\s+scope\s+([\w.]+)\s+(\S+)$', lower)
    if m:
        user, perm, tag = m.group(1), m.group(2), m.group(3)
        ok, msg = perms.grant_scope(user, perm, tag, performed_by=requesting_user)
        return msg

    # permissions [user] scope-remove [perm] [tag]
    m = re.match(r'^permissions?\s+(\w+)\s+scope[-_]remove\s+([\w.]+)\s+(\S+)$', lower)
    if m:
        user, perm, tag = m.group(1), m.group(2), m.group(3)
        ok, msg = perms.remove_scope(user, perm, tag, performed_by=requesting_user)
        return msg

    # permissions reset [user]
    m = re.match(r'^permissions?\s+reset\s+(\w+)$', lower)
    if m:
        ok, msg = perms.reset_to_role(m.group(1), performed_by=requesting_user)
        return msg

    return (
        "*Permission Commands (v4):*\n\n"
        "`permissions` — view all users\n"
        "`permissions [user] show` — view a user's permissions\n"
        "`permissions [user] role [role]` — change role\n"
        "`permissions [user] grant [perm]` — add a permission\n"
        "`permissions [user] revoke [perm]` — remove a permission\n"
        "`permissions [user] scope [perm] [tag]` — add scoped access\n"
        "`permissions [user] scope-remove [perm] [tag]` — remove scope\n"
        "`permissions reset [user]` — reset to role defaults\n"
        "`permissions roles` — list all roles\n"
        "`permissions perms` — list all permission keys\n"
        "`permissions history` — audit log\n\n"
        "_Doctrine roles: chairman · admin_financial · finance · admin_operations · staff · viewer · none_"
    )


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("REX PERMISSIONS v4 — SELF-TEST")
    print("=" * 60)

    perms = PermissionsManager()

    # 1. Doctrine roles
    assert perms.get_role("kato")  == "chairman",        f"Expected chairman got {perms.get_role('kato')}"
    assert perms.get_role("vlad")  == "admin_financial", f"Expected admin_financial got {perms.get_role('vlad')}"
    assert perms.get_role("misha") == "admin_operations", f"Expected admin_operations got {perms.get_role('misha')}"
    assert perms.get_role("allen") == "finance",         f"Expected finance got {perms.get_role('allen')}"
    print("✓ Test 1: Doctrine roles OK (kato/vlad/misha/allen)")

    # 2. Chairman has all permissions (absolute authority)
    assert perms.can("kato", "receipts.delete")
    assert perms.can("kato", "admin.change_permissions")
    assert perms.can("kato", "command_center.access")
    print("✓ Test 2: Chairman absolute authority OK")

    # 3. Vlad (admin_financial) — can view totals, no permission control
    assert perms.can("vlad", "receipts.view")
    assert perms.can("vlad", "receipts.view_all")
    assert perms.can("vlad", "receipts.view_totals")
    assert perms.can("vlad", "executive.access")
    assert not perms.can("vlad", "receipts.delete")
    assert not perms.can("vlad", "admin.change_permissions")
    assert not perms.can("vlad", "command_center.access")
    print("✓ Test 3: Vlad (admin_financial) OK")

    # 4. Allen (finance) — can view totals, no staff management
    assert perms.can("allen", "receipts.view")
    assert perms.can("allen", "receipts.view_totals")
    assert perms.can("allen", "executive.access")
    assert not perms.can("allen", "staff.view_chats")
    assert not perms.can("allen", "admin.change_permissions")
    assert not perms.can("allen", "command_center.access")
    print("✓ Test 4: Allen (finance) OK")

    # 5. Misha (admin_operations) — can submit, no financials
    assert perms.can("misha", "receipts.submit")
    assert not perms.can("misha", "receipts.view_all")
    assert not perms.can("misha", "receipts.view_totals")
    assert not perms.can("misha", "reports.view")
    print("✓ Test 5: Misha (admin_operations) OK")

    # 6. Role alias normalization
    ok, msg = perms.set_role("misha", "kitchen", performed_by="kato")
    assert ok, f"Alias set failed: {msg}"
    assert perms.get_role("misha") == "admin_operations", f"Expected admin_operations, got {perms.get_role('misha')}"
    print("✓ Test 6: Role alias normalization (kitchen → admin_operations) OK")

    # 7. Chairman protection
    ok, msg = perms.set_role("kato", "staff", performed_by="kato")
    assert not ok, "Should not be able to demote Chairman"
    ok, msg = perms.revoke_permission("kato", "receipts.delete", performed_by="kato")
    assert not ok, "Should not be able to revoke from Chairman"
    print("✓ Test 7: Chairman protection OK")

    # 8. Scope grants
    ok, msg = perms.grant_scope("misha", "receipts.view", "food_cost", performed_by="kato")
    assert ok, f"Scope grant failed: {msg}"
    # Scope check — misha has receipts.view scoped to food_cost
    perms.grant_permission("misha", "receipts.view", performed_by="kato")  # grant base perm first
    assert perms.can_scoped("misha", "receipts.view", "food_cost"), "Misha should have food_cost scope"
    assert not perms.can_scoped("misha", "receipts.view", "payroll"), "Misha should NOT have payroll scope"
    perms.remove_scope("misha", "receipts.view", "food_cost", performed_by="kato")
    perms.revoke_permission("misha", "receipts.view", performed_by="kato")
    print("✓ Test 8: Scope grants OK")

    # 9. Grant override
    ok, msg = perms.grant_permission("misha", "receipts.view", performed_by="kato")
    assert ok, f"Grant failed: {msg}"
    assert perms.can("misha", "receipts.view")
    perms.revoke_permission("misha", "receipts.view", performed_by="kato")
    assert not perms.can("misha", "receipts.view")
    print("✓ Test 9: Grant/revoke override OK")

    # 10. Reset
    perms.grant_permission("misha", "receipts.view", performed_by="kato")
    perms.grant_scope("misha", "receipts.view", "food_cost", performed_by="kato")
    ok, msg = perms.reset_to_role("misha", performed_by="kato")
    assert ok
    assert not perms.can("misha", "receipts.view")
    scopes = perms.get_scope_grants("misha")
    assert "receipts.view" not in scopes
    print("✓ Test 10: Reset (overrides + scopes) OK")

    # 11. Audit log
    log = perms.show_audit_log()
    assert "GRANT" in log.upper() or "REVOKE" in log.upper() or "SET_ROLE" in log.upper()
    print("✓ Test 11: Audit log OK")

    # 12. Telegram command routing
    result = handle_permissions_command("permissions", "kato")
    assert "vlad" in result.lower() or "misha" in result.lower()
    result = handle_permissions_command("permissions misha role admin_operations", "kato")
    assert "admin_operations" in result.lower() or "misha" in result.lower()
    result = handle_permissions_command("permissions misha grant receipts.view", "kato")
    assert "granted" in result.lower() or "receipts.view" in result
    perms.revoke_permission("misha", "receipts.view", performed_by="kato")
    result = handle_permissions_command("permissions misha role manager", "misha")
    assert "chairman" in result.lower() or "only" in result.lower()
    print("✓ Test 12: Telegram command routing OK")

    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_permissions.py v4 ready")
    print()
    print("  Doctrine roles: chairman · admin_financial · finance · admin_operations · staff")
    print("  Allen (finance) now mapped.")
    print("  Scope grants: permissions [user] scope [perm] [tag]")
    print("  Chairman protected from demotion or permission loss.")
    print("=" * 60)
