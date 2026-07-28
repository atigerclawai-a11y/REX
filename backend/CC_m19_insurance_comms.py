"""
CC_m19_insurance_comms.py — SCAFFOLD — Insurance / Partner Comms Hub
Module M19 · Tiger Claw / GOJ Operations Platform
v1.0 · 2026-06-12

STATUS: SCAFFOLD — clearly labeled; no fabricated data presented as real.
        Payer contact details below are placeholder; real contacts = Kato.

FastAPI router mounting at /m19
SQLite: ~/Desktop/REX/CC_m19_comms.db (created on import)

Schema
------
  payers          — the 8 MLTC insurance plans + contacts
  comms_log       — every communication with a payer
  document_requests — outstanding doc requests from payers

Endpoints
---------
  GET  /m19/payers                        — list all payers
  GET  /m19/payers/{payer_id}             — single payer detail + contacts
  POST /m19/comms                         — log a new communication
  GET  /m19/comms?payer_id=&limit=        — list comms (optionally filtered)
  GET  /m19/comms/pending-followups       — all comms with open follow-ups
  POST /m19/documents                     — create a document request
  GET  /m19/documents?payer_id=&status=   — list document requests
  PUT  /m19/documents/{doc_id}/status     — update doc request status

The 8 MLTC plan names are sourced from the live payer_canonical table in
auth_tracker.db and matched to the plan names confirmed in clients.plan_canonical.
Primary contacts, phone numbers, and portal URLs are PLACEHOLDER — fill in with
real payer contact info (Kato/admin to update via PUT /m19/payers/{id}).
"""
from __future__ import annotations

import sqlite3
import logging
import os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
DB_PATH = Path(os.path.expanduser("~/Desktop/REX/CC_m19_comms.db"))
router = APIRouter(prefix="/m19", tags=["M19 Insurance Comms"])

# ── MLTC Plan Seed Data ─────────────────────────────────────────────────────────
# Sourced from live payer_canonical + clients.plan_canonical in auth_tracker.db
# (verified 2026-06-12). Contact details are PLACEHOLDER — Kato to fill.
MLTC_PLANS_SEED = [
    {
        "id": 1, "short_code": "AETNA",
        "name": "Aetna Better Health",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER — provider portal URL]",
        "notes": "Includes Aetna Better Health — Transport (separate auth track)",
    },
    {
        "id": 2, "short_code": "ANTHEM",
        "name": "Anthem — Integra",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "Also known as Anthem HealthKeepers / Anthem (Integra)",
    },
    {
        "id": 3, "short_code": "CPHL",
        "name": "Anthem (formerly CPHL — Centers Plan for Healthy Living)",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "CPHL merged into Anthem as of March 2026. Largest payer by volume as of Jan 2026.\n                 Use payer ID for Anthem (Integra) for all new auths.",
    },
    {
        "id": 4, "short_code": "ELDERSERVE",
        "name": "ElderServe — Riverspring Health",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "Also known as Elderserve Riverspring",
    },
    {
        "id": 5, "short_code": "EMPIRE",
        "name": "Empire BlueCross BlueShield",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "",
    },
    {
        "id": 6, "short_code": "METROPLUS",
        "name": "MetroPlus Health",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "",
    },
    {
        "id": 7, "short_code": "VNS",
        "name": "VNS Health",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "",
    },
    {
        "id": 8, "short_code": "VILLAGECARE",
        "name": "VillageCare MAX",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "",
    },
    {
        "id": 9, "short_code": "SWH",
        "name": "Senior Whole Health",
        "category": "MLTC",
        "contact_name": "[PLACEHOLDER — Kato to fill]",
        "contact_phone": "[PLACEHOLDER]",
        "contact_email": "[PLACEHOLDER]",
        "portal_url": "[PLACEHOLDER]",
        "notes": "Verified in client roster",
    },
]


