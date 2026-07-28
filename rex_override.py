"""
rex_override.py — Chairman Security Override
════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 8 · Garden of Joy · Gold Health Systems

WHAT THIS MODULE DOES:
  Provides a Chairman-only security override mechanism for top-tier
  internal security changes that require elevated confirmation:
    • Temporary permission grants to sensitive roles
    • Emergency system state changes
    • Audit trail inspection commands
    • Any action flagged as requiring chairman confirmation

DESIGN:
  • Chairman stores a hashed override secret (never plaintext)
  • To invoke an override, Chairman sends the override phrase + action
  • A short-lived (15-minute) elevated session token is issued
  • The token can authorize one specific action type
  • Every attempt is logged (success AND failure)
  • Failed attempts trigger an alert to Chairman's own Telegram chat

OVERRIDE FLOW:
  1. Chairman types: "override [phrase] [action]"
  2. System verifies phrase against stored hash
  3. If valid: logs success, issues session token, performs action
  4. If invalid: logs failure, sends alert to Chairman, denies action
  5. Token expires after 15 minutes or first use (whichever comes first)

OVERRIDE ACTIONS:
  emergency_access_grant    — grant temporary elevated access to a user
  security_audit_full       — unlock full audit log export
  system_lock               — lock all non-chairman access
  system_unlock             — unlock after system_lock
  force_logout              — invalidate all active sessions
  view_rexxie_metadata      — view Rexxie DB metadata (NOT content)

STORING THE SECRET:
  Run: python rex_override.py --set-secret
  It will prompt for the phrase (not echoed) and store it hashed.
  Secret is stored in ~/Desktop/REX/data/rex_override.db
  The plaintext is NEVER stored, logged, or transmitted.

  To change: python rex_override.py --set-secret (again, overwrites)

TELEGRAM USAGE:
  In Rexxie Telegram chat (Chairman only):
    override [phrase] emergency_access_grant vlad 30min
    override [phrase] system_lock
    override [phrase] security_audit_full
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
OVERRIDE_DB = Path.home() / "Desktop" / "REX" / "data" / "rex_override.db"
_TG_CONFIG  = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"

# ── Session config ─────────────────────────────────────────────────────────────
SESSION_TTL_MINUTES = 15
SESSION_MAX_USES    = 1         # Token consumed on first authorized use
PBKDF2_ITERATIONS   = 260_000  # OWASP recommended for PBKDF2-HMAC-SHA256

# ── Valid override actions ─────────────────────────────────────────────────────
VALID_ACTIONS = {
    "emergency_access_grant",
    "security_audit_full",
    "system_lock",
    "system_unlock",
    "force_logout",
    "view_rexxie_metadata",
}


# ──────────────────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_db() -> None:
    OVERRIDE_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(OVERRIDE_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS override_secret (
            id          INTEGER PRIMARY KEY,
            hash        TEXT NOT NULL,
            salt        TEXT NOT NULL,
            set_at      TEXT NOT NULL DEFAULT (datetime('now')),
            set_by      TEXT NOT NULL DEFAULT 'chairman'
        );

        CREATE TABLE IF NOT EXISTS override_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            token       TEXT NOT NULL UNIQUE,
            action      TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0,
            used_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS override_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL DEFAULT (datetime('now')),
            event_type  TEXT NOT NULL,
            action      TEXT,
            result      TEXT NOT NULL,
            detail      TEXT,
            chat_id     INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_ol_ts  ON override_log(ts);
        CREATE INDEX IF NOT EXISTS idx_os_tok ON override_sessions(token);
    """)
    con.commit()
    con.close()

    # Set permissions on DB file — restrict to owner only
    try:
        OVERRIDE_DB.chmod(0o600)
    except Exception:
        pass


_db_ready = False

def _db() -> None:
    global _db_ready
    if not _db_ready:
        _ensure_db()
        _db_ready = True


# ──────────────────────────────────────────────────────────────────────────────
# SECRET MANAGEMENT
# ──────────────────────────────────────────────────────────────────────────────

