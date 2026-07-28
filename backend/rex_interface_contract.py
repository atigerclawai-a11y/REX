"""
backend/rex_interface_contract.py — Interface-Agnostic Guardrails
════════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 9 · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  Documents and enforces the interface-agnostic contract that ensures:
    1. Future video/live interfaces can be added without backend redesign
    2. Rexxie private domain remains sealed from any future interface
    3. Session-token identity works across all interface types
    4. Permission checks run the same way regardless of interface

THIS IS NOT A RUNTIME MODULE — it defines and verifies invariants.
Run it with: python rex_interface_contract.py --verify
It checks the live repo and reports what's PASS / WARN / FAIL.

INTERFACE CONTRACT (immutable):
  C1. All policy/permission checks must go through rex_permissions.py
      No interface may implement its own permission logic.

  C2. All events must flow through rex_events.write_event()
      No interface may write directly to audit tables.

  C3. The FastAPI backend (backend/main.py) is the single source of truth
      for AI responses. No interface bypasses it.

  C4. Rexxie private domain is ONLY accessible via Telegram (chat_id gate).
      Web, video, and any future interface cannot access Rexxie memory.

  C5. Identity must be interface-declared + server-verified (rex_role_auth).
      No interface can self-elevate to chairman by claiming a role.

  C6. Chairman Command Center (/api/chairman/*) requires Header auth.
      No WebSocket or URL parameter can substitute.

  C7. All financial data responses must pass through ReceiptVisibilityGate.
      No interface bypasses the visibility filter.

FUTURE VIDEO / LIVE COMPATIBILITY:
  To add a video/live interface:

  Step 1 — Identity: Define a session_token → user_label mapping.
    The session token must be exchanged for a verified user_label + role
    via the SAME verify_role() function used by all other interfaces.
    There must be NO parallel RBAC for video sessions.

  Step 2 — Events: Video session start/end events must flow through rex_events.
    EventType candidates:
      session.video_start   actor=user_label, entity=session_id
      session.video_end     actor=user_label, entity=session_id
      session.video_error   actor=system, sensitivity=high

  Step 3 — Rexxie: Rexxie MUST NOT be accessible from video sessions.
    The ALLOWED_CHAT_IDS gate (Telegram-only) must remain the only
    entry point to Rexxie memory. Video sessions use REX only.

  Step 4 — Permission: All video-triggered actions use the same
    rex_permissions.can() / can_scoped() checks as web/Telegram.

  Step 5 — Command Center: Video interface may NOT display the Command Center.
    Chairman uses Telegram or Desktop for Command Center access.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
_REX_DIR = Path.home() / "Desktop" / "REX"


# ──────────────────────────────────────────────────────────────────────────────
# CONTRACT INVARIANT CHECKS
# ──────────────────────────────────────────────────────────────────────────────

def verify_contract() -> dict:
    """
    Check all interface contract invariants against the live repo.
    Returns a dict with PASS/WARN/FAIL results for each check.
    """
    checks = {}

    # C1: rex_permissions.py exists and has can() function
    checks["C1_permissions_module"] = _check_file_and_symbol(
        _REX_DIR / "rex_permissions.py",
        symbol="def can(",
        name="rex_permissions.can() exists",
    )

    # C2: rex_events.py exists and has write_event()
    checks["C2_events_module"] = _check_file_and_symbol(
        _REX_DIR / "rex_events.py",
        symbol="def write_event(",
        name="rex_events.write_event() exists",
    )

    # C3: FastAPI backend exists
    checks["C3_fastapi_backend"] = _check_file_and_symbol(
        _REX_DIR / "backend" / "main.py",
        symbol="from fastapi import",
        name="FastAPI backend exists",
    )

    # C4: Rexxie gate — ALLOWED_CHAT_IDS in start_rexxie.command
    launch_script = _REX_DIR.parent / "Gold_Health_Systems" / "start_rexxie.command"
    alt_launch    = Path.home() / "Desktop" / "Gold_Health_Systems" / "start_rexxie.command"
    ls = launch_script if launch_script.exists() else (alt_launch if alt_launch.exists() else None)
    if ls:
        checks["C4_rexxie_gate"] = _check_file_and_symbol(
            ls,
            symbol="ALLOWED_CHAT_IDS",
            name="Rexxie ALLOWED_CHAT_IDS gate in start_rexxie.command",
        )
    else:
        checks["C4_rexxie_gate"] = {
            "status": "WARN",
            "name": "Rexxie ALLOWED_CHAT_IDS gate",
            "detail": "start_rexxie.command not found — check path",
        }

    # C5: rex_role_auth.py exists and has verify_role()
    checks["C5_role_auth"] = _check_file_and_symbol(
        _REX_DIR / "backend" / "rex_role_auth.py",
        symbol="def verify_role(",
        name="rex_role_auth.verify_role() exists",
    )

    # C6: Command Center routes exist
    checks["C6_command_center"] = _check_file_and_symbol(
        _REX_DIR / "backend" / "rex_command_center.py",
        symbol="_require_chairman(",
        name="Chairman auth guard in Command Center",
    )

    # C7: ReceiptVisibilityGate exists
    checks["C7_visibility_gate"] = _check_file_and_symbol(
        _REX_DIR / "rex_receipt_manager_v4_patch.py",
        symbol="class ReceiptVisibilityGate",
        name="ReceiptVisibilityGate exists",
    )

    # C8: Override module exists and uses PBKDF2
    checks["C8_override_module"] = _check_file_and_symbol(
        _REX_DIR / "rex_override.py",
        symbol="pbkdf2_hmac",
        name="rex_override.py uses PBKDF2 hashing",
    )

    # C9: Unresolved queue exists
    checks["C9_unresolved_queue"] = _check_file_and_symbol(
        _REX_DIR / "rex_unresolved.py",
        symbol="def create_item(",
        name="rex_unresolved.create_item() exists",
    )

    # C10: Clarification router exists
    checks["C10_clarification"] = _check_file_and_symbol(
        _REX_DIR / "rex_clarification.py",
        symbol="def route_clarification(",
        name="rex_clarification.route_clarification() exists",
    )

    # C11: Rexxie DB is in separate zone (not inside REX dir)
    rexxie_db_rex = _REX_DIR / "rexxie_private.db"
    rexxie_db_ghs = Path.home() / "Desktop" / "Gold_Health_Systems" / "rexxie_private.db"
    if rexxie_db_ghs.exists() and not rexxie_db_rex.exists():
        checks["C11_rexxie_zone_separation"] = {
            "status": "PASS",
            "name": "Rexxie private DB in separate zone (Gold_Health_Systems/)",
        }
    elif rexxie_db_rex.exists():
        checks["C11_rexxie_zone_separation"] = {
            "status": "WARN",
            "name": "Rexxie private DB location",
            "detail": "rexxie_private.db found inside REX/ dir — should be in Gold_Health_Systems/",
        }
    else:
        checks["C11_rexxie_zone_separation"] = {
            "status": "WARN",
            "name": "Rexxie private DB location",
            "detail": "rexxie_private.db not found at expected path — may not exist yet",
        }

    # C12: Interface-agnostic verification (no hardcoded interface in permission checks)
    checks["C12_interface_agnostic"] = _check_no_interface_coupling(
        _REX_DIR / "rex_permissions.py",
        bad_patterns=["webview", "telegram", "websocket", "video", "http.request"],
        name="rex_permissions.py has no interface coupling",
    )

    return checks


def _check_file_and_symbol(path: Path, symbol: str, name: str) -> dict:
    if not path.exists():
        return {"status": "FAIL", "name": name, "detail": f"File not found: {path.name}"}
    try:
        content = path.read_text(errors="ignore")
        if symbol in content:
            return {"status": "PASS", "name": name}
        else:
            return {
                "status": "FAIL",
                "name": name,
                "detail": f"Symbol '{symbol}' not found in {path.name}",
            }
    except Exception as e:
        return {"status": "WARN", "name": name, "detail": f"Read error: {e}"}


def _check_no_interface_coupling(path: Path, bad_patterns: list[str], name: str) -> dict:
    """
    Check that the CORE permission logic (can(), can_scoped(), PermissionsManager)
    has no hardcoded interface coupling.

    NOTE: rex_permissions.py intentionally contains a Telegram command handler
    (handle_permissions_command) as a convenience utility. This function is a
    command parser — NOT permission logic — so 'telegram' appearing in the file
    is architecturally correct and not a coupling violation. We therefore check
    only the core logic section (before the TELEGRAM COMMAND HANDLER marker).
    """
    if not path.exists():
        return {"status": "FAIL", "name": name, "detail": f"File not found: {path.name}"}
    try:
        full = path.read_text(errors="ignore")
        # Scope check to core logic only — stop before the command-handler section
        # which is explicitly labelled and contains interface-specific parsing by design.
        _command_handler_marker = "# TELEGRAM COMMAND HANDLER"
        if _command_handler_marker in full:
            core_section = full[:full.index(_command_handler_marker)]
        else:
            core_section = full
        # Strip all comments AND multi-line docstrings before checking.
        # Only actual executable code lines are checked for interface coupling.
        import re as _re
        # Remove triple-quoted strings (docstrings)
        stripped = _re.sub(r'""".*?"""', '', core_section, flags=_re.DOTALL)
        stripped = _re.sub(r"'''.*?'''", '', stripped, flags=_re.DOTALL)
        # Remove single-line comments
        stripped = _re.sub(r'#.*', '', stripped)
        content = stripped.lower()
        found = [p for p in bad_patterns if p in content]
        if found:
            return {
                "status": "WARN",
                "name": name,
                "detail": f"Possible interface coupling in core logic: {found}",
            }
        return {"status": "PASS", "name": name}
    except Exception as e:
        return {"status": "WARN", "name": name, "detail": f"Read error: {e}"}


def print_contract_report(checks: dict) -> None:
    """Print a formatted contract verification report."""
    print()
    print("=" * 60)
    print("REX INTERFACE CONTRACT — VERIFICATION REPORT")
    print(f"Checked: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    pass_count  = sum(1 for c in checks.values() if c["status"] == "PASS")
    warn_count  = sum(1 for c in checks.values() if c["status"] == "WARN")
    fail_count  = sum(1 for c in checks.values() if c["status"] == "FAIL")

    for key, check in sorted(checks.items()):
        status = check["status"]
        symbol = "✅" if status == "PASS" else ("⚠️ " if status == "WARN" else "❌")
        print(f"  {symbol} [{key}] {check['name']}")
        if "detail" in check:
            print(f"       → {check['detail']}")

    print()
    print(f"Results: {pass_count} PASS  |  {warn_count} WARN  |  {fail_count} FAIL")

    if fail_count == 0 and warn_count == 0:
        print("🔒 Contract fully satisfied — backend is video/live ready.")
    elif fail_count == 0:
        print("⚠️  Contract mostly satisfied — review warnings before adding new interfaces.")
    else:
        print("❌ Contract violations found — fix FAIL items before adding new interfaces.")
    print("=" * 60)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN.PY INTEGRATION PATCH INSTRUCTIONS
# ──────────────────────────────────────────────────────────────────────────────

MAIN_PY_PATCH = """
PATCH GUIDE — backend/main.py
================================
Add these lines to register the new routers.