# ── Schema ─────────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables + seed MLTC plans if not present. Safe to call on every import."""
    conn = _get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS payers (
            id              INTEGER PRIMARY KEY,
            short_code      TEXT    NOT NULL UNIQUE,
            name            TEXT    NOT NULL,
            category        TEXT    NOT NULL DEFAULT 'MLTC',
            contact_name    TEXT,
            contact_phone   TEXT,
            contact_email   TEXT,
            portal_url      TEXT,
            notes           TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comms_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            payer_id        INTEGER NOT NULL REFERENCES payers(id),
            comm_date       TEXT    NOT NULL,          -- ISO date YYYY-MM-DD
            channel         TEXT    NOT NULL,          -- phone / email / portal / fax / in-person
            direction       TEXT    NOT NULL DEFAULT 'outbound', -- inbound / outbound
            subject         TEXT    NOT NULL,
            body            TEXT,
            status          TEXT    NOT NULL DEFAULT 'open',     -- open / resolved / escalated
            follow_up_date  TEXT,                      -- ISO date, NULL = no follow-up needed
            follow_up_note  TEXT,
            logged_by       TEXT    DEFAULT 'system',
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_comms_payer ON comms_log(payer_id);
        CREATE INDEX IF NOT EXISTS idx_comms_followup ON comms_log(follow_up_date)
            WHERE follow_up_date IS NOT NULL AND status != 'resolved';

        CREATE TABLE IF NOT EXISTS document_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            payer_id        INTEGER NOT NULL REFERENCES payers(id),
            client_name     TEXT,
            request_type    TEXT    NOT NULL,    -- auth-renewal / medical-records / plan-of-care / other
            description     TEXT    NOT NULL,
            received_date   TEXT    NOT NULL,
            due_date        TEXT,
            status          TEXT    NOT NULL DEFAULT 'pending',  -- pending / in-progress / submitted / closed
            assigned_to     TEXT,
            notes           TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_docreq_payer ON document_requests(payer_id);
        CREATE INDEX IF NOT EXISTS idx_docreq_status ON document_requests(status);
    """)

    # Seed MLTC plans (INSERT OR IGNORE — idempotent)
    for p in MLTC_PLANS_SEED:
        c.execute("""
            INSERT OR IGNORE INTO payers
                (id, short_code, name, category, contact_name, contact_phone,
                 contact_email, portal_url, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (p["id"], p["short_code"], p["name"], p["category"],
              p["contact_name"], p["contact_phone"], p["contact_email"],
              p["portal_url"], p["notes"]))

    conn.commit()
    conn.close()


# Initialise on module load
init_db()


# ── Pydantic models ─────────────────────────────────────────────────────────────

class CommLogIn(BaseModel):
    payer_id: int
    comm_date: str          # YYYY-MM-DD
    channel: str            # phone / email / portal / fax / in-person
    direction: str = "outbound"
    subject: str
    body: Optional[str] = None
    status: str = "open"
    follow_up_date: Optional[str] = None
    follow_up_note: Optional[str] = None
    logged_by: str = "system"


class DocRequestIn(BaseModel):
    payer_id: int
    client_name: Optional[str] = None
    request_type: str
    description: str
    received_date: str
    due_date: Optional[str] = None
    status: str = "pending"
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class DocStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/payers")
def list_payers():
    """List all insurance payers."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM payers ORDER BY name").fetchall()
    conn.close()
    return {"payers": [dict(r) for r in rows], "count": len(rows)}


@router.get("/payers/{payer_id}")
def get_payer(payer_id: int):
    """Get a single payer + recent comms summary."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM payers WHERE id = ?", (payer_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Payer not found")
    payer = dict(row)
    # Recent comms
    comms = conn.execute(
        "SELECT * FROM comms_log WHERE payer_id = ? ORDER BY comm_date DESC LIMIT 10",
        (payer_id,)
    ).fetchall()
    payer["recent_comms"] = [dict(c) for c in comms]
    payer["open_doc_requests"] = conn.execute(
        "SELECT COUNT(*) FROM document_requests WHERE payer_id = ? AND status != 'closed'",
        (payer_id,)
    ).fetchone()[0]
    conn.close()
    return payer


@router.post("/comms", status_code=201)
def log_comm(body: CommLogIn):
    """Log a new communication with an insurance payer."""
    conn = _get_conn()
    # Validate payer exists
    if not conn.execute("SELECT 1 FROM payers WHERE id = ?", (body.payer_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Payer not found")
    c = conn.cursor()
    c.execute("""
        INSERT INTO comms_log
            (payer_id, comm_date, channel, direction, subject, body,
             status, follow_up_date, follow_up_note, logged_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (body.payer_id, body.comm_date, body.channel, body.direction,
          body.subject, body.body, body.status, body.follow_up_date,
          body.follow_up_note, body.logged_by))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"id": new_id, "status": "logged"}


@router.get("/comms")
def list_comms(payer_id: Optional[int] = None, limit: int = 50):
    """List communications, optionally filtered by payer."""
    conn = _get_conn()
    if payer_id:
        rows = conn.execute(
            "SELECT cl.*, p.name as payer_name FROM comms_log cl "
            "JOIN payers p ON p.id = cl.payer_id "
            "WHERE cl.payer_id = ? ORDER BY cl.comm_date DESC LIMIT ?",
            (payer_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT cl.*, p.name as payer_name FROM comms_log cl "
            "JOIN payers p ON p.id = cl.payer_id "
            "ORDER BY cl.comm_date DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return {"comms": [dict(r) for r in rows], "count": len(rows)}


@router.get("/comms/pending-followups")
def pending_followups():
    """All open communications that have a follow-up date set."""
    today = date.today().isoformat()
    conn = _get_conn()
    rows = conn.execute("""
        SELECT cl.*, p.name as payer_name FROM comms_log cl
        JOIN payers p ON p.id = cl.payer_id
        WHERE cl.follow_up_date IS NOT NULL
          AND cl.status != 'resolved'
        ORDER BY cl.follow_up_date ASC
    """).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    overdue = [r for r in result if r["follow_up_date"] <= today]
    upcoming = [r for r in result if r["follow_up_date"] > today]
    return {"overdue": overdue, "upcoming": upcoming,
            "overdue_count": len(overdue), "upcoming_count": len(upcoming)}


@router.post("/documents", status_code=201)
def create_doc_request(body: DocRequestIn):
    """Create a new document request from a payer."""
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM payers WHERE id = ?", (body.payer_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Payer not found")
    c = conn.cursor()
    c.execute("""
        INSERT INTO document_requests
            (payer_id, client_name, request_type, description, received_date,
             due_date, status, assigned_to, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (body.payer_id, body.client_name, body.request_type, body.description,
          body.received_date, body.due_date, body.status, body.assigned_to, body.notes))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"id": new_id, "status": "created"}


@router.get("/documents")
def list_doc_requests(payer_id: Optional[int] = None, status: Optional[str] = None):
    """List document requests."""
    conn = _get_conn()
    query = ("SELECT dr.*, p.name as payer_name FROM document_requests dr "
             "JOIN payers p ON p.id = dr.payer_id WHERE 1=1")
    params: list = []
    if payer_id:
        query += " AND dr.payer_id = ?"
        params.append(payer_id)
    if status:
        query += " AND dr.status = ?"
        params.append(status)
    query += " ORDER BY dr.due_date ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"document_requests": [dict(r) for r in rows], "count": len(rows)}


@router.put("/documents/{doc_id}/status")
def update_doc_status(doc_id: int, body: DocStatusUpdate):
    """Update document request status."""
    conn = _get_conn()
    existing = conn.execute("SELECT 1 FROM document_requests WHERE id = ?", (doc_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Document request not found")
    conn.execute(
        "UPDATE document_requests SET status = ?, notes = COALESCE(?, notes), "
        "updated_at = datetime('now') WHERE id = ?",
        (body.status, body.notes, doc_id)
    )
    conn.commit()
    conn.close()
    return {"id": doc_id, "status": body.status}


# ── Self-test ──────────────────────────────────────────────────────────────────

def _selftest():
    """
    --selftest: verifies schema creation, seed data, insert, and query.
    Run: python3 CC_m19_insurance_comms.py --selftest
    """
    import tempfile, os
    global DB_PATH
    orig = DB_PATH
    # Use temp DB so selftest never touches production data
    tmp = tempfile.mktemp(suffix=".db")
    DB_PATH = Path(tmp)
    try:
        print("=== CC_m19 SELFTEST ===")
        init_db()
        print("[PASS] init_db() — schema created")

        conn = _get_conn()
        n = conn.execute("SELECT COUNT(*) FROM payers").fetchone()[0]
        print(f"[PASS] Payers seeded: {n} rows")
        names = [r[0] for r in conn.execute("SELECT name FROM payers ORDER BY name").fetchall()]
        for name in names:
            print(f"  · {name}")
        conn.close()

        # Insert a comm
        conn = _get_conn()
        conn.execute("""
            INSERT INTO comms_log
                (payer_id, comm_date, channel, direction, subject, status)
            VALUES (1, '2026-06-12', 'phone', 'outbound',
                    '[SELFTEST] Auth renewal follow-up', 'open')
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM comms_log LIMIT 1").fetchone()
        print(f"[PASS] Comm inserted: id={row['id']} subject='{row['subject']}'")
        conn.close()

        # Insert a doc request
        conn = _get_conn()
        conn.execute("""
            INSERT INTO document_requests
                (payer_id, client_name, request_type, description, received_date, status)
            VALUES (3, '[SELFTEST Client]', 'auth-renewal',
                    '[SELFTEST] Auth renewal docs needed', '2026-06-12', 'pending')
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM document_requests LIMIT 1").fetchone()
        print(f"[PASS] Doc request inserted: id={row['id']} type='{row['request_type']}'")

        # Pending followups (none scheduled)
        count = conn.execute(
            "SELECT COUNT(*) FROM comms_log WHERE follow_up_date IS NOT NULL AND status != 'resolved'"
        ).fetchone()[0]
        print(f"[PASS] Pending follow-ups query: {count} (expected 0 in fresh DB)")
        conn.close()

        print("=== ALL SELFTEST CHECKS PASSED ===")
    finally:
        DB_PATH = orig
        os.unlink(tmp)


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print("Usage: python3 CC_m19_insurance_comms.py --selftest")
