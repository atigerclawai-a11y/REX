#!/usr/bin/env python3
"""
REX — Chairman Parameter Control Center
==========================================
Two-layer safety system for all REX configuration changes.

LAYER 1: Chat commands (in REX widget or standalone)
  — Fast, conversational, works from the dashboard
  — Requires Chairman role
  — Changes are logged to audit trail

LAYER 2: Command-line override (this script)
  — Independent of the chat/API system
  — Works even if chat interface is compromised or frozen
  — Requires physical access to the Mac
  — Has its own passphrase (separate from share passphrase)

This means: if someone overrides Layer 1, Layer 2 still works.
If Layer 2 somehow fails, Layer 1 still works. You always have control.

AVAILABLE PARAMETERS:
  Core security:
    secure_mode          on/off     (default: on)
    vault_mode           on/off     (Session toggle — use chat command for live)
    default_model        [model]    (e.g. ollama/llama3, anthropic/claude-sonnet-4-6)
    auto_ollama_on_phi   on/off     (switch to local model when PHI detected)

  Memory controls:
    wipe_memory          [confirm]  — soft-delete all memories
    wipe_sessions        [confirm]  — wipe session history
    wipe_all             [confirm]  — full sovereign reset
    reseed               [confirm]  — re-run seed scripts after wipe

  Notification:
    telegram_token       [token]
    telegram_chat_id     [chat_id]
    alert_email          [email]
    test_alert                      — fire a test alert immediately

  Agent bus:
    block_field          [name]     — add a field to BLOCKED_FIELDS (runtime)
    show_blocked                    — list all currently blocked fields

  Training:
    show_training_log               — print full training log
    clear_training_log   [confirm]  — wipe training history

EMERGENCY STOP COMMANDS (no passphrase required — physical access only):
    emergency_stop                  — halt REX, wipe sessions, alert Kato
    sovereign_reset      [confirm]  — full memory + session wipe

Usage:
  python rex_params.py --list
  python rex_params.py secure_mode off
  python rex_params.py wipe_memory confirm
  python rex_params.py emergency_stop
  python rex_params.py show_training_log
"""

import sys
import os
import json
import argparse
import getpass
import hashlib
from datetime import datetime
from pathlib import Path

REX_DIR = Path(__file__).parent
sys.path.insert(0, str(REX_DIR))

VENV_PY = REX_DIR / ".venv" / "bin" / "python"
if VENV_PY.exists():
    try:
        import cryptography
    except ImportError:
        os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)

PARAMS_PASSPHRASE_FILE = REX_DIR / ".rex_params_key"


# ── Parameter passphrase (separate from share passphrase) ─────────────────────

def _hash(s: str) -> str:
    return hashlib.sha256(s.strip().encode()).hexdigest()


def has_params_passphrase() -> bool:
    return PARAMS_PASSPHRASE_FILE.exists()


def set_params_passphrase(passphrase: str):
    PARAMS_PASSPHRASE_FILE.write_text(_hash(passphrase))
    PARAMS_PASSPHRASE_FILE.chmod(0o600)
    print("✅ Parameters passphrase set.")


def verify_params_passphrase(candidate: str) -> bool:
    if not has_params_passphrase():
        return True  # No passphrase set — allow (first-run mode)
    stored = PARAMS_PASSPHRASE_FILE.read_text().strip()
    import hmac
    return hmac.compare_digest(stored, _hash(candidate))


def require_passphrase():
    if not has_params_passphrase():
        print("⚠️  No params passphrase set. Run: python rex_params.py --set-passphrase")
        print("   Proceeding without passphrase (first-run mode)\n")
        return True
    pw = getpass.getpass("Chairman params passphrase: ")
    if not verify_params_passphrase(pw):
        print("❌ Incorrect passphrase. Access denied.")
        sys.exit(1)
    return True


# ── Parameter handlers ────────────────────────────────────────────────────────

def handle_secure_mode(value: str):
    from backend.config import Settings
    s = Settings()
    enabled = value.lower() in ("on", "true", "1", "yes")
    s.secure_mode = enabled
    print(f"✅ secure_mode → {'ON' if enabled else 'OFF'}")
    _audit_log(f"secure_mode changed to {enabled}")


def handle_default_model(value: str):
    from backend.config import Settings
    s = Settings()
    s.default_model = value
    print(f"✅ default_model → {value}")
    if "ollama" not in value.lower():
        print("⚠️  WARNING: Non-local model selected. Secure mode still ON, but queries go to cloud AI.")
    _audit_log(f"default_model changed to {value}")


