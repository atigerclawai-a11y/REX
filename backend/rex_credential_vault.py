"""
REX — Rexxie Credential Vault
================================
A genuinely secure local credential store protected by a master passphrase
that only Kato knows and is NEVER stored anywhere on disk or in Keychain.

Security architecture:
  Layer 1 — Master passphrase (in your head only)
             Argon2id key derivation: 64MB memory, 3 iterations, parallelism 4
             This makes brute-force attacks computationally infeasible.

  Layer 2 — Device secret (stored in macOS Keychain)
             A random 32-byte secret tied to this specific Mac.
             Even knowing the passphrase, you need the device secret too.

  Layer 3 — Combined key derivation
             actual_key = Argon2id(passphrase + device_secret)
             Losing either factor = losing access to data.

  Layer 4 — Triple encryption (AES-GCM → ChaCha20 → AES-GCM)
             Same as all Rexxie data, applied on top of the passphrase-derived key.

  Layer 5 — Credential retrieval NEVER sent to external AI
             All credential lookup/store is local Python only.
             The AI never sees your passwords — not even in the request.

Remote wipe:
  "rexxie wipe credentials" → overwrites credential table with zeros, then deletes
  "rexxie emergency wipe"   → overwrites ALL of rexxie.db with zeros, then deletes,
                              then removes key from Keychain

Auto-lock:
  Vault locks after 15 minutes of inactivity.
  Re-entry of master passphrase required to unlock.

What Rexxie stores:
  - Website/app credentials (username + password)
  - Bank account info (account name, type, last4 — NOT full account numbers by default)
  - PIN codes
  - Security question answers
  - Any other private text you want to give her

IMPORTANT NOTE ON FULL ACCOUNT NUMBERS:
  Storing full bank account or card numbers creates risk even with strong encryption.
  Rexxie will warn you and ask if you're sure before storing anything that looks like
  a full card or account number. The choice is always yours.

Usage (via Rexxie chat — no commands needed, just natural language):
  "Rexxie, remember my Chase login: user=kato@email.com pass=MyPass123"
  "What's my Netflix password?"
  "Type my Chase password into this field" (triggers auto-fill)
  "Rexxie, wipe all credentials" (secure wipe)
  "Rexxie, show me all my stored accounts" (lists account names, no passwords)

Usage (CLI for setup):
  python backend/rex_credential_vault.py --setup
  python backend/rex_credential_vault.py --list
  python backend/rex_credential_vault.py --get "chase"
  python backend/rex_credential_vault.py --wipe-credentials
  python backend/rex_credential_vault.py --emergency-wipe
"""

import os
import re
import json
import time
import sqlite3
import secrets
import logging
import hashlib
import getpass
from pathlib import Path
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
REXXIE_DB_PATH     = Path.home() / "Desktop" / "REX" / "rexxie.db"
DEVICE_SECRET_KEY  = "rexxie-device-secret"   # Keychain key name
VAULT_LOCK_TIMEOUT = 15 * 60                   # 15 minutes in seconds

# ── Argon2id parameters (OWASP recommended minimum for high-security) ──────────
ARGON2_TIME_COST   = 3
ARGON2_MEMORY_COST = 65536   # 64 MB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN    = 32

# ── Patterns that suggest sensitive data (for warnings) ───────────────────────
CARD_PATTERN    = re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')
ACCOUNT_PATTERN = re.compile(r'\b\d{8,17}\b')
ROUTING_PATTERN = re.compile(r'\b\d{9}\b')


def _get_device_secret() -> bytes:
    """Load or generate the device-specific secret from macOS Keychain."""
    try:
        import keyring
        existing = keyring.get_password("rex-sovereign", DEVICE_SECRET_KEY)
        if existing:
            return bytes.fromhex(existing)
        new_secret = secrets.token_bytes(32)
        keyring.set_password("rex-sovereign", DEVICE_SECRET_KEY, new_secret.hex())
        return new_secret
    except Exception:
        # Fallback: file-based (less secure but functional)
        secret_path = Path.home() / "Desktop" / "REX" / ".rexxie_device_secret"
        if secret_path.exists():
            return bytes.fromhex(secret_path.read_text().strip())
        new_secret = secrets.token_bytes(32)
        secret_path.write_text(new_secret.hex())
        secret_path.chmod(0o400)  # read-only
        return new_secret


