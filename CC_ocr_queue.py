"""
CC_ocr_queue.py — SQLite-backed job queue for GOJ OCR scans.
"""

import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "auth_tracker.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ocr_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path    TEXT NOT NULL,
    file_hash    TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'hybrid',
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT DEFAULT (datetime('now')),
    started_at   TEXT,
    completed_at TEXT,
    error        TEXT,
    inserted     INTEGER DEFAULT 0,
    skipped      INTEGER DEFAULT 0,
    UNIQUE(file_hash, mode)
);
"""


def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(_CREATE_TABLE)
    c.commit()
    return c


def _sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def enqueue_scan(file_path: str, mode: str = "hybrid") -> int | None:
    """Compute SHA-256 of file, insert job row, return job id. None if already queued/done."""
    try:
        fhash = _sha256(file_path)
    except FileNotFoundError:
        return None
    with _conn() as c:
        try:
            cur = c.execute(
                "INSERT INTO ocr_jobs (file_path, file_hash, mode) VALUES (?, ?, ?)",
                (str(file_path), fhash, mode),
            )
            c.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # UNIQUE(file_hash, mode) violation — already queued or done
            return None


def get_next_pending() -> dict | None:
    """Return oldest pending job as dict and mark it running. None if queue empty."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM ocr_jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        c.execute(
            "UPDATE ocr_jobs SET status='running', started_at=datetime('now') WHERE id=?",
            (row["id"],),
        )
        c.commit()
        return dict(row)


def mark_done(job_id: int, inserted: int, skipped: int) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE ocr_jobs SET status='done', completed_at=datetime('now'), inserted=?, skipped=? WHERE id=?",
            (inserted, skipped, job_id),
        )
        c.commit()


def mark_error(job_id: int, error_msg: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE ocr_jobs SET status='error', completed_at=datetime('now'), error=? WHERE id=?",
            (str(error_msg)[:1000], job_id),
        )
        c.commit()


def get_queue_status() -> dict:
    with _conn() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) as cnt FROM ocr_jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}


def reset_stuck_jobs() -> int:
    """Reset any job stuck in 'running' for >30 min back to 'pending'. Returns count reset."""
    cutoff = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        cur = c.execute(
            "UPDATE ocr_jobs SET status='pending', started_at=NULL WHERE status='running' AND started_at < ?",
            (cutoff,),
        )
        c.commit()
        return cur.rowcount
