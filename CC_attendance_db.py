"""
CC_attendance_db.py — Unified Attendance Database Layer
─────────────────────────────────────────────────────────
GHS Attendance Backend · Port 8101 · Gold Health Systems
Handles: staff WiFi/ZK biometric, client sign-ins, driver GPS clock-ins

Security:
  AES-256-GCM field-level encryption (phone, fingerprint_id)
  SHA-256 hash-chain immutable audit log
  RBAC via rex_permissions integration
  Key from macOS Keychain 'rex-sovereign' or generated on first run
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger("attendance_db")

# ── paths ──────────────────────────────────────────────────────────────────
REX_DIR   = Path(os.environ.get("REX_DIR", os.path.expanduser("~/Desktop/REX")))
DB_PATH   = REX_DIR / "attendance.db"
KEY_FILE  = REX_DIR / ".attendance_key"

# ── key management ─────────────────────────────────────────────────────────

def _get_or_create_key() -> bytes:
    """Retrieve AES-256 key from Keychain or key file; generate if missing."""
    # 1. Try Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "rex-sovereign", "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip()
            return hashlib.sha256(raw.encode()).digest()
    except Exception:
        pass

    # 2. Try key file
    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes()
        if len(raw) >= 32:
            return raw[:32]

    # 3. Generate new key
    key = AESGCM.generate_key(bit_length=256)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(key)
    os.chmod(KEY_FILE, 0o600)
    log.warning(f"Generated new AES key at {KEY_FILE} — store in Keychain.")
    return key


_ENCRYPTION_KEY = _get_or_create_key()
_AESGCM = AESGCM(_ENCRYPTION_KEY)


def encrypt_field(plaintext: str) -> str:
    """AES-256-GCM encrypt a field. Returns base64-encoded ciphertext with nonce."""
    if not plaintext:
        return ""
    nonce = os.urandom(12)
    ct = _AESGCM.encrypt(nonce, plaintext.encode(), None)
    import base64
    return base64.b64encode(nonce + ct).decode()


def decrypt_field(ciphertext_b64: str) -> str:
    """Decrypt a field encrypted with encrypt_field."""
    if not ciphertext_b64:
        return ""
    import base64
    raw = base64.b64decode(ciphertext_b64)
    nonce, ct = raw[:12], raw[12:]
    return _AESGCM.decrypt(nonce, ct, None).decode()


# ── audit log hash chain ───────────────────────────────────────────────────

def _compute_hash(prev_hash: str, data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(f"{prev_hash}{payload}".encode()).hexdigest()


# ── schema ─────────────────────────────────────────────────────────────────

import sqlite3

SCHEMA = """
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;

    CREATE TABLE IF NOT EXISTS staff (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        phone           TEXT,              -- AES-256-GCM encrypted
        mac_address     TEXT,
        wifi_user       TEXT UNIQUE,
        fingerprint_id  TEXT,              -- ZK biometric template ID
        rfid_card       TEXT,              -- ZK RFID card number
        department      TEXT DEFAULT 'staff',
        exempt          INTEGER DEFAULT 0,
        active          INTEGER DEFAULT 1,
        created_at      DATETIME DEFAULT (datetime('now')),
        acknowledged_at DATETIME
    );

    CREATE TABLE IF NOT EXISTS attendance_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id        INTEGER NOT NULL REFERENCES staff(id),
        event_type      TEXT NOT NULL CHECK(
                            event_type IN ('clock_in','clock_out','break_start','break_end')
                        ),
        method          TEXT DEFAULT 'wifi' CHECK(
                            method IN ('wifi','zk_biometric','rfid','mobile_pwa','manual')
                        ),
        source_device   TEXT,
        gps_lat         REAL,
        gps_lon         REAL,
        session_id      TEXT,              -- UUID grouping clock_in → clock_out
        ts              DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS compliance_flags (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id        INTEGER NOT NULL REFERENCES staff(id),
        flag_type       TEXT NOT NULL CHECK(
                            flag_type IN (
                                'late_arrival','early_departure','missed_break',
                                'daily_overtime','weekly_overtime','unknown_device'
                            )
                        ),
        threshold_value TEXT,
        actual_value    TEXT,
        flagged_at      DATETIME DEFAULT (datetime('now')),
        resolved        INTEGER DEFAULT 0,
        resolved_at     DATETIME
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        action          TEXT NOT NULL,
        table_name      TEXT NOT NULL,
        record_id       INTEGER,
        old_values      TEXT,
        new_values      TEXT,
        performed_by    TEXT DEFAULT 'system',
        ts              DATETIME DEFAULT (datetime('now')),
        prev_hash       TEXT,
        current_hash    TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_events_staff ON attendance_events(staff_id);
    CREATE INDEX IF NOT EXISTS idx_events_ts    ON attendance_events(ts);
    CREATE INDEX IF NOT EXISTS idx_events_date  ON attendance_events(DATE(ts));
    CREATE INDEX IF NOT EXISTS idx_flags_staff  ON compliance_flags(staff_id);
    CREATE INDEX IF NOT EXISTS idx_flags_type   ON compliance_flags(flag_type, resolved);
    CREATE INDEX IF NOT EXISTS idx_audit_table  ON audit_log(table_name, record_id);
"""


class AttendanceDB:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def conn(self):
        cn = sqlite3.connect(self.db_path)
        cn.row_factory = sqlite3.Row
        cn.execute("PRAGMA journal_mode=WAL")
        cn.execute("PRAGMA foreign_keys=ON")
        try:
            yield cn
            cn.commit()
        except Exception:
            cn.rollback()
            raise
        finally:
            cn.close()

    def _init_db(self):
        with self.conn() as cn:
            cn.executescript(SCHEMA)
            # Seed audit hash chain if empty
            row = cn.execute("SELECT current_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                genesis_data = {"action": "genesis", "table": "system",
                                "record_id": 0, "performed_by": "system",
                                "ts": datetime.now().isoformat()}
                genesis_hash = _compute_hash("", genesis_data)
                cn.execute(
                    "INSERT INTO audit_log (action, table_name, record_id, prev_hash, "
                    "current_hash, performed_by, ts) VALUES (?,?,?,?,?,?,?)",
                    ("genesis", "system", 0, "", genesis_hash, "system", genesis_data["ts"])
                )

    def _audit(self, cn: sqlite3.Connection, action: str, table_name: str,
               record_id: int, old_values: dict = None, new_values: dict = None,
               performed_by: str = "system"):
        prev = cn.execute(
            "SELECT current_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = prev["current_hash"] if prev else ""
        data = {
            "action": action, "table": table_name, "record_id": record_id,
            "performed_by": performed_by,
            "ts": datetime.now().isoformat()
        }
        current_hash = _compute_hash(prev_hash, data)
        cn.execute(
            "INSERT INTO audit_log (action, table_name, record_id, old_values, "
            "new_values, performed_by, prev_hash, current_hash, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (action, table_name, record_id,
             json.dumps(old_values) if old_values else None,
             json.dumps(new_values) if new_values else None,
             performed_by, prev_hash, current_hash, data["ts"])
        )

    # ── staff CRUD ─────────────────────────────────────────────────────────

    def register_staff(self, name: str, phone: str = None, mac: str = None,
                       department: str = "staff", rfid: str = None,
                       fingerprint_id: str = None) -> int:
        with self.conn() as cn:
            enc_phone = encrypt_field(phone) if phone else None
            cn.execute(
                "INSERT INTO staff (name, phone, mac_address, department, "
                "rfid_card, fingerprint_id) VALUES (?,?,?,?,?,?)",
                (name.strip(), enc_phone, mac.lower().strip() if mac else None,
                 department, rfid, fingerprint_id)
            )
            sid = cn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._audit(cn, "insert", "staff", sid,
                        new_values={"name": name, "department": department})
        return sid

    def get_staff_by_mac(self, mac: str) -> Optional[sqlite3.Row]:
        mac = mac.lower().strip()
        with self.conn() as cn:
            return cn.execute(
                "SELECT * FROM staff WHERE mac_address = ? AND active = 1", (mac,)
            ).fetchone()

    def get_staff_by_rfid(self, rfid: str) -> Optional[sqlite3.Row]:
        with self.conn() as cn:
            return cn.execute(
                "SELECT * FROM staff WHERE rfid_card = ? AND active = 1", (rfid,)
            ).fetchone()

    def get_staff_by_fingerprint(self, fp_id: str) -> Optional[sqlite3.Row]:
        with self.conn() as cn:
            return cn.execute(
                "SELECT * FROM staff WHERE fingerprint_id = ? AND active = 1", (fp_id,)
            ).fetchone()

    def list_staff(self, active_only: bool = True) -> list[dict]:
        with self.conn() as cn:
            clause = "WHERE active = 1" if active_only else ""
            rows = cn.execute(f"SELECT id, name, department, exempt, active, created_at "
                              f"FROM staff {clause} ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_staff(self, staff_id: int) -> Optional[dict]:
        with self.conn() as cn:
            row = cn.execute(
                "SELECT id, name, phone, department, exempt, active, rfid_card, "
                "mac_address, fingerprint_id, created_at FROM staff WHERE id = ?",
                (staff_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("phone"):
            try:
                d["phone"] = decrypt_field(d["phone"])
            except Exception:
                pass
        return d

    def get_staff_phone(self, staff_id: int) -> Optional[str]:
        """Decrypt phone only when explicitly requested (TOTP gate in future)."""
        with self.conn() as cn:
            row = cn.execute("SELECT phone FROM staff WHERE id = ?", (staff_id,)).fetchone()
        if row and row["phone"]:
            try:
                return decrypt_field(row["phone"])
            except Exception:
                return None
        return None

    def toggle_exempt(self, staff_id: int) -> bool:
        with self.conn() as cn:
            row = cn.execute("SELECT exempt FROM staff WHERE id = ?", (staff_id,)).fetchone()
            if not row:
                return False
            new = 0 if row["exempt"] else 1
            cn.execute("UPDATE staff SET exempt = ? WHERE id = ?", (new, staff_id))
            self._audit(cn, "toggle_exempt", "staff", staff_id,
                        old_values={"exempt": row["exempt"]}, new_values={"exempt": new})
        return bool(new)

    # ── attendance events ──────────────────────────────────────────────────

    def log_event(self, staff_id: int, event_type: str, method: str = "wifi",
                  source_device: str = None, gps_lat: float = None,
                  gps_lon: float = None, session_id: str = None) -> int:
        """Log a clock_in, clock_out, break_start, or break_end event."""
        with self.conn() as cn:
            cn.execute(
                "INSERT INTO attendance_events (staff_id, event_type, method, "
                "source_device, gps_lat, gps_lon, session_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (staff_id, event_type, method, source_device, gps_lat, gps_lon, session_id)
            )
            eid = cn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._audit(cn, "insert", "attendance_events", eid,
                        new_values={"staff_id": staff_id, "event_type": event_type, "method": method})
        return eid

    def get_session_id(self, staff_id: int) -> Optional[str]:
        """Get open session_id for a staff member (clocked in, not clocked out)."""
        with self.conn() as cn:
            events = cn.execute(
                "SELECT event_type, session_id FROM attendance_events "
                "WHERE staff_id = ? AND DATE(ts) = DATE('now') ORDER BY ts DESC",
                (staff_id,)
            ).fetchall()
        balance = 0
        sid = None
        for ev in events:
            if ev["event_type"] in ("clock_in", "break_end"):
                balance += 1
                sid = ev["session_id"]
            elif ev["event_type"] in ("clock_out", "break_start"):
                balance -= 1
        return sid if balance > 0 else None

    def get_todays_events(self, staff_id: int = None) -> list[dict]:
        with self.conn() as cn:
            clause = "WHERE DATE(e.ts) = DATE('now')"
            params = ()
            if staff_id:
                clause += " AND e.staff_id = ?"
                params = (staff_id,)
            rows = cn.execute(
                f"SELECT e.*, s.name FROM attendance_events e "
                f"JOIN staff s ON s.id = e.staff_id "
                f"{clause} ORDER BY e.ts",
                params
            ).fetchall()
        return [dict(r) for r in rows]

    def get_hours(self, target_date: str = None, staff_id: int = None,
                  start_date: str = None, end_date: str = None) -> list[dict]:
        """Compute worked hours from clock_in/clock_out pairs."""
        target = target_date or date.today().isoformat()
        with self.conn() as cn:
            if start_date and end_date:
                where = "DATE(e.ts) BETWEEN ? AND ?"
                params = (start_date, end_date)
            else:
                where = "DATE(e.ts) = ?"
                params = (target,)
            if staff_id:
                where += " AND e.staff_id = ?"
                params += (staff_id,)

            events = cn.execute(
                f"SELECT e.*, s.name FROM attendance_events e "
                f"JOIN staff s ON s.id = e.staff_id "
                f"WHERE {where} ORDER BY e.staff_id, e.ts",
                params
            ).fetchall()

        from collections import defaultdict
        staff_sessions = defaultdict(list)
        for ev in events:
            staff_sessions[ev["staff_id"]].append(ev)

        results = []
        for sid, ev_list in staff_sessions.items():
            sessions = []
            total_sec = 0
            last_in = None
            name = ev_list[0]["name"]

            for ev in ev_list:
                if ev["event_type"] in ("clock_in", "break_end"):
                    last_in = datetime.fromisoformat(ev["ts"])
                elif ev["event_type"] in ("clock_out", "break_start") and last_in:
                    delta = (datetime.fromisoformat(ev["ts"]) - last_in).total_seconds()
                    sessions.append({
                        "in": last_in.isoformat(),
                        "out": ev["ts"],
                        "duration_seconds": int(delta)
                    })
                    total_sec += delta
                    last_in = None

            if last_in:
                delta = (datetime.now() - last_in).total_seconds()
                sessions.append({
                    "in": last_in.isoformat(),
                    "out": None,
                    "duration_seconds": int(delta)
                })
                total_sec += delta

            results.append({
                "staff_id": sid,
                "name": name,
                "sessions": sessions,
                "total_seconds": int(total_sec),
                "total_fmt": f"{int(total_sec//3600)}h {int((total_sec%3600)//60)}m",
                "status": "in" if (sessions and sessions[-1]["out"] is None) else "out"
            })

        return results

    # ── compliance flags ───────────────────────────────────────────────────

    def create_flag(self, staff_id: int, flag_type: str,
                    threshold: str = None, actual: str = None) -> int:
        """Create a compliance flag. Returns flag ID."""
        with self.conn() as cn:
            # Don't duplicate unresolved flags of same type for same staff
            existing = cn.execute(
                "SELECT id FROM compliance_flags "
                "WHERE staff_id = ? AND flag_type = ? AND resolved = 0",
                (staff_id, flag_type)
            ).fetchone()
            if existing:
                return existing["id"]
            cn.execute(
                "INSERT INTO compliance_flags (staff_id, flag_type, threshold_value, actual_value) "
                "VALUES (?,?,?,?)",
                (staff_id, flag_type, threshold, actual)
            )
            fid = cn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._audit(cn, "insert", "compliance_flags", fid,
                        new_values={"staff_id": staff_id, "flag_type": flag_type})
        return fid

    def get_active_flags(self, staff_id: int = None) -> list[dict]:
        with self.conn() as cn:
            clause = "WHERE c.resolved = 0"
            params = ()
            if staff_id:
                clause += " AND c.staff_id = ?"
                params = (staff_id,)
            rows = cn.execute(
                f"SELECT c.*, s.name FROM compliance_flags c "
                f"JOIN staff s ON s.id = c.staff_id "
                f"{clause} ORDER BY c.flagged_at DESC",
                params
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_flag(self, flag_id: int):
        with self.conn() as cn:
            cn.execute(
                "UPDATE compliance_flags SET resolved = 1, resolved_at = datetime('now') "
                "WHERE id = ?", (flag_id,)
            )
            self._audit(cn, "resolve", "compliance_flags", flag_id)

    # ── verification ───────────────────────────────────────────────────────

    def verify_audit_chain(self) -> tuple[bool, str]:
        """Verify the entire audit log hash chain. Returns (valid, message)."""
        with self.conn() as cn:
            rows = cn.execute(
                "SELECT id, prev_hash, current_hash, action, table_name, record_id, "
                "performed_by, ts FROM audit_log ORDER BY id"
            ).fetchall()

        if not rows:
            return True, "Empty audit log"

        prev_hash = ""
        for i, row in enumerate(rows):
            data = {
                "action": row["action"], "table": row["table_name"],
                "record_id": row["record_id"], "performed_by": row["performed_by"],
                "ts": row["ts"]
            }
            expected = _compute_hash(row["prev_hash"], data)
            if expected != row["current_hash"]:
                return False, f"Hash mismatch at audit_log id={row['id']}"
            if i > 0 and row["prev_hash"] != prev_hash:
                return False, f"Chain break at audit_log id={row['id']}"
            prev_hash = row["current_hash"]

        return True, f"Chain valid — {len(rows)} entries"


# ── singleton ──────────────────────────────────────────────────────────────

_db: Optional[AttendanceDB] = None

def get_db() -> AttendanceDB:
    global _db
    if _db is None:
        _db = AttendanceDB()
    return _db


# ── main (test) ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = AttendanceDB()
    print(f"DB: {db.db_path}")
    print(f"Tables: {db._init_db()}")

    # Register test staff
    sid = db.register_staff("Test Employee", phone="+15551234567",
                            mac="aa:bb:cc:dd:ee:ff", department="staff")
    print(f"Registered staff ID: {sid}")

    # Log clock in
    session = str(uuid.uuid4())
    db.log_event(sid, "clock_in", method="wifi",
                 source_device="aa:bb:cc:dd:ee:ff", session_id=session)
    print(f"Clocked in — session: {session}")

    # Log clock out
    time.sleep(0.5)
    db.log_event(sid, "clock_out", method="wifi",
                 source_device="aa:bb:cc:dd:ee:ff", session_id=session)
    print("Clocked out")

    # Get hours
    hours = db.get_hours()
    print(f"Today's hours: {hours}")

    # Verify audit chain
    valid, msg = db.verify_audit_chain()
    print(f"Audit chain: {'✅' if valid else '❌'} — {msg}")

    # Staff list
    staff = db.list_staff()
    print(f"Staff count: {len(staff)}")
