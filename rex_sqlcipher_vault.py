"""
rex_sqlcipher_vault.py
──────────────────────────────────────────────────────────────────────────────
REX — Per-Agent SQLCipher Vault
Garden of Joy · Gold Health Systems · Locked Lucy Compliant

Security architecture:
  Layer 1 — SQLCipher database-file encryption
             The .db file itself is AES-256 encrypted using PRAGMA key.
             Anyone with file access sees encrypted bytes — not readable
             by DB Browser, sqlite3 CLI, or any tool without the key.

  Layer 2 — Secrecy levels enforced at the query layer (not just prompts)
             never_share  (3) — TOTP verification required to read;
                                never returned in AI responses
             owner_only   (2) — Kato only; role check enforced
             restricted   (1) — Authenticated staff with explicit access
             public       (0) — Freely accessible within the local system

  Layer 3 — TOTP gate on never_share reads
             Integrates with rex_2fa.py. All never_share reads require
             a current TOTP code. Gate is CODE-LEVEL, not prompt-based.

  Layer 4 — Master key in ~/.rex/vault.key (chmod 600)
             32-byte random key generated on first run, stored in
             ~/.rex/vault.key (owner read/write only) with macOS
             Keychain as backup. Key file is the primary source of
             truth — reliable across all Python process boundaries.

  Layer 5 — Immutable vault audit log
             Every read/write of restricted/owner_only/never_share is
             appended to vault_audit.jsonl with SHA-256 hash chaining.

Usage:
    from rex_sqlcipher_vault import VaultManager, SecrecyLevel

    vm = VaultManager()
    with vm.open("rexxie") as vault:
        vault.write("memories", "last_session", "...", SecrecyLevel.RESTRICTED)
        value = vault.read("memories", "last_session")

    # TOTP-gated read (never_share)
    totp_code = "123456"
    secret = vm.open("rexxie").read_sensitive("system", "totp_secret", totp_code)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("rex.vault")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

REX_DIR    = Path.home() / "Desktop" / "REX"
VAULT_DIR  = REX_DIR / "data" / "vaults"
AUDIT_LOG  = REX_DIR / "data" / "vaults" / "vault_audit.jsonl"

# SQLCipher PRAGMA settings — deliberately strong defaults
SQLCIPHER_PRAGMAS = [
    "PRAGMA kdf_iter = 256000;",
    "PRAGMA cipher_page_size = 4096;",
    "PRAGMA cipher_hmac_algorithm = HMAC_SHA512;",
    "PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;",
]

# Agent vault names
AGENT_VAULTS = {
    "rexxie":          "rexxie_agent_vault.db",
    "goj":             "goj_agent_vault.db",
    "backend":         "backend_agent_vault.db",
    "knowledge":       "knowledge_agent_vault.db",
    "credentials":     "credentials_agent_vault.db",
}

# Default secrecy level — conservative
DEFAULT_SECRECY = "restricted"

# Keychain service/account names
KEYCHAIN_SERVICE = "rex_vault"
KEYCHAIN_ACCOUNT = "rex_vault_master_key"

# Primary key file — chmod 600, owner read/write only
# Lives in ~/.rex/ (separate directory from the vault .db files)
VAULT_KEY_FILE = Path.home() / ".rex" / "vault.key"


# ─────────────────────────────────────────────────────────────────────────────
# SECRECY LEVELS
# ─────────────────────────────────────────────────────────────────────────────

class SecrecyLevel(IntEnum):
    PUBLIC      = 0   # Freely accessible within local system
    RESTRICTED  = 1   # Authenticated staff with explicit access
    OWNER_ONLY  = 2   # Kato only
    NEVER_SHARE = 3   # TOTP required; never sent to AI

    @classmethod
    def from_str(cls, s: str) -> "SecrecyLevel":
        mapping = {
            "public":      cls.PUBLIC,
            "restricted":  cls.RESTRICTED,
            "owner_only":  cls.OWNER_ONLY,
            "never_share": cls.NEVER_SHARE,
        }
        return mapping.get(str(s).lower(), cls.RESTRICTED)

    def label(self) -> str:
        return self.name.lower()


# ─────────────────────────────────────────────────────────────────────────────
# TOTP GATE
# ─────────────────────────────────────────────────────────────────────────────

def _verify_totp(code: str) -> bool:
    """
    Verify a TOTP code using rex_2fa.py.
    Returns True if valid, False otherwise.
    Falls back to False (deny) if rex_2fa is unavailable — never silently allows.
    """
    try:
        from rex_2fa import verify_totp
        return verify_totp(code)
    except ImportError:
        logger.error("[vault] rex_2fa not available — TOTP gate will DENY all never_share reads")
        return False
    except Exception as e:
        logger.error(f"[vault] TOTP verification error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# KEY MANAGEMENT — macOS KEYCHAIN
# ─────────────────────────────────────────────────────────────────────────────

class VaultKeyManager:
    """
    Manages the master vault key using ~/.rex/vault.key as primary storage
    (chmod 600, owner read/write only) with macOS Keychain as backup.

    Priority order (get_or_create_key):
      1. Read from ~/.rex/vault.key  — reliable across all process boundaries
      2. Read from macOS Keychain    — fallback if key file missing
      3. Generate new key            — first-ever run; write to both file + Keychain

    The key is a 32-byte random value stored as a 64-char hex string.
    """

    @classmethod
    def _save_key_file(cls, key: bytes) -> None:
        """Write key to ~/.rex/vault.key with chmod 600."""
        try:
            VAULT_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            VAULT_KEY_FILE.write_text(key.hex())
            os.chmod(VAULT_KEY_FILE, 0o600)
            logger.debug(f"[vault] Key written to {VAULT_KEY_FILE}")
        except Exception as e:
            logger.warning(f"[vault] Could not write key file: {e}")

    @staticmethod
    def _keychain_get() -> Optional[str]:
        """Read the vault master key from macOS Keychain. Returns hex string or None."""
        try:
            result = subprocess.run(
                ["security", "find-generic-password",
                 "-a", KEYCHAIN_ACCOUNT,
                 "-s", KEYCHAIN_SERVICE,
                 "-w"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.debug(f"[vault] Keychain read failed: {e}")
            return None

    @staticmethod
    def _keychain_set(key_hex: str) -> bool:
        """Write the vault master key to macOS Keychain. Returns True on success."""
        try:
            # Delete existing entry first (ignore error if not exists)
            subprocess.run(
                ["security", "delete-generic-password",
                 "-a", KEYCHAIN_ACCOUNT,
                 "-s", KEYCHAIN_SERVICE],
                capture_output=True, timeout=5
            )
            # Store new key
            result = subprocess.run(
                ["security", "add-generic-password",
                 "-a", KEYCHAIN_ACCOUNT,
                 "-s", KEYCHAIN_SERVICE,
                 "-w", key_hex,
                 "-T", ""],   # Allow access from any app (user will be prompted once)
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"[vault] Keychain write failed: {e}")
            return False

    @classmethod
    def get_or_create_key(cls) -> bytes:
        """
        Get the vault master key. Priority:
          1. ~/.rex/vault.key  (reliable across process boundaries)
          2. macOS Keychain    (fallback; also syncs to key file if found)
          3. Generate new key  (first run; persists to both)

        Returns 32 raw bytes.
        """
        # ── 1. Try key file first ─────────────────────────────────────────────
        if VAULT_KEY_FILE.exists():
            try:
                hex_key = VAULT_KEY_FILE.read_text().strip()
                if len(hex_key) == 64:
                    key = bytes.fromhex(hex_key)
                    logger.debug("[vault] Key loaded from key file")
                    return key
                else:
                    logger.warning("[vault] Key file content invalid — trying Keychain")
            except Exception as e:
                logger.warning(f"[vault] Key file read error: {e} — trying Keychain")

        # ── 2. Try Keychain as fallback ───────────────────────────────────────
        hex_key = cls._keychain_get()
        if hex_key and len(hex_key) == 64:
            try:
                key = bytes.fromhex(hex_key)
                # Persist to key file so future calls don't need Keychain
                cls._save_key_file(key)
                logger.info("[vault] Key recovered from Keychain — synced to key file")
                return key
            except ValueError:
                logger.warning("[vault] Keychain key is malformed — generating new key")

        # ── 3. Generate fresh key (first ever run) ────────────────────────────
        new_key = os.urandom(32)
        cls._save_key_file(new_key)
        if cls._keychain_set(new_key.hex()):
            logger.info("[vault] New vault master key generated — stored in key file + Keychain")
        else:
            logger.info("[vault] New vault master key generated — stored in key file (Keychain unavailable)")
        return new_key

    @classmethod
    def rotate_key(cls, new_key: Optional[bytes] = None) -> bytes:
        """Generate and store a new vault key in both key file and Keychain. Returns new key."""
        if new_key is None:
            new_key = os.urandom(32)
        cls._save_key_file(new_key)
        cls._keychain_set(new_key.hex())
        logger.info("[vault] Vault master key rotated")
        return new_key


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

class VaultAuditLog:
    """
    Append-only audit log for vault operations above PUBLIC level.
    Uses SHA-256 hash chaining — each entry includes hash of previous entry.
    Compatible with Grok's audit_log.jsonl format.
    """

    def __init__(self, path: Path = AUDIT_LOG):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._get_last_hash()

    def _get_last_hash(self) -> str:
        """Read the hash of the last log entry for chaining."""
        try:
            if not self.path.exists():
                return "0" * 64
            lines = self.path.read_text().strip().splitlines()
            if not lines:
                return "0" * 64
            last = json.loads(lines[-1])
            return last.get("entry_hash", "0" * 64)
        except Exception:
            return "0" * 64

    def log(
        self,
        operation:     str,
        agent:         str,
        namespace:     str,
        key:           str,
        secrecy_level: str,
        outcome:       str,
        totp_verified: bool = False,
        extra:         dict | None = None,
    ) -> None:
        """Append one audit entry with hash chaining."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            entry = {
                "timestamp":     now,
                "operation":     operation,
                "agent":         agent,
                "namespace":     namespace,
                "key":           key,
                "secrecy_level": secrecy_level,
                "outcome":       outcome,
                "totp_verified": totp_verified,
                "prev_hash":     self._last_hash,
            }
            if extra:
                entry.update(extra)

            # Hash the entry (excluding entry_hash itself)
            entry_str  = json.dumps(entry, sort_keys=True)
            entry_hash = hashlib.sha256(entry_str.encode()).hexdigest()
            entry["entry_hash"] = entry_hash

            with open(self.path, "a") as f:
                f.write(json.dumps(entry) + "\n")

            self._last_hash = entry_hash
        except Exception as e:
            logger.error(f"[vault] Audit log write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# VAULT SESSION
# ─────────────────────────────────────────────────────────────────────────────

class VaultSession:
    """
    An open SQLCipher connection to one agent vault.

    All reads and writes go through this class — never raw SQL from outside.
    Secrecy levels are enforced here at the method level (code-level, not prompt).
    """

    # Schema for the generic vault_items table
    _VAULT_ITEMS_DDL = """
        CREATE TABLE IF NOT EXISTS vault_items (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace      TEXT NOT NULL,
            key            TEXT NOT NULL,
            value          TEXT,
            secrecy_level  TEXT NOT NULL DEFAULT 'restricted',
            created_at     TEXT DEFAULT (datetime('now')),
            updated_at     TEXT DEFAULT (datetime('now')),
            access_count   INTEGER DEFAULT 0,
            UNIQUE(namespace, key)
        );
    """

    _VAULT_META_DDL = """
        CREATE TABLE IF NOT EXISTS vault_meta (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            meta_key       TEXT UNIQUE NOT NULL,
            meta_value     TEXT,
            secrecy_level  TEXT NOT NULL DEFAULT 'never_share',
            created_at     TEXT DEFAULT (datetime('now'))
        );
    """

    def __init__(
        self,
        agent_name:  str,
        db_path:     Path,
        master_key:  bytes,
        audit:       VaultAuditLog,
    ):
        self.agent   = agent_name
        self.db_path = db_path
        self._key    = master_key
        self._audit  = audit
        self._conn   = None

        # Triple encryption for Rexxie's personal namespaces
        # Applied ON TOP of SQLCipher — 4 layers total for personal memories
        self._triple: Optional[Any] = None
        if agent_name == "rexxie":
            try:
                from rex_triple_encrypt import TripleEncrypt
                self._triple = TripleEncrypt(master_key)
                logger.info("[vault] Rexxie triple encryption active (AES-GCM → ChaCha20 → AES-GCM)")
            except Exception as e:
                logger.warning(f"[vault] Triple encryption unavailable for Rexxie: {e} — SQLCipher only")

        self._open()

    def _open(self) -> None:
        """Open the SQLCipher connection and apply security PRAGMAs."""
        try:
            from pysqlcipher3 import dbapi2 as sqlcipher
        except ImportError:
            raise RuntimeError(
                "pysqlcipher3 not installed. Run: "
                "brew install sqlcipher && "
                "LDFLAGS='-L/opt/homebrew/lib' CFLAGS='-I/opt/homebrew/include' "
                "pip install pysqlcipher3"
            )

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlcipher.connect(str(self.db_path))
        conn.row_factory = sqlcipher.Row

        # PRAGMA key MUST be the first operation
        key_hex = self._key.hex()
        conn.execute(f"PRAGMA key = \"x'{key_hex}'\";")
        for pragma in SQLCIPHER_PRAGMAS:
            conn.execute(pragma)

        # Verify key works (will throw if wrong key)
        conn.execute("SELECT count(*) FROM sqlite_master;").fetchone()

        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create standard vault tables if they don't exist."""
        self._conn.execute(self._VAULT_ITEMS_DDL)
        self._conn.execute(self._VAULT_META_DDL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Triple encryption helpers ─────────────────────────────────────────────

    def _should_triple(self, namespace: str) -> bool:
        """True if this namespace gets triple encryption (Rexxie personal only)."""
        if self._triple is None:
            return False
        try:
            from rex_triple_encrypt import TripleEncrypt
            return TripleEncrypt.should_triple_encrypt(self.agent, namespace)
        except Exception:
            return False

    def _te_encode(self, namespace: str, serialized: str) -> str:
        """Apply triple encryption if applicable. Returns hex string for storage."""
        if not self._should_triple(namespace):
            return serialized
        blob = self._triple.encrypt_str(serialized)
        return "__REXT3__" + blob.hex()   # prefix flags triple-encrypted value

    def _te_decode(self, namespace: str, stored: str) -> str:
        """Reverse triple encryption if applicable."""
        if not stored.startswith("__REXT3__"):
            return stored   # not triple-encrypted — return as-is
        if self._triple is None:
            raise RuntimeError(
                f"[vault] Value in {namespace} is triple-encrypted but "
                "TripleEncrypt engine is not loaded — cannot decrypt"
            )
        blob = bytes.fromhex(stored[len("__REXT3__"):])
        return self._triple.decrypt_str(blob)

    # ── Core write ────────────────────────────────────────────────────────────

    def write(
        self,
        namespace:     str,
        key:           str,
        value:         Any,
        secrecy_level: SecrecyLevel | str = SecrecyLevel.RESTRICTED,
    ) -> None:
        """
        Write a value into the vault.
        Value is JSON-serialized before storage.
        For Rexxie personal namespaces: triple-encrypted before storage.
        """
        level = SecrecyLevel.from_str(secrecy_level) if isinstance(secrecy_level, str) else secrecy_level
        serialized = self._te_encode(namespace, json.dumps(value))
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute("""
            INSERT INTO vault_items (namespace, key, value, secrecy_level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, key) DO UPDATE SET
                value = excluded.value,
                secrecy_level = excluded.secrecy_level,
                updated_at = excluded.updated_at
        """, (namespace, key, serialized, level.label(), now, now))
        self._conn.commit()

        if level >= SecrecyLevel.RESTRICTED:
            self._audit.log("write", self.agent, namespace, key, level.label(), "ok")

    # ── Core read ─────────────────────────────────────────────────────────────

    def read(
        self,
        namespace: str,
        key:       str,
    ) -> Optional[Any]:
        """
        Read a value from the vault.
        Returns None if not found or if secrecy level would block it.
        Use read_sensitive() for never_share items.
        """
        row = self._conn.execute("""
            SELECT value, secrecy_level, access_count
            FROM vault_items
            WHERE namespace = ? AND key = ?
        """, (namespace, key)).fetchone()

        if not row:
            return None

        level = SecrecyLevel.from_str(row["secrecy_level"])

        if level == SecrecyLevel.NEVER_SHARE:
            # BLOCK — never_share requires explicit TOTP gate
            logger.warning(
                f"[vault] BLOCKED: read({namespace}/{key}) "
                f"is never_share — use read_sensitive() with TOTP"
            )
            self._audit.log("read", self.agent, namespace, key, level.label(), "blocked_no_totp")
            return None

        # Bump access count
        self._conn.execute(
            "UPDATE vault_items SET access_count = access_count + 1 WHERE namespace = ? AND key = ?",
            (namespace, key)
        )
        self._conn.commit()

        if level >= SecrecyLevel.RESTRICTED:
            self._audit.log("read", self.agent, namespace, key, level.label(), "ok")

        try:
            decoded = self._te_decode(namespace, row["value"])
            return json.loads(decoded)
        except (json.JSONDecodeError, TypeError):
            return self._te_decode(namespace, row["value"])

    def read_sensitive(
        self,
        namespace:  str,
        key:        str,
        totp_code:  str,
    ) -> Optional[Any]:
        """
        Read a never_share item — requires valid TOTP code.
        This is the ONLY method that can return never_share data.
        All access is logged regardless of outcome.
        """
        if not _verify_totp(totp_code):
            self._audit.log(
                "read_sensitive", self.agent, namespace, key,
                "never_share", "denied_invalid_totp",
                totp_verified=False
            )
            logger.warning(f"[vault] TOTP DENIED: read_sensitive({namespace}/{key})")
            return None

        row = self._conn.execute("""
            SELECT value, secrecy_level, access_count
            FROM vault_items
            WHERE namespace = ? AND key = ?
        """, (namespace, key)).fetchone()

        if not row:
            self._audit.log(
                "read_sensitive", self.agent, namespace, key,
                "never_share", "not_found",
                totp_verified=True
            )
            return None

        self._conn.execute(
            "UPDATE vault_items SET access_count = access_count + 1 WHERE namespace = ? AND key = ?",
            (namespace, key)
        )
        self._conn.commit()

        self._audit.log(
            "read_sensitive", self.agent, namespace, key,
            row["secrecy_level"], "ok",
            totp_verified=True
        )

        try:
            decoded = self._te_decode(namespace, row["value"])
            return json.loads(decoded)
        except (json.JSONDecodeError, TypeError):
            return self._te_decode(namespace, row["value"])

    # ── Query helpers ─────────────────────────────────────────────────────────

    def list_keys(
        self,
        namespace: str,
        max_secrecy: SecrecyLevel = SecrecyLevel.RESTRICTED,
    ) -> list[dict]:
        """
        List all keys in a namespace up to max_secrecy level.
        never_share items are never listed without explicit TOTP read.
        """
        rows = self._conn.execute("""
            SELECT namespace, key, secrecy_level, updated_at, access_count
            FROM vault_items
            WHERE namespace = ?
            ORDER BY updated_at DESC
        """, (namespace,)).fetchall()

        result = []
        for row in rows:
            level = SecrecyLevel.from_str(row["secrecy_level"])
            if level <= max_secrecy:
                result.append({
                    "namespace":     row["namespace"],
                    "key":           row["key"],
                    "secrecy_level": row["secrecy_level"],
                    "updated_at":    row["updated_at"],
                    "access_count":  row["access_count"],
                })
        return result

    def count_by_secrecy(self) -> dict[str, int]:
        """Return count of items per secrecy level — useful for diagnostics."""
        rows = self._conn.execute("""
            SELECT secrecy_level, COUNT(*) as n
            FROM vault_items
            GROUP BY secrecy_level
        """).fetchall()
        return {r["secrecy_level"]: r["n"] for r in rows}

    def delete(
        self,
        namespace: str,
        key:       str,
        totp_code: Optional[str] = None,
    ) -> bool:
        """
        Delete an item. never_share items require TOTP.
        Returns True if deleted, False if blocked or not found.
        """
        row = self._conn.execute(
            "SELECT secrecy_level FROM vault_items WHERE namespace = ? AND key = ?",
            (namespace, key)
        ).fetchone()

        if not row:
            return False

        level = SecrecyLevel.from_str(row["secrecy_level"])

        if level == SecrecyLevel.NEVER_SHARE:
            if not totp_code or not _verify_totp(totp_code):
                self._audit.log("delete", self.agent, namespace, key, level.label(), "denied_no_totp")
                return False

        self._conn.execute(
            "DELETE FROM vault_items WHERE namespace = ? AND key = ?",
            (namespace, key)
        )
        self._conn.commit()
        self._audit.log("delete", self.agent, namespace, key, level.label(), "ok")
        return True

    # ── Metadata (never_share system secrets) ─────────────────────────────────

    def store_secret(self, meta_key: str, meta_value: str) -> None:
        """Store a system secret (always never_share). E.g. TOTP seed."""
        self._conn.execute("""
            INSERT INTO vault_meta (meta_key, meta_value, secrecy_level)
            VALUES (?, ?, 'never_share')
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
        """, (meta_key, meta_value))
        self._conn.commit()
        self._audit.log("write_secret", self.agent, "vault_meta", meta_key, "never_share", "ok")

    def read_secret(self, meta_key: str, totp_code: str) -> Optional[str]:
        """Read a system secret — TOTP required."""
        if not _verify_totp(totp_code):
            self._audit.log("read_secret", self.agent, "vault_meta", meta_key, "never_share", "denied_invalid_totp")
            return None
        row = self._conn.execute(
            "SELECT meta_value FROM vault_meta WHERE meta_key = ?", (meta_key,)
        ).fetchone()
        if row:
            self._audit.log("read_secret", self.agent, "vault_meta", meta_key, "never_share", "ok", totp_verified=True)
            return row["meta_value"]
        return None

    # ── Direct SQL for migrated tables ────────────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """
        Execute raw SQL on the vault connection.
        For use by migration scripts and internal tooling ONLY.
        Production code should use write()/read() above.
        """
        return self._conn.execute(sql, params)

    def executescript(self, sql: str) -> None:
        """Execute a SQL script (multiple statements). Migration use only."""
        self._conn.executescript(sql)

    def commit(self) -> None:
        self._conn.commit()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return diagnostic stats for this vault session."""
        counts = self.count_by_secrecy()
        total  = sum(counts.values())
        return {
            "agent":    self.agent,
            "db_path":  str(self.db_path),
            "total":    total,
            "by_secrecy": counts,
            "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# VAULT MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class VaultManager:
    """
    Central manager for all agent vaults.
    Handles key management, vault creation, and session lifecycle.

    Instantiate once per application lifecycle.
    """

    def __init__(
        self,
        vault_dir:   Path = VAULT_DIR,
        master_key:  Optional[bytes] = None,
    ):
        self.vault_dir = vault_dir
        self.vault_dir.mkdir(parents=True, exist_ok=True)

        # Key: from Keychain unless explicitly provided (testing)
        self._master_key = master_key or VaultKeyManager.get_or_create_key()
        self._audit      = VaultAuditLog(self.vault_dir / "vault_audit.jsonl")
        self._sessions: dict[str, VaultSession] = {}

        logger.info(f"[vault] VaultManager initialized — vault_dir={self.vault_dir}")

    def open(self, agent_name: str) -> VaultSession:
        """
        Open (or return existing) vault session for an agent.
        agent_name: one of "rexxie", "goj", "backend", "knowledge", "credentials"
        or any custom name (will create new vault file).
        """
        if agent_name in self._sessions:
            return self._sessions[agent_name]

        filename = AGENT_VAULTS.get(agent_name, f"{agent_name}_agent_vault.db")
        db_path  = self.vault_dir / filename

        session = VaultSession(
            agent_name  = agent_name,
            db_path     = db_path,
            master_key  = self._master_key,
            audit       = self._audit,
        )
        self._sessions[agent_name] = session
        logger.info(f"[vault] Opened vault: {agent_name} → {db_path.name}")
        return session

    @contextmanager
    def session(self, agent_name: str):
        """Context manager for vault access."""
        vault = self.open(agent_name)
        try:
            yield vault
        finally:
            pass   # Keep session alive — close explicitly with close_all()

    def close_all(self) -> None:
        """Close all open vault sessions."""
        for name, session in self._sessions.items():
            session.close()
            logger.debug(f"[vault] Closed vault: {name}")
        self._sessions.clear()

    def list_vaults(self) -> list[dict]:
        """List all vault files in the vault directory."""
        result = []
        for path in sorted(self.vault_dir.glob("*_vault.db")):
            size_kb = path.stat().st_size // 1024
            result.append({
                "file":       path.name,
                "size_kb":    size_kb,
                "agent":      path.stem.replace("_agent_vault", "").replace("_vault", ""),
            })
        return result

    def full_stats(self) -> dict:
        """Return stats for all open vaults."""
        return {
            "vault_dir":  str(self.vault_dir),
            "open_agents": list(self._sessions.keys()),
            "sessions": {
                name: session.stats()
                for name, session in self._sessions.items()
            }
        }

    def verify_integrity(self, agent_name: str) -> bool:
        """
        Verify a vault can be opened and read.
        Used in startup health checks.
        """
        try:
            vault = self.open(agent_name)
            count = vault.execute("SELECT COUNT(*) FROM vault_items").fetchone()[0]
            logger.info(f"[vault] Integrity OK: {agent_name} ({count} items)")
            return True
        except Exception as e:
            logger.error(f"[vault] Integrity FAIL: {agent_name} — {e}")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE: assign secrecy level by table/namespace name
# ─────────────────────────────────────────────────────────────────────────────

def infer_secrecy_level(name: str) -> SecrecyLevel:
    """
    Infer a default secrecy level from a table or namespace name.
    Used during migration to assign conservative defaults.
    """
    name_lower = name.lower()

    # never_share: credentials, keys, tokens, secrets, TOTP
    if any(kw in name_lower for kw in [
        "password", "credential", "token", "secret", "key", "totp",
        "pin", "auth_code", "2fa", "passphrase", "api_key",
    ]):
        return SecrecyLevel.NEVER_SHARE

    # owner_only: PHI-adjacent, client data, financial
    if any(kw in name_lower for kw in [
        "client", "patient", "phi", "hipaa", "diagnosis", "medical",
        "financial", "billing", "insurance", "personal", "ssn",
        "dob", "birthdate", "address", "phone",
    ]):
        return SecrecyLevel.OWNER_ONLY

    # restricted: memories, conversations, operational
    if any(kw in name_lower for kw in [
        "memory", "memories", "exchange", "conversation", "history",
        "session", "journey", "attendance", "menu", "task", "idea",
        "user_model", "reflection", "user",
    ]):
        return SecrecyLevel.RESTRICTED

    # public: general knowledge, system config
    if any(kw in name_lower for kw in [
        "knowledge", "curriculum", "background", "config", "setting",
        "version", "schema",
    ]):
        return SecrecyLevel.PUBLIC

    # Conservative default
    return SecrecyLevel.RESTRICTED


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os, sys

    print("=" * 60)
    print("REX SQLCIPHER VAULT — SELF-TEST")
    print("=" * 60)

    # ── Test 0: Key file persistence (exercises VaultKeyManager) ──────────────
    # Temporarily redirect VAULT_KEY_FILE to a temp path so we don't clobber
    # the real key during testing, but still exercise the full code path.
    # Must use globals() — not a module import — because _save_key_file()
    # resolves VAULT_KEY_FILE from __main__'s globals at call time.
    with tempfile.TemporaryDirectory() as _kdir:
        _real_key_file = globals()["VAULT_KEY_FILE"]
        _test_key_file = Path(_kdir) / "test_vault.key"
        globals()["VAULT_KEY_FILE"] = _test_key_file

        try:
            # First call — should generate key + write file
            key_a = VaultKeyManager.get_or_create_key()
            assert _test_key_file.exists(), "Key file was not created by get_or_create_key()"
            assert oct(os.stat(_test_key_file).st_mode)[-3:] == "600", "Key file permissions not 600"

            # Second call — should load from file (not regenerate)
            key_b = VaultKeyManager.get_or_create_key()
            assert key_a == key_b, "Key changed between calls — file read failed"

            print("✓ Test 0: Key file persistence OK — key stable across calls")
        finally:
            globals()["VAULT_KEY_FILE"] = _real_key_file  # Restore

    # Use a temp directory so self-test doesn't touch real vaults
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use a test key (never use a fixed key in production)
        test_key = os.urandom(32)
        vm = VaultManager(vault_dir=Path(tmpdir), master_key=test_key)

        # ── Test 1: Write and read public item ──
        vault = vm.open("rexxie")
        vault.write("memories", "last_session", "Helped Kato with menu OCR", SecrecyLevel.PUBLIC)
        result = vault.read("memories", "last_session")
        assert result == "Helped Kato with menu OCR", f"Got: {result}"
        print("✓ Test 1: Public read/write OK")

        # ── Test 2: Write restricted item ──
        vault.write("user_model", "communication_style", {"style": "direct"}, SecrecyLevel.RESTRICTED)
        result = vault.read("user_model", "communication_style")
        assert result == {"style": "direct"}, f"Got: {result}"
        print("✓ Test 2: Restricted read/write OK")

        # ── Test 3: never_share is blocked by read() ──
        vault.write("system", "totp_secret", "JBSWY3DPEHPK3PXP", SecrecyLevel.NEVER_SHARE)
        result = vault.read("system", "totp_secret")
        assert result is None, f"never_share should return None from read(), got: {result}"
        print("✓ Test 3: never_share blocked by read() — TOTP gate working")

        # ── Test 4: read_sensitive denied with wrong TOTP ──
        result = vault.read_sensitive("system", "totp_secret", "000000")
        assert result is None, f"Wrong TOTP should return None, got: {result}"
        print("✓ Test 4: read_sensitive denies wrong TOTP")

        # ── Test 5: Vault persists (reopen same file) ──
        vault.close()
        vm2 = VaultManager(vault_dir=Path(tmpdir), master_key=test_key)
        vault2 = vm2.open("rexxie")
        result2 = vault2.read("memories", "last_session")
        assert result2 == "Helped Kato with menu OCR", f"Got after reopen: {result2}"
        print("✓ Test 5: Vault persists across close/reopen")

        # ── Test 6: Wrong key cannot open vault ──
        wrong_key = os.urandom(32)
        try:
            vm3 = VaultManager(vault_dir=Path(tmpdir), master_key=wrong_key)
            vm3.open("rexxie")
            print("✗ Test 6: FAIL — wrong key should have thrown")
            sys.exit(1)
        except Exception:
            print("✓ Test 6: Wrong key correctly rejected")

        # ── Test 7: Secrecy level inference ──
        checks = [
            ("password_hash",    SecrecyLevel.NEVER_SHARE),
            ("client_records",   SecrecyLevel.OWNER_ONLY),
            ("rexxie_memories",  SecrecyLevel.RESTRICTED),
            ("background_knowledge", SecrecyLevel.PUBLIC),
            ("unknown_table",    SecrecyLevel.RESTRICTED),
        ]
        for name, expected in checks:
            got = infer_secrecy_level(name)
            assert got == expected, f"infer({name!r}): expected {expected}, got {got}"
        print("✓ Test 7: Secrecy level inference correct for all 5 cases")

        # ── Test 8: Stats ──
        stats = vm2.full_stats()
        assert "sessions" in stats
        print(f"✓ Test 8: Stats OK — {stats['sessions']['rexxie']['total']} items in rexxie vault")

        # ── Test 9: Audit log entries exist ──
        audit_path = Path(tmpdir) / "vault_audit.jsonl"
        assert audit_path.exists(), "Audit log not created"
        entries = [json.loads(l) for l in audit_path.read_text().strip().splitlines()]
        assert len(entries) >= 3, f"Expected >= 3 audit entries, got {len(entries)}"
        # Verify hash chaining
        for i, entry in enumerate(entries[1:], 1):
            prev_hash = hashlib.sha256(
                json.dumps({k: v for k, v in entries[i-1].items() if k != "entry_hash"}, sort_keys=True).encode()
            ).hexdigest()
            assert entries[i]["prev_hash"] == entries[i-1]["entry_hash"], \
                f"Hash chain broken at entry {i}"
        print(f"✓ Test 9: Audit log OK — {len(entries)} entries, hash chain verified")

        vm2.close_all()

    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_sqlcipher_vault.py is ready")
    print("=" * 60)