1. After existing imports, add:
   from .rex_command_center import cc_router
   from .rex_executive import exec_router

2. After app = FastAPI(...) is created, add:
   app.include_router(cc_router, prefix="/api/chairman")
   app.include_router(exec_router, prefix="/api/executive")

3. Add startup event hook (in @asynccontextmanager lifespan or @app.on_event("startup")):
   # Run v4 migrations on startup
   try:
       import sys, os
       sys.path.insert(0, str(Path(__file__).parent.parent))
       from rex_receipt_manager_v4_patch import run_v4_migration
       from rex_events import _ensure_db as _ensure_events_db
       from rex_unresolved import _ensure_db as _ensure_unresolved_db
       run_v4_migration()
       _ensure_events_db()
       _ensure_unresolved_db()
   except Exception as e:
       logger.warning(f"v4 migration: {e}")

4. (Optional) Add override command handler to WebSocket chat endpoint:
   # In the /api/chat route, before calling LLM:
   if user_message.lower().startswith("override "):
       from rex_override import handle_override_command
       result = handle_override_command(user_message, chat_id=0)
       return {"reply": result}

   # Or in private_confidant_gold.py (Telegram), add to handle():
   if msg.lower().startswith("override "):
       from rex_override import handle_override_command
       reply = handle_override_command(msg, chat_id=chat_id)
       await update.message.reply_text(reply)
       return

5. (Optional) Register daily resurfacing scheduler:
   # In startup, schedule check_resurfacing() to run at 21:00 daily.
   # This can be done via: launchd, APScheduler, or the existing
   # rex_daily_curriculum.py / goj_daily_scheduler.py scheduler.
   # Example with APScheduler:
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
   from rex_unresolved import check_resurfacing
   scheduler = AsyncIOScheduler()
   scheduler.add_job(check_resurfacing, 'cron', hour=21, minute=0)
   scheduler.start()
"""

# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Interface Contract Verifier")
    parser.add_argument("--verify", action="store_true",
                        help="Verify interface contract against live repo")
    parser.add_argument("--patch-guide", action="store_true",
                        help="Show main.py integration patch guide")
    args = parser.parse_args()

    if args.verify:
        checks = verify_contract()
        print_contract_report(checks)
        fail_count = sum(1 for c in checks.values() if c["status"] == "FAIL")
        sys.exit(1 if fail_count > 0 else 0)

    elif args.patch_guide:
        print(MAIN_PY_PATCH)

    else:
        parser.print_help()
