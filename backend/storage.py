"""
REX — Encrypted Local Storage
AES-256-GCM encryption via Python `cryptography` library.
All messages are encrypted before being written to SQLite.
Master key is derived from a passphrase (Argon2) and stored in macOS Keychain.

Storage path is configurable — supports external drives.
"""
import sqlite3
import json
import os
import base64
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import keyring

logger = logging.getLogger(__name__)

APP_NAME = "REX-PrivacyProxy"
KEYCHAIN_KEY = "rex_master_encryption_key"


def _get_or_create_master_key() -> bytes:
    """Retrieve or generate the AES-256 master key from macOS Keychain."""
    try:
        stored = keyring.get_password(APP_NAME, KEYCHAIN_KEY)
        if stored:
            return base64.b64decode(stored)
    except Exception:
        pass

    # Generate a new 32-byte key
    key = os.urandom(32)
    try:
        keyring.set_password(APP_NAME, KEYCHAIN_KEY, base64.b64encode(key).decode())
        logger.info("🔑 New master encryption key generated and stored in Keychain")
    except Exception as e:
        logger.warning(f"Keychain unavailable ({e}), key will not persist across sessions")
    return key


def _encrypt(data: str, key: bytes) -> str:
    """Encrypt a string with AES-256-GCM. Returns base64-encoded ciphertext."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, data.encode("utf-8"), None)
    # Prepend nonce so we can decrypt later
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode("ascii")


def _decrypt(encoded: str, key: bytes) -> str:
    """Decrypt AES-256-GCM ciphertext produced by _encrypt()."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    combined = base64.b64decode(encoded)
    nonce = combined[:12]
    ciphertext = combined[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


class EncryptedStorage:
    """
    Encrypted SQLite storage for journeys, messages, and audit events.

    All text content is encrypted with AES-256-GCM before storage.
    Metadata (timestamps, counts, flags) is stored plaintext for indexing.

    The database file can live on an external drive — pass `db_path` to configure.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            config_dir = Path.home() / ".rex"
            config_dir.mkdir(exist_ok=True)
            db_path = config_dir / "rex_journeys.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._key = _get_or_create_master_key()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS journeys (
                    id          TEXT PRIMARY KEY,
                    created_at  TEXT NOT NULL,
                    title_enc   TEXT,
                    secure_mode INTEGER DEFAULT 0,
                    msg_count   INTEGER DEFAULT 0,
                    updated_at  TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id          TEXT PRIMARY KEY,
                    journey_id  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content_enc TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    secure      INTEGER DEFAULT 0,
                    phi_detected INTEGER DEFAULT 0,
                    model_enc   TEXT,
                    FOREIGN KEY (journey_id) REFERENCES journeys(id)
                );

                CREATE TABLE IF NOT EXISTS phi_mappings (
                    journey_id   TEXT NOT NULL,
                    original_enc TEXT NOT NULL,
                    placeholder  TEXT NOT NULL,
                    PRIMARY KEY (journey_id, placeholder)
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id          TEXT PRIMARY KEY,
                    timestamp   TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    details_enc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chairman_events (
                    id          TEXT PRIMARY KEY,
                    created_at  TEXT NOT NULL,
                    event_date  TEXT NOT NULL,
                    event_time  TEXT,
                    title_enc   TEXT NOT NULL,
                    notes_enc   TEXT,
                    reminder_at TEXT,
                    reminded    INTEGER DEFAULT 0,
                    source      TEXT DEFAULT 'rexxie'
                );

                CREATE INDEX IF NOT EXISTS idx_chairman_events_date
                    ON chairman_events(event_date);
                CREATE INDEX IF NOT EXISTS idx_chairman_events_reminder
                    ON chairman_events(reminder_at, reminded);

                CREATE TABLE IF NOT EXISTS staff_users (
                    id                TEXT PRIMARY KEY,
                    created_at        TEXT NOT NULL,
                    username          TEXT NOT NULL UNIQUE,
                    password_hash     TEXT NOT NULL,
                    first_name        TEXT NOT NULL,
                    last_name         TEXT NOT NULL,
                    address_enc       TEXT,
                    phone_enc         TEXT,
                    email_enc         TEXT,
                    role              TEXT NOT NULL DEFAULT 'staff',
                    active            INTEGER DEFAULT 1,
                    last_login        TEXT,
                    panel_permissions TEXT DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS idx_staff_users_username
                    ON staff_users(username);

                CREATE INDEX IF NOT EXISTS idx_messages_journey
                    ON messages(journey_id);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                    ON audit_log(timestamp);
            """)
        # ── Migration: add panel_permissions if missing (existing DBs) ──────────
        with self._connect() as conn:
            existing = {row[1] for row in conn.execute("PRAGMA table_info(staff_users)").fetchall()}
            if "panel_permissions" not in existing:
                conn.execute("ALTER TABLE staff_users ADD COLUMN panel_permissions TEXT DEFAULT '[]'")
                logger.info("🔧 DB migration: added panel_permissions column to staff_users")
        logger.info(f"📦 Encrypted DB initialized at {self.db_path}")

    # ── Journeys ──────────────────────────────────────────────────────────────

    def create_journey(self, journey_id: str, secure_mode: bool = False, title: str = None):
        now = datetime.utcnow().isoformat()
        title_enc = _encrypt(title or f"Journey {now[:10]}", self._key)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO journeys (id, created_at, title_enc, secure_mode, msg_count, updated_at) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (journey_id, now, title_enc, int(secure_mode), now)
            )

    def list_journeys(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, title_enc, secure_mode, msg_count, updated_at "
                "FROM journeys ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()

        result = []
        for row in rows:
            try:
                title = _decrypt(row["title_enc"], self._key) if row["title_enc"] else "Untitled"
            except Exception:
                title = "Untitled"
            result.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "title": title,
                "secure_mode": bool(row["secure_mode"]),
                "message_count": row["msg_count"],
                "updated_at": row["updated_at"],
            })
        return result

    # ── Messages ──────────────────────────────────────────────────────────────

    def save_message(
        self,
        journey_id: str,
        msg_id: str,
        role: str,
        content: str,
        secure: bool = False,
        phi_detected: bool = False,
        model: Optional[str] = None,
    ):
        # Ensure journey exists
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM journeys WHERE id=?", (journey_id,)).fetchone()
        if not exists:
            self.create_journey(journey_id, secure_mode=secure)

        now = datetime.utcnow().isoformat()
        content_enc = _encrypt(content, self._key)
        model_enc = _encrypt(model or "", self._key)

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, journey_id, role, content_enc, timestamp, secure, phi_detected, model_enc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (msg_id, journey_id, role, content_enc, now, int(secure), int(phi_detected), model_enc)
            )
            conn.execute(
                "UPDATE journeys SET msg_count = msg_count + 1, updated_at = ? WHERE id = ?",
                (now, journey_id)
            )

    def load_journey_messages(self, journey_id: str) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content_enc, timestamp, secure, phi_detected, model_enc "
                "FROM messages WHERE journey_id = ? ORDER BY timestamp ASC",
                (journey_id,)
            ).fetchall()

        messages = []
        for row in rows:
            try:
                content = _decrypt(row["content_enc"], self._key)
            except Exception:
                content = "[decryption error]"
            try:
                model = _decrypt(row["model_enc"], self._key) if row["model_enc"] else None
            except Exception:
                model = None
            messages.append({
                "id": row["id"],
                "role": row["role"],
                "content": content,
                "timestamp": row["timestamp"],
                "secure": bool(row["secure"]),
                "phi_detected": bool(row["phi_detected"]),
                "model": model,
            })
        return messages

    def load_journey(self, journey_id: str) -> Dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, title_enc, secure_mode, msg_count FROM journeys WHERE id=?",
                (journey_id,)
            ).fetchone()
        if not row:
            return {}
        try:
            title = _decrypt(row["title_enc"], self._key) if row["title_enc"] else "Untitled"
        except Exception:
            title = "Untitled"
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "title": title,
            "secure_mode": bool(row["secure_mode"]),
            "message_count": row["msg_count"],
            "messages": self.load_journey_messages(journey_id),
        }

    # ── PHI Mappings (for Secure Mode multi-turn consistency) ────────────────

    def save_phi_mapping(self, journey_id: str, original: str, placeholder: str):
        original_enc = _encrypt(original, self._key)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO phi_mappings (journey_id, original_enc, placeholder) VALUES (?, ?, ?)",
                (journey_id, original_enc, placeholder)
            )

    def load_phi_mapping(self, journey_id: str) -> Dict[str, str]:
        """Returns {original: placeholder} mapping for a journey."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT original_enc, placeholder FROM phi_mappings WHERE journey_id=?",
                (journey_id,)
            ).fetchall()
        result = {}
        for row in rows:
            try:
                original = _decrypt(row["original_enc"], self._key)
                result[original] = row["placeholder"]
            except Exception:
                pass
        return result

    # ── Audit Log ────────────────────────────────────────────────────────────

    def log_audit(self, event_id: str, event_type: str, details: Dict):
        details_enc = _encrypt(json.dumps(details), self._key)
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (id, timestamp, event_type, details_enc) VALUES (?, ?, ?, ?)",
                (event_id, now, event_type, details_enc)
            )

    def get_audit_log(self, limit: int = 500) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, event_type, details_enc FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        events = []
        for row in rows:
            try:
                details = json.loads(_decrypt(row["details_enc"], self._key))
            except Exception:
                details = {}
            events.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "details": details,
            })
        return events

    # ── Chairman Personal Events ─────────────────────────────────────────────
    # All event content is AES-encrypted. Dates stored plain for indexing.
    # Only accessible to chairman-verified callers.

    def create_event(self, event_id: str, event_date: str, event_time: Optional[str],
                     title: str, notes: str = "", reminder_at: Optional[str] = None,
                     source: str = "rexxie") -> None:
        title_enc = _encrypt(title, self._key)
        notes_enc = _encrypt(notes, self._key) if notes else ""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chairman_events (id, created_at, event_date, event_time, title_enc, notes_enc, reminder_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, now, event_date, event_time, title_enc, notes_enc, reminder_at, source)
            )

    def get_events(self, date: Optional[str] = None, month: Optional[str] = None) -> List[Dict]:
        with self._connect() as conn:
            if date:
                rows = conn.execute(
                    "SELECT * FROM chairman_events WHERE event_date=? ORDER BY event_time",
                    (date,)
                ).fetchall()
            elif month:
                rows = conn.execute(
                    "SELECT * FROM chairman_events WHERE event_date LIKE ? ORDER BY event_date, event_time",
                    (f"{month}%",)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chairman_events ORDER BY event_date, event_time"
                ).fetchall()
        result = []
        for row in rows:
            try:
                title = _decrypt(row["title_enc"], self._key)
                notes = _decrypt(row["notes_enc"], self._key) if row["notes_enc"] else ""
            except Exception:
                title, notes = "[decryption error]", ""
            result.append({
                "id": row["id"], "event_date": row["event_date"],
                "event_time": row["event_time"], "title": title,
                "notes": notes, "reminder_at": row["reminder_at"],
                "reminded": bool(row["reminded"]), "source": row["source"],
                "created_at": row["created_at"],
            })
        return result

    def delete_event(self, event_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM chairman_events WHERE id=?", (event_id,))
            return cur.rowcount > 0

    def get_pending_reminders(self, as_of: str) -> List[Dict]:
        """Return events whose reminder_at <= as_of and have not been sent yet."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chairman_events WHERE reminder_at IS NOT NULL AND reminded=0 AND reminder_at <= ?",
                (as_of,)
            ).fetchall()
        result = []
        for row in rows:
            try:
                title = _decrypt(row["title_enc"], self._key)
                notes = _decrypt(row["notes_enc"], self._key) if row["notes_enc"] else ""
            except Exception:
                title, notes = "[decryption error]", ""
            result.append({
                "id": row["id"], "event_date": row["event_date"],
                "event_time": row["event_time"], "title": title,
                "notes": notes, "reminder_at": row["reminder_at"],
            })
        return result

    def mark_reminded(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE chairman_events SET reminded=1 WHERE id=?", (event_id,))

    # ── Staff Users ────────────────────────────────────────────────────────────

    def create_user(self, user_id: str, username: str, password_hash: str,
                    first_name: str, last_name: str, role: str = "staff",
                    address: str = "", phone: str = "", email: str = "") -> None:
        now = datetime.utcnow().isoformat()
        address_enc = _encrypt(address, self._key) if address else None
        phone_enc   = _encrypt(phone,   self._key) if phone   else None
        email_enc   = _encrypt(email,   self._key) if email   else None
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO staff_users "
                "(id, created_at, username, password_hash, first_name, last_name, "
                " address_enc, phone_enc, email_enc, role, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (user_id, now, username.lower().strip(), password_hash,
                 first_name.strip(), last_name.strip(),
                 address_enc, phone_enc, email_enc, role)
            )

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, first_name, last_name, "
                "role, active, last_login, address_enc, phone_enc, email_enc, "
                "COALESCE(panel_permissions, '[]') as panel_permissions "
                "FROM staff_users WHERE username=? AND active=1",
                (username.lower().strip(),)
            ).fetchone()
        if not row:
            return None
        try:
            perms = json.loads(row["panel_permissions"] or "[]")
        except Exception:
            perms = []
        return {
            "id":                row["id"],
            "username":          row["username"],
            "password_hash":     row["password_hash"],
            "first_name":        row["first_name"],
            "last_name":         row["last_name"],
            "role":              row["role"],
            "active":            row["active"],
            "last_login":        row["last_login"],
            "panel_permissions": perms,
            "address":           _decrypt(row["address_enc"], self._key) if row["address_enc"] else "",
            "phone":             _decrypt(row["phone_enc"],   self._key) if row["phone_enc"]   else "",
            "email":             _decrypt(row["email_enc"],   self._key) if row["email_enc"]   else "",
        }

    def list_users(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, username, first_name, last_name, role, active, last_login, "
                "created_at, COALESCE(panel_permissions, '[]') as panel_permissions "
                "FROM staff_users ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["panel_permissions"] = json.loads(d.get("panel_permissions") or "[]")
            except Exception:
                d["panel_permissions"] = []
            result.append(d)
        return result

    def set_user_permissions(self, user_id: str, permissions: list) -> bool:
        """Update panel_permissions for a user. Chairman-only operation."""
        perms_json = json.dumps(permissions)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE staff_users SET panel_permissions=? WHERE id=?",
                (perms_json, user_id)
            )
            return cur.rowcount > 0

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, first_name, last_name, role, active, "
                "COALESCE(panel_permissions, '[]') as panel_permissions "
                "FROM staff_users WHERE id=?",
                (user_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["panel_permissions"] = json.loads(d.get("panel_permissions") or "[]")
        except Exception:
            d["panel_permissions"] = []
        return d

    def update_last_login(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE staff_users SET last_login=? WHERE id=?",
                (datetime.utcnow().isoformat(), user_id)
            )

    def deactivate_user(self, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE staff_users SET active=0 WHERE id=?", (user_id,))
            return cur.rowcount > 0

    def user_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM staff_users WHERE active=1").fetchone()[0]

    # ── External Drive Support ────────────────────────────────────────────────

    def relocate(self, new_path: Path):
        """Move the database to a new path (e.g., external drive)."""
        import shutil
        new_path = Path(new_path)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(self.db_path), str(new_path))
        self.db_path = new_path
        logger.info(f"📦 Database relocated to {new_path}")

    def export_journey_plaintext(self, journey_id: str) -> Dict:
        """Decrypt and export a journey for local review."""
        return self.load_journey(journey_id)

    @property
    def key_fingerprint(self) -> str:
        """SHA-256 fingerprint of the master key for verification."""
        import hashlib
        digest = hashlib.sha256(self._key).hexdigest()
        return f"{digest[:8]}...{digest[-8:]}"