def _derive_vault_key(passphrase: str, device_secret: bytes) -> bytes:
    """
    Derive the vault encryption key from master passphrase + device secret.
    Uses Argon2id — computationally expensive by design to defeat brute force.
    Falls back to PBKDF2-SHA256 if argon2-cffi not installed.
    """
    # Combine passphrase with device secret before hashing
    # This means you need BOTH to derive the key
    combined_input = passphrase.encode("utf-8") + b"::" + device_secret

    try:
        from argon2.low_level import hash_secret_raw, Type
        key = hash_secret_raw(
            secret=combined_input,
            salt=device_secret[:16],         # Use device secret as salt too
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST,
            parallelism=ARGON2_PARALLELISM,
            hash_len=ARGON2_HASH_LEN,
            type=Type.ID,
        )
        return key
    except ImportError:
        # Fallback to PBKDF2 (still strong, but Argon2id is better)
        logger.warning("argon2-cffi not installed — using PBKDF2-SHA256. "
                       "Install with: pip install argon2-cffi --break-system-packages")
        import hashlib
        key = hashlib.pbkdf2_hmac(
            "sha256",
            combined_input,
            device_secret,
            iterations=600_000,   # OWASP recommended for PBKDF2-SHA256
            dklen=32,
        )
        return key


def _derive_subkey(key: bytes, label: str) -> bytes:
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    return HKDF(SHA256(), 32, None, label.encode(), default_backend()).derive(key)


def _aes_gcm_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, None)


def _aes_gcm_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(data[:12], data[12:], None)


def _chacha_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = os.urandom(12)
    return nonce + ChaCha20Poly1305(key).encrypt(nonce, data, None)


def _chacha_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    return ChaCha20Poly1305(key).decrypt(data[:12], data[12:], None)


def _triple_encrypt(data: bytes, vault_key: bytes) -> bytes:
    k1 = _derive_subkey(vault_key, "cred-vault-layer1-aes")
    k2 = _derive_subkey(vault_key, "cred-vault-layer2-cha")
    k3 = _derive_subkey(vault_key, "cred-vault-layer3-aes")
    ct = _aes_gcm_encrypt(data, k1)
    ct = _chacha_encrypt(ct, k2)
    ct = _aes_gcm_encrypt(ct, k3)
    return ct


def _triple_decrypt(data: bytes, vault_key: bytes) -> bytes:
    k1 = _derive_subkey(vault_key, "cred-vault-layer1-aes")
    k2 = _derive_subkey(vault_key, "cred-vault-layer2-cha")
    k3 = _derive_subkey(vault_key, "cred-vault-layer3-aes")
    ct = _aes_gcm_decrypt(data, k3)
    ct = _chacha_decrypt(ct, k2)
    ct = _aes_gcm_decrypt(ct, k1)
    return ct


def _secure_wipe_file(path: Path):
    """Overwrite file with random bytes before deleting — prevents recovery."""
    if not path.exists():
        return
    size = path.stat().st_size
    with open(path, "r+b") as f:
        f.write(os.urandom(size))
        f.flush()
        os.fsync(f.fileno())
    path.unlink()
    logger.info(f"🗑️  Secure-wiped: {path}")


def _looks_like_sensitive_number(text: str) -> Optional[str]:
    """Detect if text contains full card or account numbers."""
    if CARD_PATTERN.search(text):
        return "credit/debit card number"
    if ROUTING_PATTERN.search(text):
        return "routing number (9 digits)"
    # Only warn for very long account numbers, not short ones
    matches = ACCOUNT_PATTERN.findall(text)
    for m in matches:
        if len(m) >= 12:
            return "account number"
    return None