def handle_wipe_memory(confirm: str):
    if confirm.lower() != "confirm":
        print("❌ Must pass 'confirm' to wipe memory. Example: python rex_params.py wipe_memory confirm")
        return
    require_passphrase()
    from backend.storage import EncryptedStorage
    from backend.memory import RexMemory
    storage = EncryptedStorage()
    mem = RexMemory(db_path=storage.db_path, key=storage._key)
    count = mem._emergency_wipe_memory()
    print(f"🗑️  Memory wiped: {count} entries removed")
    _audit_log(f"EMERGENCY: memory wiped ({count} entries)")
    _notify_audit(f"Memory wipe executed from rex_params.py — {count} entries removed")


def handle_wipe_sessions(confirm: str):
    if confirm.lower() != "confirm":
        print("❌ Must pass 'confirm'. Example: python rex_params.py wipe_sessions confirm")
        return
    require_passphrase()
    from backend.storage import EncryptedStorage
    from backend.memory import RexMemory
    storage = EncryptedStorage()
    mem = RexMemory(db_path=storage.db_path, key=storage._key)
    count = mem._emergency_wipe_sessions()
    print(f"🗑️  Sessions wiped: {count} records removed")
    _audit_log(f"EMERGENCY: sessions wiped ({count} records)")


def handle_wipe_all(confirm: str):
    if confirm.lower() != "confirm":
        print("❌ Must pass 'confirm'. This wipes ALL memory and sessions.")
        return
    require_passphrase()
    print("⚠️  SOVEREIGN RESET — this cannot be undone")
    double_confirm = input("Type 'RESET' to confirm full wipe: ").strip()
    if double_confirm != "RESET":
        print("❌ Cancelled.")
        return
    from backend.storage import EncryptedStorage
    from backend.memory import RexMemory
    storage = EncryptedStorage()
    mem = RexMemory(db_path=storage.db_path, key=storage._key)
    m = mem._emergency_wipe_memory()
    s = mem._emergency_wipe_sessions()
    print(f"🔴 SOVEREIGN RESET: {m} memories + {s} sessions wiped")
    print("   Run seed scripts to restore foundational knowledge:")
    print("   python seed_rex_memory.py && python seed_rex_from_claude.py")
    _audit_log(f"SOVEREIGN RESET: {m} memories + {s} sessions wiped")
    _notify_audit(f"SOVEREIGN RESET executed — {m} memories + {s} sessions wiped")


def handle_telegram_token(token: str):
    from backend.rex_notify import RexNotify
    n = RexNotify()
    n._cfg["telegram_token"] = token
    n._save_config()
    print("✅ Telegram token saved")


def handle_telegram_chat(chat_id: str):
    from backend.rex_notify import RexNotify
    n = RexNotify()
    n._cfg["telegram_chat_id"] = chat_id
    n._save_config()
    print("✅ Telegram Chat ID saved")


def handle_alert_email(email: str):
    from backend.rex_notify import RexNotify
    n = RexNotify()
    n.set_alert_email(email)
    print(f"✅ Alert email set to {email}")


def handle_test_alert():
    from backend.rex_notify import RexNotify
    n = RexNotify()
    result = n.test_alert()
    print(f"📲 Telegram: {'✅ Sent' if result.get('telegram') else '❌ Failed'}")
    print(f"📧 Gmail:    {'✅ Sent' if result.get('gmail') else '📄 Saved to alerts/'}")


def handle_show_training_log():
    from backend.storage import EncryptedStorage
    from backend.rex_training import RexTraining
    storage = EncryptedStorage()
    t = RexTraining(db_path=str(storage.db_path))
    print(t.get_training_log(limit=100))


def handle_show_blocked():
    from backend.agent_bus import BLOCKED_FIELDS
    print(f"\n🔒 Agent Bus BLOCKED_FIELDS ({len(BLOCKED_FIELDS)} fields):\n")
    for i, f in enumerate(sorted(BLOCKED_FIELDS), 1):
        print(f"  {i:3}. {f}")
    print()


def handle_emergency_stop():
    """No passphrase required — physical access protection."""
    print("\n🔴 EMERGENCY STOP")
    print("This will: halt REX, wipe all sessions, and alert Kato.\n")
    confirm = input("Type 'STOP' to confirm: ").strip()
    if confirm != "STOP":
        print("❌ Cancelled.")
        return
    try:
        # Wipe sessions only — preserve memory for forensics
        from backend.storage import EncryptedStorage
        from backend.memory import RexMemory
        storage = EncryptedStorage()
        mem = RexMemory(db_path=storage.db_path, key=storage._key)
        s = mem._emergency_wipe_sessions()
        print(f"✅ Sessions wiped: {s}")
    except Exception as e:
        print(f"⚠️  Could not wipe sessions: {e}")
    try:
        _notify_audit("🔴 EMERGENCY STOP executed from rex_params.py (physical access)")
    except Exception:
        pass
    _audit_log("EMERGENCY STOP: sessions wiped, REX halted")
    print("🔴 REX halted. Restart with: cd ~/Desktop/REX && ./run.sh")


