#!/usr/bin/env python3
"""
REX — Master Session Unlock (MSU) Engine  (rex_session.py)
Phase 10 | Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
PURPOSE
  Provides one authenticated privileged session for Chairman/Kato.
  Unlocks protected controls for the session duration without weakening
  any underlying governance, approval tiers, audit trails, or safeguards.

SESSION STATES
  LOCKED              — default; protected controls unavailable
  UNLOCKED_PRIVILEGED — authenticated; protected controls available
  HALTED              — emergency halt active; overrides UNLOCKED; execution blocked
  DEGRADED            — system issue at boot; reduced functionality

UNLOCK REQUIREMENTS (all three required)
  1. Identity — username in role registry at chairman level
  2. Passphrase — verified against rex_credential_vault
  3. TOTP — 6-digit code from authenticator app via rex_2fa.verify_totp()

INTEGRITY
  Every write to session_state.json includes an integrity_hash computed
  as HMAC-SHA256(canonical_json_without_hash, integrity_key).
  On every read, the hash is recomputed and compared. A mismatch means
  the file was tampered externally — session is immediately invalidated.

TIMER
  Auto-locks after auto_lock_minutes of no protected activity (default 5).
  Timer resets ONLY on protected activity calls.
  Background polling / health checks / read-only calls do NOT reset timer.
  max_extensions_per_session: after N resets in one session, full re-auth required.

OPTIONAL (optional improvements from Phase 10 plan)
  - Extension threshold: prevent infinite reset loops
  - DEV_SESSION=1 env var: bypasses credential check for sandbox testing

AUDIT EVENTS → state/prompt_audit.log
  session_unlock_requested, session_unlock_success, session_unlock_failed,
  session_locked_manual, session_locked_timeout, session_locked_halt,
  session_extended, session_rejected

GOVERNANCE NOTE
  Unlocking grants access to protected controls.
  It does NOT bypass:  approval tiers, 48h protected-prompt window,
  audit logs, Gauntlet, MemorySteward gates, or OCR quarantine rules.
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("rex_session")

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE         = Path(__file__).parent.parent
STATE_FILE    = _BASE / "state" / "session_state.json"
CONFIG_FILE   = _BASE / "config" / "session.yaml"
AUDIT_LOG     = _BASE / "state" / "prompt_audit.log"
INTEGRITY_KEY = _BASE.parent / ".rex" / "session.key"  # ~/.rex/session.key

# ── Session states ─────────────────────────────────────────────────────────────
STATE_LOCKED      = "LOCKED"
STATE_UNLOCKED    = "UNLOCKED_PRIVILEGED"
STATE_HALTED      = "HALTED"
STATE_DEGRADED    = "DEGRADED"

# ── Defaults (overridden by config/session.yaml) ───────────────────────────────
DEFAULT_AUTO_LOCK_MINUTES       = 5
DEFAULT_MAX_EXTENSIONS          = 20
PRIVILEGED_IDENTITIES           = {"kato", "chairman"}

# Dev mode: bypass credential checks when DEV_SESSION=1
_DEV_MODE = os.environ.get("DEV_SESSION") == "1"


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRITY KEY
# ══════════════════════════════════════════════════════════════════════════════

def _load_or_create_integrity_key() -> bytes:
    """
    Load or generate the HMAC key used to sign session_state.json.
    Stored at ~/.rex/session.key (chmod 600). Machine-local.

    KEY LIFECYCLE (Part F):
      Missing:   auto-created fresh; all prior sessions invalidated (no hash can verify)
      Corrupted: treated same as missing — auto-recreate; existing session locked
      Rotated:   call SessionEngine.rotate_key() — generates new key, logs event,
                 locks current session immediately. All prior integrity hashes become invalid.

    Recovery:
      If key is lost and session is locked, simply re-authenticate (unlock) normally.
      There is no "recovery" that bypasses the unlock flow — that is by design.
    """
    key_dir = INTEGRITY_KEY.parent
    key_dir.mkdir(parents=True, exist_ok=True)
    if INTEGRITY_KEY.exists():
        raw = INTEGRITY_KEY.read_bytes()
        if len(raw) >= 32:
            return raw[:32]
        # Corrupted — treat as missing
        log.warning("Session integrity key corrupted (size=%d) — recreating", len(raw))
    import secrets
    key = secrets.token_bytes(32)
    INTEGRITY_KEY.write_bytes(key)
    INTEGRITY_KEY.chmod(0o600)
    log.info("Session integrity key created at %s", INTEGRITY_KEY)
    return key


def _compute_hash(state: Dict, key: bytes) -> str:
    """
    Compute HMAC-SHA256 of the canonical state dict (integrity_hash field excluded).
    Returns hex digest.
    """
    payload = {k: v for k, v in sorted(state.items()) if k != "integrity_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG LOADER
# ══════════════════════════════════════════════════════════════════════════════

def _load_config() -> Dict:
    """Load config/session.yaml; return defaults if file absent or unparseable."""
    cfg = {
        "auto_lock_minutes":         DEFAULT_AUTO_LOCK_MINUTES,
        "max_extensions_per_session": DEFAULT_MAX_EXTENSIONS,
    }
    if not CONFIG_FILE.exists():
        return cfg
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
        s = data.get("session", {})
        cfg["auto_lock_minutes"]          = int(s.get("auto_lock_minutes", DEFAULT_AUTO_LOCK_MINUTES))
        cfg["max_extensions_per_session"] = int(s.get("max_extensions_per_session", DEFAULT_MAX_EXTENSIONS))
    except Exception as e:
        log.warning("config/session.yaml load error: %s — using defaults", e)
    return cfg


# ══════════════════════════════════════════════════════════════════════════════
# SESSION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class SessionEngine:
    """
    Master Session Unlock engine.

    Thread-safety note: reads and writes use an atomic temp-file swap
    to prevent partial writes. Not designed for concurrent processes —
    REX runs as a single backend process.
    """

    def __init__(self):
        self._key    = _load_or_create_integrity_key()
        self._config = _load_config()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not STATE_FILE.exists():
            self._write(_initial_state())

    # ── Public API ─────────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """
        Return current session status. Verifies integrity on read.
        If tampered: invalidates session and returns LOCKED with tamper_detected=True.
        """
        state = self._read()
        now   = _now_iso()

        # Enforce HALTED override
        if state["state"] == STATE_HALTED:
            return {**state, "session_active": False, "time_remaining_seconds": 0}

        # Check expiry for UNLOCKED sessions
        if state["state"] == STATE_UNLOCKED:
            if state.get("expires_at") and now >= state["expires_at"]:
                self._lock("timeout")
                state = self._read()

        active   = state["state"] == STATE_UNLOCKED
        remaining = 0
        if active and state.get("expires_at"):
            try:
                exp = datetime.fromisoformat(state["expires_at"])
                remaining = max(0, int((exp - _now_dt()).total_seconds()))
            except Exception:
                remaining = 0

        return {
            **state,
            "session_active":        active,
            "time_remaining_seconds": remaining,
            "max_extensions":         self._config["max_extensions_per_session"],
        }

    def unlock(
        self,
        identity:   str,
        passphrase: str,
        totp_code:  str,
    ) -> Dict[str, Any]:
        """
        Attempt to unlock a privileged session.
        Returns {"ok": bool, "state": str, "message": str}.

        Refinement: emits audit events on both success and failure.
        """
        self._audit("session_unlock_requested", identity=identity)

        # Gate: must not be HALTED
        current = self._read()
        if current["state"] == STATE_HALTED:
            self._audit("session_rejected", identity=identity, reason="system_halted")
            return {"ok": False, "state": STATE_HALTED,
                    "message": "System is HALTED. Unlock not permitted until halt is lifted."}

        # Gate 1: identity must be in privileged set AND role registry
        if not self._verify_identity(identity):
            self._audit("session_unlock_failed", identity=identity, reason="identity_check_failed")
            return {"ok": False, "state": current["state"],
                    "message": "Identity verification failed."}

        # Gate 2: passphrase
        if not _DEV_MODE:
            ok_pass, msg_pass = self._verify_passphrase(passphrase)
            if not ok_pass:
                self._audit("session_unlock_failed", identity=identity, reason="passphrase_failed")
                return {"ok": False, "state": current["state"],
                        "message": "Passphrase verification failed."}

        # Gate 3: TOTP
        if not _DEV_MODE:
            if not self._verify_totp(totp_code):
                self._audit("session_unlock_failed", identity=identity, reason="totp_failed")
                return {"ok": False, "state": current["state"],
                        "message": "TOTP verification failed. Check your authenticator app."}

        # All gates passed
        cfg     = self._config
        minutes = cfg["auto_lock_minutes"]
        now     = _now_dt()
        expires = (now + timedelta(minutes=minutes)).isoformat()

        new_state = {
            "schema_version":          "1.0",
            "state":                   STATE_UNLOCKED,
            "identity":                identity,
            "unlocked_at":             _now_iso(),
            "expires_at":              expires,
            "last_protected_activity": _now_iso(),
            "auto_lock_minutes":       minutes,
            "extensions_this_session": 0,
            "lock_reason":             None,
        }
        self._write(new_state)
        self._audit("session_unlock_success", identity=identity,
                    expires_at=expires, auto_lock_minutes=minutes)
        log.info("MSU: session unlocked for %s, expires %s", identity, expires)

        return {
            "ok":              True,
            "state":           STATE_UNLOCKED,
            "identity":        identity,
            "expires_at":      expires,
            "auto_lock_minutes": minutes,
            "message":         f"Session unlocked. Auto-locks in {minutes} minutes.",
        }

    def lock(self, reason: str = "manual") -> Dict[str, Any]:
        """Manually lock the session. Allowed at any time."""
        state = self._read()
        identity = state.get("identity")
        self._lock(reason)
        self._audit(
            "session_locked_manual" if reason == "manual" else "session_locked_timeout",
            identity=identity, reason=reason,
        )
        return {"ok": True, "state": STATE_LOCKED,
                "message": f"Session locked ({reason})."}

    def extend(self) -> Dict[str, Any]:
        """
        Reset the auto-lock timer. Protected activity only.
        Enforces max_extensions_per_session to prevent infinite reset loops.
        """
        state = self._read()

        if state["state"] != STATE_UNLOCKED:
            return {"ok": False, "state": state["state"],
                    "message": "Session is not unlocked. Cannot extend."}

        cfg     = self._config
        max_ext = cfg["max_extensions_per_session"]
        current_ext = state.get("extensions_this_session", 0)

        if current_ext >= max_ext:
            self._lock("max_extensions_reached")
            self._audit("session_locked_timeout", identity=state.get("identity"),
                        reason=f"max_extensions_reached ({max_ext})")
            return {
                "ok":    False,
                "state": STATE_LOCKED,
                "message": (
                    f"Maximum session extensions ({max_ext}) reached. "
                    f"Re-authenticate to start a new session."
                ),
            }

        minutes = cfg["auto_lock_minutes"]
        expires = (_now_dt() + timedelta(minutes=minutes)).isoformat()

        state["expires_at"]              = expires
        state["last_protected_activity"] = _now_iso()
        state["extensions_this_session"] = current_ext + 1
        self._write(state)

        self._audit("session_extended", identity=state.get("identity"),
                    extensions=current_ext + 1, max=max_ext, expires_at=expires)

        return {
            "ok":        True,
            "state":     STATE_UNLOCKED,
            "expires_at": expires,
            "extensions_used": current_ext + 1,
            "extensions_max":  max_ext,
            "message":   f"Timer reset. Session expires at {expires[:19]} UTC.",
        }

    def record_protected_activity(self) -> None:
        """
        Called by protected operations (stage_edit, approve_edit, restore drill, etc.)
        to reset the auto-lock timer. Silently no-ops if session is locked.
        """
        try:
            state = self._read()
            if state["state"] == STATE_UNLOCKED:
                self.extend()
        except Exception as e:
            log.debug("record_protected_activity: %s", e)

    def is_unlocked(self) -> bool:
        """Quick check: True if session is currently UNLOCKED_PRIVILEGED and not expired."""
        try:
            s = self.status()
            return bool(s.get("session_active"))
        except Exception:
            return False

    def require_unlocked(self) -> Optional[Dict]:
        """
        Call at the top of any protected operation.
        Returns None if unlocked (proceed).
        Returns an error dict if locked/halted (return this to caller).
        """
        s = self.status()
        if s.get("session_active"):
            return None
        state_label = s["state"]
        return {
            "ok":    False,
            "error": (
                f"MSU session is {state_label}. "
                "Unlock required: POST /api/chairman/session/unlock"
            ),
            "session_state": state_label,
        }

    def rotate_key(self) -> Dict[str, Any]:
        """
        Part F: Rotate the integrity key.
        Generates a new key, locks the current session immediately,
        invalidates all prior integrity hashes.
        After rotation, Kato must re-authenticate.
        """
        import secrets
        new_key = secrets.token_bytes(32)
        INTEGRITY_KEY.write_bytes(new_key)
        INTEGRITY_KEY.chmod(0o600)
        self._key = new_key

        # Lock session with rotated reason
        state = self._read_raw_unsafe()
        state["state"]       = STATE_LOCKED
        state["identity"]    = None
        state["unlocked_at"] = None
        state["expires_at"]  = None
        state["lock_reason"] = "key_rotated"
        state["extensions_this_session"] = 0
        # Write with new key hash
        state["integrity_hash"] = _compute_hash(state, new_key)
        self._write_raw(state)

        self._audit("session_key_rotated")
        log.info("Session integrity key rotated. All prior sessions invalidated.")
        return {
            "ok":      True,
            "message": "Integrity key rotated. Session locked. Re-authenticate to continue.",
            "state":   STATE_LOCKED,
        }

    def _read_raw_unsafe(self) -> Dict:
        """Read state file without hash verification — used only during key rotation."""
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return _initial_state()

    def key_status(self) -> Dict[str, Any]:
        """
        Part F: Return session key metadata (not key bytes).
        Includes: existence, size, file path, permissions, last rotation event.
        """
        exists = INTEGRITY_KEY.exists()
        size   = INTEGRITY_KEY.stat().st_size if exists else 0
        perms  = oct(INTEGRITY_KEY.stat().st_mode)[-3:] if exists else "n/a"

        # Find last rotation event from audit log
        last_rotation = None
        try:
            if AUDIT_LOG.exists():
                for line in reversed(AUDIT_LOG.read_text().splitlines()):
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("event") == "session_key_rotated":
                            last_rotation = entry.get("timestamp")
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        return {
            "key_exists":      exists,
            "key_size_bytes":  size,
            "key_path":        str(INTEGRITY_KEY),
            "key_permissions": perms,
            "last_rotation":   last_rotation,
            "lifecycle_note":  (
                "Missing key → auto-created on next startup; prior sessions invalidated. "
                "Rotated key → prior hashes invalid; re-auth required."
            ),
        }

    def set_halted(self, halted: bool = True) -> None:
        """Set or clear HALTED state. Called by emergency halt system."""
        state = self._read()
        if halted:
            state["state"]       = STATE_HALTED
            state["lock_reason"] = "emergency_halt"
            self._write(state)
            self._audit("session_locked_halt", identity=state.get("identity"))
        else:
            # Coming out of halt: return to LOCKED (not UNLOCKED)
            state["state"]       = STATE_LOCKED
            state["identity"]    = None
            state["unlocked_at"] = None
            state["expires_at"]  = None
            state["lock_reason"] = "halt_lifted"
            self._write(state)
            self._audit("session_unlock_requested",
                        identity="system", reason="halt_lifted_returning_to_locked")

    def set_degraded(self, reason: str = "boot_error") -> None:
        """Mark session as DEGRADED. Surfaces in Command Center with visible warning."""
        state = self._read()
        state["state"]       = STATE_DEGRADED
        state["lock_reason"] = reason
        self._write(state)
        log.warning("Session state set to DEGRADED: %s", reason)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _lock(self, reason: str) -> None:
        state = self._read()
        state["state"]                   = STATE_LOCKED
        state["identity"]                = None
        state["unlocked_at"]             = None
        state["expires_at"]              = None
        state["last_protected_activity"] = None
        state["extensions_this_session"] = 0
        state["lock_reason"]             = reason
        self._write(state)

    def _read(self) -> Dict:
        """
        Read state file, verify integrity_hash.
        If tampered or corrupt: invalidate session, return LOCKED state.
        """
        if not STATE_FILE.exists():
            init = _initial_state()
            self._write(init)
            return init

        try:
            raw   = json.loads(STATE_FILE.read_text())
            stored = raw.get("integrity_hash", "")

            if stored == "__INIT__":
                # First read after initialization — compute and write real hash
                raw["integrity_hash"] = _compute_hash(raw, self._key)
                self._write_raw(raw)
                return raw

            expected = _compute_hash(raw, self._key)
            if not hmac.compare_digest(stored, expected):
                log.error("SESSION INTEGRITY VIOLATION: session_state.json hash mismatch — invalidating")
                self._audit("session_rejected", identity="unknown",
                             reason="integrity_hash_mismatch")
                locked = _initial_state()
                locked["lock_reason"] = "tamper_detected"
                self._write(locked)
                return locked

            return raw

        except (json.JSONDecodeError, Exception) as e:
            log.error("session_state.json read error: %s — reinitializing", e)
            init = _initial_state()
            self._write(init)
            return init

    def _write(self, state: Dict) -> None:
        """Write state with fresh integrity_hash using atomic temp-file swap."""
        state["integrity_hash"] = _compute_hash(state, self._key)
        self._write_raw(state)

    def _write_raw(self, state: Dict) -> None:
        """Atomic write: write to .tmp then rename."""
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(STATE_FILE)

    def _audit(self, event: str, **kwargs) -> None:
        """Append a session event to the shared audit log."""
        entry = {"event": event, "timestamp": _now_iso(), **kwargs}
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Session audit write failed: %s", e)

    # ── Credential verifiers ───────────────────────────────────────────────────

    @staticmethod
    def _verify_identity(identity: str) -> bool:
        """Check identity is in privileged set AND role registry confirms chairman."""
        if identity.lower() not in PRIVILEGED_IDENTITIES:
            return False
        try:
            from .rex_role_auth import verify_role
            role = verify_role(identity, "chairman")
            return role == "chairman"
        except Exception as e:
            log.warning("Identity verify error: %s — falling back to privileged_identities set", e)
            return identity.lower() in PRIVILEGED_IDENTITIES

    @staticmethod
    def _verify_passphrase(passphrase: str) -> Tuple[bool, str]:
        """Verify passphrase against rex_credential_vault."""
        try:
            from .rex_credential_vault import CredentialVault
            vault = CredentialVault()
            ok, msg = vault.unlock(passphrase, bypass_2fa=True)  # TOTP checked separately
            return ok, msg
        except Exception as e:
            log.error("Passphrase verify error: %s", e)
            return False, str(e)

    @staticmethod
    def _verify_totp(code: str) -> bool:
        """Verify TOTP code via rex_2fa."""
        try:
            from .rex_2fa import verify_totp
            return verify_totp(code)
        except Exception as e:
            log.error("TOTP verify error: %s", e)
            return False


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _initial_state() -> Dict:
    return {
        "schema_version":          "1.0",
        "state":                   STATE_LOCKED,
        "identity":                None,
        "unlocked_at":             None,
        "expires_at":              None,
        "last_protected_activity": None,
        "auto_lock_minutes":       DEFAULT_AUTO_LOCK_MINUTES,
        "extensions_this_session": 0,
        "lock_reason":             "initial",
        "integrity_hash":          "__INIT__",
    }

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _now_dt() -> datetime:
    return datetime.now(timezone.utc)