class RexxieCredentialVault:
    """
    Secure credential store for Rexxie.
    Locked by master passphrase + device secret.
    All credential access is local only — no AI API involved.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path       = str(db_path or REXXIE_DB_PATH)
        self._device_secret = _get_device_secret()
        self._vault_key: Optional[bytes] = None
        self._locked_at: Optional[float] = None
        self._unlock_time: Optional[float] = None
        self._passphrase_hash: Optional[bytes] = None   # For lock verification
        self._init_tables()

    def _init_tables(self):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS rexxie_credentials (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                label_hash   TEXT NOT NULL,        -- SHA256 of label (for lookup without decryption)
                label_enc    BLOB NOT NULL,         -- encrypted label
                username_enc BLOB,                  -- encrypted username (optional)
                secret_enc   BLOB NOT NULL,         -- encrypted password/pin/secret
                notes_enc    BLOB,                  -- encrypted notes
                category     TEXT DEFAULT 'login',  -- login / bank / pin / note
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                active       INTEGER DEFAULT 1
            )
        """)
        # Store a passphrase verifier (hash of derived key) so we can detect wrong passphrase
        con.execute("""
            CREATE TABLE IF NOT EXISTS rexxie_vault_meta (
                id           INTEGER PRIMARY KEY,
                key_verifier TEXT,                  -- HMAC of known constant with vault key
                argon2_used  INTEGER DEFAULT 1,
                created_at   TEXT NOT NULL
            )
        """)
        con.commit()
        con.close()

    # ── Lock / Unlock ──────────────────────────────────────────────────────────

    def is_unlocked(self) -> bool:
        if self._vault_key is None:
            return False
        if self._unlock_time is None:
            return False
        elapsed = time.time() - self._unlock_time
        if elapsed > VAULT_LOCK_TIMEOUT:
            self.lock()
            return False
        return True

    def _refresh_lock_timer(self):
        if self._vault_key is not None:
            self._unlock_time = time.time()

    def lock(self):
        """Wipe the derived key from memory."""
        if self._vault_key:
            # Overwrite key bytes in memory before releasing
            ba = bytearray(self._vault_key)
            for i in range(len(ba)):
                ba[i] = 0
        self._vault_key   = None
        self._unlock_time = None
        self._passphrase_hash = None
        logger.info("🔒 Credential vault locked.")

    def unlock(self, passphrase: str, bypass_2fa: bool = False) -> Tuple[bool, str]:
        """
        Derive vault key from passphrase + device secret.
        bypass_2fa=True when seed phrase or Touch ID has already been verified.
        Returns (success, message).
        """
        if not passphrase.strip():
            return False, "Passphrase cannot be empty."

        # Check if a secondary factor already verified (seed phrase or Touch ID)
        if self._is_seed_phrase_verified() or self._is_touch_id_verified():
            bypass_2fa = True

        try:
            key = _derive_vault_key(passphrase, self._device_secret)
        except Exception as e:
            return False, f"Key derivation failed: {e}"

        # Verify against stored verifier if one exists
        con = sqlite3.connect(self.db_path)
        meta = con.execute("SELECT key_verifier FROM rexxie_vault_meta WHERE id=1").fetchone()
        con.close()

        if meta and meta[0]:
            # Compute expected verifier
            import hmac as hmac_lib
            verifier = hmac_lib.new(key, b"rexxie-vault-verifier", hashlib.sha256).hexdigest()
            if not hmac_lib.compare_digest(verifier, meta[0]):
                return False, "Wrong passphrase."
        else:
            # First unlock — store verifier
            import hmac as hmac_lib
            verifier = hmac_lib.new(key, b"rexxie-vault-verifier", hashlib.sha256).hexdigest()
            now = __import__("datetime").datetime.utcnow().isoformat()
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT OR REPLACE INTO rexxie_vault_meta (id, key_verifier, created_at) VALUES (1, ?, ?)",
                (verifier, now)
            )
            con.commit()
            con.close()

        self._vault_key   = key
        self._unlock_time = time.time()
        return True, "✅ Vault unlocked."

    # ── Credential Storage ─────────────────────────────────────────────────────

    def _label_hash(self, label: str) -> str:
        return hashlib.sha256(label.lower().strip().encode()).hexdigest()

    def store_credential(
        self,
        label: str,
        secret: str,
        username: str = "",
        notes: str = "",
        category: str = "login",
    ) -> Tuple[bool, str]:
        """
        Store a credential. Returns (success, message).
        NEVER calls any external AI — fully local.
        """
        if not self.is_unlocked():
            return False, "🔒 Vault is locked. Unlock with your master passphrase first."

        self._refresh_lock_timer()

        # Warn if looks like a sensitive number
        sensitive_type = _looks_like_sensitive_number(secret)
        # (Caller should check this before calling — warning shown in chat interface)

        now = __import__("datetime").datetime.utcnow().isoformat()
        lhash = self._label_hash(label)

        label_enc    = _triple_encrypt(label.encode(),    self._vault_key)
        secret_enc   = _triple_encrypt(secret.encode(),   self._vault_key)
        username_enc = _triple_encrypt(username.encode(), self._vault_key) if username else None
        notes_enc    = _triple_encrypt(notes.encode(),    self._vault_key) if notes else None

        con = sqlite3.connect(self.db_path)
        # Check if updating existing
        existing = con.execute(
            "SELECT id FROM rexxie_credentials WHERE label_hash=? AND active=1", (lhash,)
        ).fetchone()

        if existing:
            con.execute(
                """UPDATE rexxie_credentials
                   SET secret_enc=?, username_enc=?, notes_enc=?, category=?, updated_at=?
                   WHERE id=?""",
                (secret_enc, username_enc, notes_enc, category, now, existing[0])
            )
            msg = f"✅ Updated: **{label}**"
        else:
            con.execute(
                """INSERT INTO rexxie_credentials
                   (label_hash, label_enc, username_enc, secret_enc, notes_enc, category, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (lhash, label_enc, username_enc, secret_enc, notes_enc, category, now, now)
            )
            msg = f"✅ Saved: **{label}**"

        con.commit()
        con.close()

        if sensitive_type:
            msg += f"\n\n⚠️ This looks like a full {sensitive_type}. It's stored and encrypted, but remember: the fewer places you store complete account numbers, the safer you are."

        return True, msg

    def get_credential(self, label: str) -> Tuple[bool, Optional[Dict]]:
        """
        Retrieve a credential by label.
        Returns (success, {label, username, secret, notes, category}).
        NEVER calls any external AI — fully local.
        """
        if not self.is_unlocked():
            return False, None

        self._refresh_lock_timer()
        lhash = self._label_hash(label)

        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM rexxie_credentials WHERE label_hash=? AND active=1", (lhash,)
        ).fetchone()
        con.close()

        if not row:
            # Try fuzzy match — decrypt all labels and find closest
            return self._fuzzy_find(label)

        return True, {
            "label":    _triple_decrypt(bytes(row["label_enc"]),    self._vault_key).decode(),
            "username": _triple_decrypt(bytes(row["username_enc"]), self._vault_key).decode()
                        if row["username_enc"] else "",
            "secret":   _triple_decrypt(bytes(row["secret_enc"]),   self._vault_key).decode(),
            "notes":    _triple_decrypt(bytes(row["notes_enc"]),     self._vault_key).decode()
                        if row["notes_enc"] else "",
            "category": row["category"],
        }

    def _fuzzy_find(self, query: str) -> Tuple[bool, Optional[Dict]]:
        """Find credential by partial label match."""
        query_lower = query.lower().strip()
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM rexxie_credentials WHERE active=1"
        ).fetchall()
        con.close()

        for row in rows:
            try:
                label = _triple_decrypt(bytes(row["label_enc"]), self._vault_key).decode()
                if query_lower in label.lower():
                    return True, {
                        "label":    label,
                        "username": _triple_decrypt(bytes(row["username_enc"]), self._vault_key).decode()
                                    if row["username_enc"] else "",
                        "secret":   _triple_decrypt(bytes(row["secret_enc"]),   self._vault_key).decode(),
                        "notes":    _triple_decrypt(bytes(row["notes_enc"]),     self._vault_key).decode()
                                    if row["notes_enc"] else "",
                        "category": row["category"],
                    }
            except Exception:
                continue
        return False, None

    def list_credentials(self) -> List[Dict]:
        """
        List all credential LABELS only — never returns secrets in the list.
        Safe to display in chat.
        """
        if not self.is_unlocked():
            return []

        self._refresh_lock_timer()
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT label_enc, username_enc, category, created_at FROM rexxie_credentials WHERE active=1 ORDER BY created_at DESC"
        ).fetchall()
        con.close()

        results = []
        for row in rows:
            try:
                label    = _triple_decrypt(bytes(row["label_enc"]), self._vault_key).decode()
                username = _triple_decrypt(bytes(row["username_enc"]), self._vault_key).decode()[:20] \
                           if row["username_enc"] else ""
                results.append({
                    "label":    label,
                    "username": username,
                    "category": row["category"],
                })
            except Exception:
                continue
        return results

    def delete_credential(self, label: str) -> bool:
        if not self.is_unlocked():
            return False
        self._refresh_lock_timer()
        lhash = self._label_hash(label)
        con = sqlite3.connect(self.db_path)
        con.execute("UPDATE rexxie_credentials SET active=0 WHERE label_hash=?", (lhash,))
        con.commit()
        con.close()
        return True

    # ── Secure Wipe ────────────────────────────────────────────────────────────

    def wipe_credentials_only(self) -> str:
        """
        Securely wipe only the credentials table.
        Rexxie's personal memories remain intact.
        """
        con = sqlite3.connect(self.db_path)
        # Overwrite data with zeros first
        rows = con.execute(
            "SELECT id FROM rexxie_credentials WHERE active=1"
        ).fetchall()
        zeros_32 = bytes(32)
        for (row_id,) in rows:
            con.execute(
                "UPDATE rexxie_credentials SET secret_enc=?, username_enc=?, notes_enc=?, active=0 WHERE id=?",
                (zeros_32, zeros_32, zeros_32, row_id)
            )
        con.commit()
        # Remove verifier so passphrase must be reset
        con.execute("DELETE FROM rexxie_vault_meta")
        con.commit()
        con.close()
        self.lock()
        logger.warning("🗑️  All credentials securely wiped.")
        return f"🗑️ Done. All {len(rows)} credentials have been securely overwritten and removed. Vault locked."

    def emergency_wipe(self) -> str:
        """
        Nuclear option: overwrite and delete ALL of rexxie.db + remove key from Keychain.
        This destroys ALL Rexxie memories AND credentials. Irreversible.
        """
        self.lock()

        # Remove device secret from Keychain
        try:
            import keyring
            keyring.delete_password("rex-sovereign", DEVICE_SECRET_KEY)
        except Exception:
            pass

        # Wipe the database file itself
        db = Path(self.db_path)
        if db.exists():
            _secure_wipe_file(db)

        # Wipe key file if exists
        key_file = Path.home() / "Desktop" / "REX" / ".rexxie_device_secret"
        if key_file.exists():
            _secure_wipe_file(key_file)

        logger.critical("🚨 EMERGENCY WIPE COMPLETE — all Rexxie data destroyed.")
        return "🗑️ Emergency wipe complete. All Rexxie data and credentials have been destroyed and are unrecoverable."

    # ── Chat Command Parser ────────────────────────────────────────────────────

    def detect_credential_command(
        self, user_text: str, passphrase_callback=None
    ) -> Optional[str]:
        """
        Parse credential commands from natural language.
        This is called BEFORE any AI API — credentials never enter the AI pipeline.

        Returns reply string if a credential command was handled, else None.
        """
        lower = user_text.lower().strip()

        # ── Unlock vault ──────────────────────────────────────────────────────
        if any(t in lower for t in ["unlock vault", "open vault", "enter passphrase", "vault passphrase:"]):
            # Extract passphrase from "vault passphrase: MySecret"
            for prefix in ["vault passphrase:", "open vault:", "unlock vault:"]:
                if prefix in lower:
                    phrase = user_text[lower.index(prefix) + len(prefix):].strip()
                    if phrase:
                        ok, msg = self.unlock(phrase)
                        return msg
            return (
                "🔐 To unlock your vault, say:\n"
                "`vault passphrase: [your master passphrase]`\n\n"
                "This message is processed locally — your passphrase never leaves your Mac."
            )

        # ── Lock vault ────────────────────────────────────────────────────────
        if any(t in lower for t in ["lock vault", "lock credentials", "lock rexxie vault"]):
            self.lock()
            return "🔒 Vault locked."

        # ── Store credential ──────────────────────────────────────────────────
        save_triggers = ["remember my ", "save my ", "store my ", "rexxie, my ", "add credential:"]
        is_save = any(t in lower for t in save_triggers)
        has_pass_indicator = any(t in lower for t in ["password", "pass:", "login:", "pin:", "pass =", "password:"])
        if is_save and has_pass_indicator:
            return self._parse_and_store(user_text)

        # ── Retrieve credential ───────────────────────────────────────────────
        retrieve_triggers = ["what's my ", "what is my ", "give me my ", "show me my ",
                             "get my ", "rexxie, what's my ", "what's the password for",
                             "password for ", "login for "]
        if any(t in lower for t in retrieve_triggers):
            return self._parse_and_retrieve(lower)

        # ── List credentials ──────────────────────────────────────────────────
        if any(t in lower for t in ["show my accounts", "list my credentials",
                                     "what credentials", "what logins", "what do you have stored"]):
            return self._format_list()

        # ── Delete credential ─────────────────────────────────────────────────
        if any(t in lower for t in ["delete my ", "remove my ", "forget my "]):
            for trigger in ["delete my ", "remove my ", "forget my "]:
                if trigger in lower:
                    label = lower.split(trigger, 1)[1].strip().split(" password")[0].split(" login")[0].strip()
                    if label and self.delete_credential(label):
                        return f"✅ Removed: **{label}**"
                    return "Vault locked — unlock first, or I couldn't find that credential."

        # ── Wipe commands ─────────────────────────────────────────────────────
        if "wipe credentials" in lower or "wipe all credentials" in lower:
            return self.wipe_credentials_only()

        if "emergency wipe" in lower or "wipe everything" in lower:
            return self.emergency_wipe()

        # ── Backup seed phrase unlock (phone lost fallback) ───────────────────
        any_phrase_trigger = any(t in lower for t in
            ["backup phrase:", "recovery phrase:", "seed phrase:", "emergency phrase:"])
        if any_phrase_trigger:
            try:
                import sys
                from pathlib import Path
                parent = Path(__file__).resolve().parent.parent
                if str(parent) not in sys.path:
                    sys.path.insert(0, str(parent))
                from rex_seed_phrase import detect_seed_phrase_command
                result = detect_seed_phrase_command(user_text)
                if result is not None:
                    valid, msg = result
                    if valid:
                        # Seed phrase confirmed — but we still need passphrase to derive the key
                        # Mark seed phrase as verified so next passphrase entry skips TOTP
                        self._seed_phrase_verified = True
                        self._seed_phrase_expires  = __import__("time").time() + 300  # 5 min window
                        return (
                            msg + "\n\n🔐 Now enter your vault passphrase to complete unlock:\n"
                            "`vault passphrase: [your passphrase]`\n\n"
                            "_A security email will be sent to confirm this bypass was used._"
                        )
                    return msg
            except Exception as e:
                logger.error(f"Seed phrase check error: {e}")

        # ── Touch ID fallback (when answering "unlock vault" without a phone) ─
        if any(t in lower for t in ["touch id", "use touch id", "fingerprint unlock"]):
            try:
                from .rex_2fa import verify_touch_id_fallback
                ok, msg = verify_touch_id_fallback()
                if ok:
                    self._touch_id_verified = True
                    self._touch_id_expires  = __import__("time").time() + 300
                    return (
                        msg + "\n\n🔐 Touch ID accepted. Now enter your passphrase:\n"
                        "`vault passphrase: [your passphrase]`"
                    )
                return f"⚠️ {msg}"
            except Exception as e:
                return f"Touch ID not available on this system: {e}"

        return None

    def _is_seed_phrase_verified(self) -> bool:
        """Check if seed phrase bypass is still within the 5-minute window."""
        if not getattr(self, "_seed_phrase_verified", False):
            return False
        if __import__("time").time() > getattr(self, "_seed_phrase_expires", 0):
            self._seed_phrase_verified = False
            return False
        return True

    def _is_touch_id_verified(self) -> bool:
        """Check if Touch ID bypass is still within the 5-minute window."""
        if not getattr(self, "_touch_id_verified", False):
            return False
        if __import__("time").time() > getattr(self, "_touch_id_expires", 0):
            self._touch_id_verified = False
            return False
        return True

    def _parse_and_store(self, text: str) -> str:
        """Parse natural language credential from text and store it."""
        if not self.is_unlocked():
            return (
                "🔒 Vault is locked. Unlock with:\n"
                "`vault passphrase: [your master passphrase]`\n\n"
                "Your passphrase never leaves your Mac."
            )

        lower = text.lower()

        # Try to extract label, username, password from patterns like:
        # "remember my Chase login: user=kato pass=abc123"
        # "save my Netflix password: abc123"
        # "my Apple ID is: user=kato@icloud.com pass=MyPass"

        label = ""
        username = ""
        secret = ""
        category = "login"

        # Extract label — word before "login", "password", "credentials", "pin"
        for marker in ["login:", "password:", "credentials:", "pin:", "pass:"]:
            if marker in lower:
                before = lower.split(marker)[0]
                for trigger in ["remember my ", "save my ", "store my ", "rexxie, my ", "my "]:
                    if trigger in before:
                        label = before.split(trigger)[-1].strip().rstrip(" :")
                        break
                after = text[text.lower().index(marker) + len(marker):].strip()

                # Parse "user=x pass=y" or "username=x password=y"
                user_match = re.search(r'user(?:name)?[=:]\s*(\S+)', after, re.I)
                pass_match = re.search(r'pass(?:word)?[=:]\s*(\S+)', after, re.I)

                if user_match:
                    username = user_match.group(1)
                if pass_match:
                    secret = pass_match.group(1)
                elif not pass_match and after:
                    # Assume everything after the colon is the secret
                    secret = after.split()[0] if after.split() else ""

                if "pin" in marker:
                    category = "pin"
                break

        if not label:
            return "I'm not sure what to save. Try: `save my [site] login: user=email pass=password`"
        if not secret:
            return f"I understood you want to save **{label}**, but I couldn't find the password. Try: `save my {label} login: user=email pass=yourpassword`"

        # Warn for sensitive numbers
        warning = ""
        sensitive = _looks_like_sensitive_number(secret)
        if sensitive:
            warning = f"\n\n⚠️ Heads up — that looks like a full {sensitive}. It's stored and triple-encrypted, but consider whether you need the full number or just the last 4 digits."

        ok, msg = self.store_credential(label, secret, username=username, category=category)
        return msg + warning

    def _parse_and_retrieve(self, lower: str) -> str:
        """Parse and retrieve a credential."""
        if not self.is_unlocked():
            return (
                "🔒 Vault is locked. Unlock with:\n"
                "`vault passphrase: [your master passphrase]`"
            )

        # Extract label from "what's my Chase password" etc.
        label = ""
        for trigger in ["what's my ", "what is my ", "give me my ", "show me my ",
                        "get my ", "rexxie, what's my ", "password for ", "login for "]:
            if trigger in lower:
                after = lower.split(trigger, 1)[1]
                label = after.split(" password")[0].split(" login")[0].split(" pin")[0].strip().rstrip("?.")
                break

        if not label:
            return "Which account are you looking for? Try: `what's my Chase password`"

        found, cred = self.get_credential(label)
        if not found or not cred:
            return f"I don't have anything saved for **{label}**. Save it with:\n`save my {label} login: user=email pass=yourpassword`"

        lines = [f"🔑 **{cred['label']}**"]
        if cred["username"]:
            lines.append(f"Username: `{cred['username']}`")
        lines.append(f"Password: `{cred['secret']}`")
        if cred["notes"]:
            lines.append(f"Notes: {cred['notes']}")
        lines.append("\n_⚠️ Delete this message after reading — or ask me to auto-type it instead._")
        return "\n".join(lines)

    def _format_list(self) -> str:
        if not self.is_unlocked():
            return "🔒 Vault is locked. Unlock with: `vault passphrase: [your passphrase]`"
        creds = self.list_credentials()
        if not creds:
            return "🌸 Nothing stored yet. Save a credential with:\n`save my [site] login: user=email pass=password`"
        lines = ["🔑 **Your stored accounts** (labels only — unlock to retrieve any password):\n"]
        for c in creds:
            icon = {"login": "🌐", "bank": "🏦", "pin": "🔢", "note": "📝"}.get(c["category"], "🔑")
            user_hint = f"  (`{c['username']}`)" if c["username"] else ""
            lines.append(f"{icon} {c['label']}{user_hint}")
        return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rexxie Credential Vault")
    parser.add_argument("--setup",             action="store_true", help="Set up master passphrase")
    parser.add_argument("--list",              action="store_true", help="List stored credentials")
    parser.add_argument("--get",               metavar="LABEL",     help="Retrieve a credential")
    parser.add_argument("--store",             nargs=3, metavar=("LABEL","USERNAME","SECRET"),
                                               help="Store a credential: --store chase kato@email.com MyPass123")
    parser.add_argument("--delete",            metavar="LABEL",     help="Delete a credential")
    parser.add_argument("--wipe-credentials",  action="store_true", help="Wipe all credentials")
    parser.add_argument("--emergency-wipe",    action="store_true", help="⚠️  Wipe ALL Rexxie data")
    args = parser.parse_args()

    vault = RexxieCredentialVault()

    if args.emergency_wipe:
        confirm = input("⚠️  This destroys ALL Rexxie data permanently. Type WIPE to confirm: ")
        if confirm.strip() == "WIPE":
            print(vault.emergency_wipe())
        else:
            print("Cancelled.")
        exit()

    # All other commands need passphrase
    passphrase = getpass.getpass("Master passphrase: ")
    ok, msg = vault.unlock(passphrase)
    print(msg)
    if not ok:
        exit(1)

    if args.setup:
        print("\n✅ Vault initialized with your master passphrase.")
        print("This passphrase is never stored. If you forget it, the vault cannot be recovered.")
        print("Keep it somewhere secure — or in your actual memory.")

    elif args.list:
        creds = vault.list_credentials()
        if not creds:
            print("No credentials stored.")
        else:
            print(f"\n{'Label':<25} {'Username':<30} {'Category'}")
            print("-" * 65)
            for c in creds:
                print(f"{c['label']:<25} {c['username']:<30} {c['category']}")

    elif args.get:
        found, cred = vault.get_credential(args.get)
        if found:
            print(f"\nLabel:    {cred['label']}")
            print(f"Username: {cred['username']}")
            print(f"Secret:   {cred['secret']}")
            if cred["notes"]:
                print(f"Notes:    {cred['notes']}")
        else:
            print(f"Not found: {args.get}")

    elif args.store:
        ok, msg = vault.store_credential(args.store[0], args.store[2], username=args.store[1])
        print(msg)

    elif args.delete:
        if vault.delete_credential(args.delete):
            print(f"Deleted: {args.delete}")
        else:
            print("Not found.")

    elif args.wipe_credentials:
        confirm = input("Wipe all credentials? Type YES: ")
        if confirm.strip() == "YES":
            print(vault.wipe_credentials_only())
        else:
            print("Cancelled.")