# ── List all parameters ────────────────────────────────────────────────────────

def handle_list():
    from backend.config import Settings
    from backend.rex_notify import RexNotify
    from backend.rex_vault import ChairmanVault
    try:
        s = Settings()
        n = RexNotify()
        status = n.is_configured()
        print("\n" + "=" * 60)
        print("REX SOVEREIGN — CURRENT PARAMETER STATE")
        print("=" * 60)
        print(f"\n🔐 SECURITY")
        print(f"  secure_mode:        {'ON ✅' if s.secure_mode else 'OFF ⚠️'}")
        print(f"  default_model:      {s.default_model}")
        print(f"  vault_mode:         [session-based — use chat 'vault status']")
        print(f"\n📲 NOTIFICATIONS")
        print(f"  telegram:           {'✅ Configured' if status['telegram'] else '❌ Not set'}")
        print(f"  alert_email:        {'✅ ' + n._cfg.get('alert_email','') if status['gmail'] else '❌ Not set'}")
        print(f"\n🔑 PASSPHRASE PROTECTION")
        print(f"  params_passphrase:  {'✅ Set' if has_params_passphrase() else '⚠️  Not set (any user can change params!)'}")
        print(f"\n⚡ EMERGENCY COMMANDS (no passphrase needed)")
        print(f"  python rex_params.py emergency_stop")
        print(f"  python rex_params.py wipe_all confirm  (passphrase required)")
        print(f"\n📋 ALL COMMANDS")
        print(f"  python rex_params.py --help")
        print()
    except Exception as e:
        print(f"Error reading config: {e}")


# ── Audit helpers ─────────────────────────────────────────────────────────────

def _audit_log(message: str):
    log_path = REX_DIR / "rex_params_audit.log"
    ts = datetime.utcnow().isoformat()
    with open(log_path, "a") as f:
        f.write(f"{ts} | PARAMS | {message}\n")


def _notify_audit(message: str):
    try:
        from backend.rex_notify import RexNotify
        n = RexNotify()
        n.alert(
            level="WARNING",
            title="REX Parameter Change (CLI)",
            details=f"A parameter was changed via rex_params.py (physical CLI access):\n\n{message}",
            source="rex_params.py",
        )
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

COMMANDS = {
    "secure_mode":       (handle_secure_mode,    "on|off"),
    "default_model":     (handle_default_model,  "model-name"),
    "wipe_memory":       (handle_wipe_memory,     "confirm"),
    "wipe_sessions":     (handle_wipe_sessions,  "confirm"),
    "wipe_all":          (handle_wipe_all,        "confirm"),
    "telegram_token":    (handle_telegram_token,  "token"),
    "telegram_chat_id":  (handle_telegram_chat,   "chat-id"),
    "alert_email":       (handle_alert_email,     "email"),
    "test_alert":        (handle_test_alert,      None),
    "show_training_log": (handle_show_training_log, None),
    "show_blocked":      (handle_show_blocked,    None),
    "emergency_stop":    (handle_emergency_stop,  None),
}


def main():
    parser = argparse.ArgumentParser(
        description="REX Chairman Parameter Control Center",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\nAvailable commands:\n" + "\n".join(
            f"  {k:20} {v}" for k, (_, v) in COMMANDS.items() if v
        ) + "\n" + "\n".join(
            f"  {k:20} (no args)" for k, (_, v) in COMMANDS.items() if not v
        ),
    )
    parser.add_argument("command",  nargs="?", help="Parameter to change")
    parser.add_argument("value",    nargs="?", help="New value")
    parser.add_argument("--list",              action="store_true", help="Show current state of all params")
    parser.add_argument("--set-passphrase",    action="store_true", help="Set the params access passphrase")

    args = parser.parse_args()

    if args.set_passphrase:
        pw  = getpass.getpass("New params passphrase: ")
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            print("❌ Passphrases don't match.")
            sys.exit(1)
        set_params_passphrase(pw)
        sys.exit(0)

    if args.list or not args.command:
        handle_list()
        sys.exit(0)

    cmd = args.command.lower()

    if cmd not in COMMANDS:
        print(f"❌ Unknown command: {cmd}")
        print(f"   Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    handler, needs_value = COMMANDS[cmd]

    # Emergency stop never needs passphrase
    if cmd != "emergency_stop" and cmd not in ("test_alert", "show_training_log", "show_blocked"):
        require_passphrase()

    if needs_value:
        if not args.value:
            print(f"❌ This command requires a value: {needs_value}")
            sys.exit(1)
        handler(args.value)
    else:
        handler()


if __name__ == "__main__":
    main()
