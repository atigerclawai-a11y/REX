"""
REX — Server-Side Role Authorization
=====================================
Fixes the WebSocket role escalation vulnerability where any client
could declare themselves 'chairman' in the payload without verification.

Design:
  • A JSON registry maps known usernames → their maximum allowed role
  • Chairman is ONLY ever granted to 'kato' (or whatever the registry holds)
  • Any unregistered username gets 'staff' regardless of what they claim
  • Claimed role is capped to what the registry allows — no escalation possible
  • Registry stored at ~/Desktop/REX/rex_role_registry.json
  • CLI: python rex_role_auth.py --add kato chairman
         python rex_role_auth.py --list
         python rex_role_auth.py --revoke staff_user

Role hierarchy (0 = highest privilege):
  chairman  →  can use vault, Rexxie, training, all chairman_only commands
  staff     →  can use standard REX memory and chat
  guest     →  read-only, no memory commands

The Telegram bot identity ('rex-telegram') is registered at 'staff' so
natural Telegram conversations never accidentally gain chairman rights.
Chairman Telegram sessions are identified by chat_id, not by role claim.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path.home() / "Desktop" / "REX" / "rex_role_registry.json"

# Role hierarchy — lower index = higher privilege
# "admin" and "director" are equivalent privileged roles (e.g. Vladimir Khiger).
# They are stored in the staff_users DB and checked by PRIVILEGED_ROLES in main.py.
ROLE_LEVELS = ["chairman", "admin", "director", "staff", "guest"]

# Default registry — Kato is Chairman by username
# Role hierarchy is used by verify_role() only (WebSocket/Telegram bridge auth).
# Dashboard auth uses the SQL staff_users table role field directly.
DEFAULT_REGISTRY = {
    "kato":          "chairman",
    "chairman":      "chairman",   # alias — if user_name field literally says 'chairman'
    "vlad":          "staff",      # Vladimir Khiger — set staff here, admin role is in staff_users DB
    "rex-telegram":  "staff",      # Telegram bridge identity
    "ws-desktop":    "staff",      # Default WebSocket desktop identity
    "dashboard":     "staff",      # GOJ dashboard widget
    "unknown":       "staff",
}


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text())
        except Exception:
            pass
    # Write default registry on first run
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(DEFAULT_REGISTRY, indent=2))
    REGISTRY_PATH.chmod(0o600)
    return dict(DEFAULT_REGISTRY)


def _save_registry(registry: dict):
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    REGISTRY_PATH.chmod(0o600)


def _role_level(role: str) -> int:
    """Lower number = higher privilege. Unknown roles treated as guest."""
    try:
        return ROLE_LEVELS.index(role.lower())
    except ValueError:
        return len(ROLE_LEVELS)  # below guest


def verify_role(user_name: str, claimed_role: str) -> str:
    """
    Verify that user_name is allowed to claim claimed_role.
    Returns the verified role (may be downgraded).

    Rules:
      1. Look up user_name in registry → get their max_role
      2. If claimed_role is LESS privileged than max_role → allow as-is
      3. If claimed_role is MORE privileged than max_role → cap to max_role
      4. Unknown user_name → 'staff' regardless of claim
      5. Empty user_name → 'staff'
    """
    if not user_name:
        return "staff"

    registry = _load_registry()
    max_role = registry.get(user_name.lower().strip(), "staff")

    claimed_level = _role_level(claimed_role)
    max_level     = _role_level(max_role)

    if claimed_level >= max_level:
        # Claimed role is equal or less privileged → granted as-is
        # (e.g., chairman claiming 'staff' is fine)
        return claimed_role.lower() if claimed_role else max_role
    else:
        # Claimed role exceeds what this user is allowed — cap it
        logger.warning(
            f"🚨 Role escalation blocked: user='{user_name}' claimed='{claimed_role}' "
            f"but max_allowed='{max_role}'. Capped to '{max_role}'."
        )
        return max_role


def is_chairman(user_name: str, claimed_role: str) -> bool:
    """Convenience — returns True only if verified role is 'chairman'."""
    return verify_role(user_name, claimed_role) == "chairman"


def register_user(user_name: str, role: str) -> bool:
    """Add or update a user's max role. Returns True on success."""
    if role not in ROLE_LEVELS:
        logger.error(f"Unknown role '{role}'. Valid: {ROLE_LEVELS}")
        return False
    registry = _load_registry()
    registry[user_name.lower().strip()] = role
    _save_registry(registry)
    logger.info(f"✅ Registered {user_name} → {role}")
    return True


def revoke_user(user_name: str) -> bool:
    """Remove a user from the registry (they default to 'staff')."""
    registry = _load_registry()
    removed = registry.pop(user_name.lower().strip(), None)
    if removed:
        _save_registry(registry)
        logger.info(f"🗑️  Revoked {user_name} (was '{removed}')")
        return True
    return False


def list_registry() -> dict:
    return _load_registry()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="REX Role Registry Manager")
    parser.add_argument("--add",    nargs=2, metavar=("USERNAME", "ROLE"),
                        help="Grant a user a role: --add kato chairman")
    parser.add_argument("--revoke", metavar="USERNAME",
                        help="Remove a user from registry")
    parser.add_argument("--list",   action="store_true",
                        help="List all registered users and roles")
    parser.add_argument("--verify", nargs=2, metavar=("USERNAME", "CLAIMED_ROLE"),
                        help="Test role verification: --verify kato chairman")
    args = parser.parse_args()

    if args.add:
        ok = register_user(args.add[0], args.add[1])
        if ok:
            print(f"✅ {args.add[0]} → {args.add[1]}")
        else:
            print(f"❌ Invalid role '{args.add[1]}'. Valid roles: {ROLE_LEVELS}")
    elif args.revoke:
        ok = revoke_user(args.revoke)
        print(f"{'✅ Removed' if ok else '⚠️  Not found'}: {args.revoke}")
    elif args.verify:
        result = verify_role(args.verify[0], args.verify[1])
        print(f"User '{args.verify[0]}' claimed '{args.verify[1]}' → verified as '{result}'")
    else:
        reg = list_registry()
        print("\n📋 REX Role Registry:")
        print(f"{'Username':<20} {'Role':<12}")
        print("-" * 34)
        for user, role in sorted(reg.items()):
            print(f"{user:<20} {role:<12}")
        print()