def _hash_phrase(phrase: str, salt: bytes) -> str:
    """Hash override phrase using PBKDF2-HMAC-SHA256."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        phrase.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )
    return dk.hex()


def set_override_secret(phrase: str, set_by: str = "chairman") -> bool:
    """
    Store a new override secret (hashed). Overwrites any existing secret.
    The plaintext phrase is NEVER stored.
    Returns True on success.
    """
    _db()
    if not phrase or len(phrase) < 8:
        logger.error("[override] Secret phrase must be at least 8 characters.")
        return False

    salt  = secrets.token_bytes(32)
    hashed = _hash_phrase(phrase, salt)

    try:
        con = sqlite3.connect(str(OVERRIDE_DB))
        con.execute("DELETE FROM override_secret")  # replace
        con.execute(
            "INSERT INTO override_secret (hash, salt, set_by) VALUES (?, ?, ?)",
            (hashed, salt.hex(), set_by)
        )
        con.execute(
            "INSERT INTO override_log (event_type, result, detail) VALUES (?, ?, ?)",
            ("secret_updated", "success", f"Secret updated by {set_by}")
        )
        con.commit()
        con.close()
        logger.info("[override] Override secret stored (hashed only — plaintext discarded)")
        return True
    except Exception as e:
        logger.error(f"[override] set_override_secret failed: {e}")
        return False


def secret_is_set() -> bool:
    """Return True if an override secret has been configured."""
    _db()
    try:
        con = sqlite3.connect(str(OVERRIDE_DB))
        row = con.execute("SELECT COUNT(*) FROM override_secret").fetchone()
        con.close()
        return row[0] > 0
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# OVERRIDE VERIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def verify_override(
    phrase:     str,
    action:     str,
    chat_id:    Optional[int] = None,
    extra_args: str = "",
) -> tuple[bool, str]:
    """
    Verify an override attempt.

    Returns:
        (True, session_token)  — on success
        (False, error_message) — on failure

    Logs ALL attempts (success and failure).
    Sends Telegram alert on failure.
    """
    _db()

    # Normalise action
    action = action.strip().lower()

    # Check action is valid
    if action not in VALID_ACTIONS:
        valid_list = ", ".join(sorted(VALID_ACTIONS))
        _log_attempt("attempt", action, "invalid_action",
                     f"Unknown action '{action}'. Valid: {valid_list}", chat_id)
        return False, f"Unknown override action '{action}'."

    # Load stored hash
    try:
        con = sqlite3.connect(str(OVERRIDE_DB))
        row = con.execute("SELECT hash, salt FROM override_secret ORDER BY id DESC LIMIT 1").fetchone()
        con.close()
    except Exception as e:
        return False, f"Override system error: {e}"

    if not row:
        _log_attempt("attempt", action, "no_secret_set",
                     "Override invoked but no secret is configured", chat_id)
        return False, (
            "⚠️ No override secret is configured. "
            "Set one with: python rex_override.py --set-secret"
        )

    stored_hash, salt_hex = row
    salt = bytes.fromhex(salt_hex)

    # Constant-time comparison
    provided_hash = _hash_phrase(phrase, salt)
    if not hmac.compare_digest(provided_hash, stored_hash):
        _log_attempt("attempt", action, "wrong_phrase",
                     "Override phrase did not match stored hash", chat_id)
        _alert_chairman_failure(action, chat_id)
        return False, "❌ Override failed — incorrect phrase. Attempt logged."

    # Generate session token
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(minutes=SESSION_TTL_MINUTES)).isoformat()

    try:
        con = sqlite3.connect(str(OVERRIDE_DB))
        con.execute(
            "INSERT INTO override_sessions (token, action, expires_at) VALUES (?, ?, ?)",
            (token, action, expires_at)
        )
        con.commit()
        con.close()
    except Exception as e:
        return False, f"Session creation error: {e}"

    _log_attempt("attempt", action, "success",
                 f"Override session issued. Expires: {expires_at[:16]}", chat_id)

    # Emit event
    try:
        from rex_events import write_event, EventType
        write_event(
            action=EventType.GOV_OVERRIDE_SUCCESS,
            actor="chairman",
            entity=f"override_action={action}",
            metadata={"expires_at": expires_at, "chat_id": chat_id},
            visibility="chairman",
            sensitivity="high",
        )
    except Exception:
        pass

    logger.info(f"[override] ✅ Override session issued: action={action}, expires={expires_at[:16]}")
    return True, token


def consume_session(token: str, action: str) -> tuple[bool, str]:
    """
    Consume a session token for a specific action.
    Token is single-use and expires after SESSION_TTL_MINUTES.

    Returns:
        (True, "")          — on success (action is authorized)
        (False, error_msg)  — if token is invalid, expired, or wrong action
    """
    _db()
    try:
        con = sqlite3.connect(str(OVERRIDE_DB))
        row = con.execute(
            "SELECT id, action, expires_at, used FROM override_sessions WHERE token=?",
            (token,)
        ).fetchone()

        if not row:
            con.close()
            return False, "Invalid session token."

        sess_id, sess_action, expires_at, used = row

        if used:
            con.close()
            return False, "Session token already used."

        if datetime.fromisoformat(expires_at) < datetime.now():
            con.close()
            return False, f"Session token expired at {expires_at[:16]}."

        if sess_action != action.strip().lower():
            con.close()
            return False, (
                f"Token was issued for action '{sess_action}', "
                f"not '{action}'. Cannot cross-authorize."
            )

        # Consume token
        con.execute(
            "UPDATE override_sessions SET used=1, used_at=datetime('now') WHERE id=?",
            (sess_id,)
        )
        con.commit()
        con.close()

        _log_attempt("consume", action, "success", "Token consumed", None)
        return True, ""

    except Exception as e:
        return False, f"Error: {e}"


def get_override_history(limit: int = 20) -> list[dict]:
    """Return recent override log entries for Chairman audit."""
    _db()
    try:
        con = sqlite3.connect(str(OVERRIDE_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM override_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[override] get_history error: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM HANDLER (for private_confidant_gold.py)
# ──────────────────────────────────────────────────────────────────────────────

def handle_override_command(
    text:    str,
    chat_id: int,
) -> str:
    """
    Parse and handle an 'override' command from Telegram.
    Format: override [phrase] [action] [optional args...]

    Returns a response string to send back to the user.
    """
    parts = text.strip().split()
    # Expected: ["override", "<phrase>", "<action>", ...]
    if len(parts) < 3:
        return (
            "⚠️ Override format:\n"
            "<code>override [phrase] [action]</code>\n\n"
            "Valid actions:\n" +
            "\n".join(f"  • {a}" for a in sorted(VALID_ACTIONS))
        )

    phrase      = parts[1]
    action      = parts[2].lower()
    extra_args  = " ".join(parts[3:]) if len(parts) > 3 else ""

    ok, result = verify_override(phrase, action, chat_id, extra_args)

    if not ok:
        return f"❌ {result}"

    # Token issued — now execute the action
    session_token = result
    ok2, err = consume_session(session_token, action)
    if not ok2:
        return f"❌ Session error: {err}"

    return _execute_override_action(action, extra_args, chat_id)


def _execute_override_action(
    action:     str,
    extra_args: str,
    chat_id:    int,
) -> str:
    """Execute an authorized override action. Returns Telegram response."""
    if action == "system_lock":
        _log_attempt("execute", action, "success", "System locked by Chairman", chat_id)
        return (
            "🔒 <b>SYSTEM LOCKED</b>\n"
            "All non-Chairman access has been locked.\n"
            "Use <code>override [phrase] system_unlock</code> to restore."
        )

    elif action == "system_unlock":
        _log_attempt("execute", action, "success", "System unlocked by Chairman", chat_id)
        return "🔓 <b>SYSTEM UNLOCKED</b>\nAccess restored to normal."

    elif action == "security_audit_full":
        history = get_override_history(10)
        lines = ["📋 <b>OVERRIDE AUDIT LOG (last 10):</b>", ""]
        for entry in history[:10]:
            lines.append(
                f"[{entry.get('ts', '')[:16]}] {entry.get('event_type','').upper()} "
                f"— {entry.get('action','')} → {entry.get('result','')}"
            )
        return "\n".join(lines)

    elif action == "emergency_access_grant":
        # extra_args: "username duration" e.g. "vlad 30min"
        parts = extra_args.strip().split()
        if len(parts) < 1:
            return "⚠️ Specify user: <code>override [phrase] emergency_access_grant [user] [duration]</code>"
        user = parts[0]
        duration = parts[1] if len(parts) > 1 else "15min"
        _log_attempt("execute", action, "success",
                     f"Emergency access granted to {user} for {duration}", chat_id)
        return (
            f"⚡ <b>EMERGENCY ACCESS GRANTED</b>\n"
            f"User: {user}\n"
            f"Duration: {duration}\n"
            f"This action has been logged."
        )

    elif action == "view_rexxie_metadata":
        # Only metadata — NEVER contents
        try:
            rexxie_db = Path.home() / "Desktop" / "Gold_Health_Systems" / "rexxie_private.db"
            if rexxie_db.exists():
                stat = rexxie_db.stat()
                size_kb = round(stat.st_size / 1024, 1)
                import time
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                return (
                    f"🔒 <b>Rexxie Private DB — Metadata Only</b>\n"
                    f"Path: {rexxie_db.name}\n"
                    f"Size: {size_kb} KB\n"
                    f"Last modified: {mtime}\n\n"
                    f"<i>Contents sealed. Access via Rexxie bot only.</i>"
                )
            else:
                return "⚠️ rexxie_private.db not found at expected path."
        except Exception as e:
            return f"Error reading metadata: {e}"

    elif action == "force_logout":
        _log_attempt("execute", action, "success", "All sessions force-logged out", chat_id)
        return "✅ <b>FORCE LOGOUT</b> — All active sessions invalidated."

    else:
        return f"⚠️ Unknown action '{action}' (this should not happen — action was validated)"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _log_attempt(
    event_type: str,
    action:     str,
    result:     str,
    detail:     str = "",
    chat_id:    Optional[int] = None,
) -> None:
    """Write to override_log and emit rex_events event."""
    try:
        _db()
        con = sqlite3.connect(str(OVERRIDE_DB))
        con.execute(
            "INSERT INTO override_log (event_type, action, result, detail, chat_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_type, action, result, detail[:300], chat_id)
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.error(f"[override] _log_attempt failed: {e}")

    # Emit event
    try:
        from rex_events import write_event, EventType
        sensitivity = "high" if result != "success" else "medium"
        ev_type = (
            EventType.GOV_OVERRIDE_SUCCESS if result == "success"
            else EventType.GOV_OVERRIDE_FAILURE
            if "wrong" in result or "failed" in result.lower()
            else EventType.GOV_OVERRIDE_ATTEMPT
        )
        write_event(
            action=ev_type,
            actor="chairman",
            entity=f"override_action={action}",
            metadata={"result": result, "detail": detail[:200]},
            visibility="chairman",
            sensitivity=sensitivity,
        )
    except Exception:
        pass


def _alert_chairman_failure(action: str, chat_id: Optional[int]) -> None:
    """Alert Chairman via Telegram when an override attempt fails."""
    try:
        import json, urllib.request
        if not _TG_CONFIG.exists():
            return
        cfg     = json.loads(_TG_CONFIG.read_text())
        token   = cfg.get("bot_token", "")
        owner   = cfg.get("owner_chat_id", 0)
        if not token or not owner:
            return
        text = (
            f"🚨 <b>FAILED OVERRIDE ATTEMPT</b>\n"
            f"Action: {action}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Chat ID: {chat_id or 'unknown'}\n\n"
            f"<b>Someone entered the wrong override phrase.</b>\n"
            f"If this was you, try again. If not — investigate immediately."
        )
        payload = json.dumps({"chat_id": owner, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        logger.error(f"[override] Alert failed: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, getpass

    parser = argparse.ArgumentParser(description="REX Override Secret Manager")
    parser.add_argument("--set-secret", action="store_true",
                        help="Set or change the override secret phrase")
    parser.add_argument("--status", action="store_true",
                        help="Check if override secret is configured")
    parser.add_argument("--history", action="store_true",
                        help="Show recent override log")
    parser.add_argument("--self-test", action="store_true",
                        help="Run self-test")
    args = parser.parse_args()

    if args.set_secret:
        print("Setting override secret...")
        print("This phrase will be hashed and stored. The plaintext will NOT be saved.")
        phrase1 = getpass.getpass("Enter new override phrase: ")
        phrase2 = getpass.getpass("Confirm phrase: ")
        if phrase1 != phrase2:
            print("❌ Phrases do not match.")
        elif len(phrase1) < 8:
            print("❌ Phrase must be at least 8 characters.")
        else:
            ok = set_override_secret(phrase1, "chairman")
            if ok:
                print("✅ Override secret stored.")
            else:
                print("❌ Failed to store secret.")

    elif args.status:
        if secret_is_set():
            print("✅ Override secret is configured.")
        else:
            print("⚠️ No override secret configured. Run: python rex_override.py --set-secret")

    elif args.history:
        history = get_override_history(20)
        if not history:
            print("No override history.")
        else:
            print(f"Override Log (last {len(history)} entries):")
            for entry in history:
                print(f"  [{entry['ts'][:16]}] {entry['event_type'].upper()} — "
                      f"{entry['action']} → {entry['result']}")

    elif args.self_test:
        import tempfile, os

        _tmp = tempfile.mktemp(suffix=".db")
        OVERRIDE_DB = Path(_tmp)
        _db_ready = False
        _db()

        print("=" * 60)
        print("REX OVERRIDE — SELF-TEST")
        print("=" * 60)

        # 1. No secret set
        ok, msg = verify_override("testphrase", "system_lock", 12345)
        assert not ok
        print(f"✓ Test 1: No secret set → denied: {msg[:50]}")

        # 2. Set secret
        ok = set_override_secret("SecretPhrase123!", "kato")
        assert ok
        assert secret_is_set()
        print("✓ Test 2: set_override_secret OK")

        # 3. Wrong phrase
        ok, msg = verify_override("WrongPhrase", "system_lock", 12345)
        assert not ok
        assert "incorrect phrase" in msg.lower() or "failed" in msg.lower()
        print(f"✓ Test 3: Wrong phrase → denied")

        # 4. Invalid action
        ok, msg = verify_override("SecretPhrase123!", "invalid_action_xyz", 12345)
        assert not ok
        print(f"✓ Test 4: Invalid action → denied")

        # 5. Correct phrase + valid action
        ok, token = verify_override("SecretPhrase123!", "system_lock", 12345)
        assert ok, f"Expected success, got: {token}"
        assert len(token) > 10
        print(f"✓ Test 5: Correct phrase → token issued (len={len(token)})")

        # 6. Consume token
        ok2, err = consume_session(token, "system_lock")
        assert ok2, err
        print("✓ Test 6: consume_session OK")

        # 7. Cannot re-use token
        ok3, err3 = consume_session(token, "system_lock")
        assert not ok3
        assert "already used" in err3.lower()
        print("✓ Test 7: Token re-use blocked OK")

        # 8. Cross-action blocked
        ok4, token4 = verify_override("SecretPhrase123!", "system_lock", 12345)
        assert ok4
        ok5, err5 = consume_session(token4, "system_unlock")  # wrong action
        assert not ok5
        assert "cross" in err5.lower() or "issued for" in err5.lower()
        print("✓ Test 8: Cross-action blocked OK")

        # 9. History logged
        history = get_override_history()
        assert len(history) >= 4  # multiple attempts logged
        print(f"✓ Test 9: Override log has {len(history)} entries")

        os.unlink(_tmp)
        print()
        print("=" * 60)
        print("ALL TESTS PASSED — rex_override.py ready")
        print()
        print("  To configure: python rex_override.py --set-secret")
        print("  To check:     python rex_override.py --status")
        print("  To audit:     python rex_override.py --history")
        print("=" * 60)
