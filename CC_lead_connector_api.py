#!/usr/bin/env python3
"""
CC_lead_connector_api.py
GHS Lead Connector — FastAPI CRM Backend
Port: 8002
DB:   ~/Desktop/REX/CC_lead_connector.db

Run (dev):
    source ~/debate-chamber/.venv/bin/activate
    uvicorn CC_lead_connector_api:app --host 0.0.0.0 --port 8002 --reload

Tables: contacts · pipelines · deals · activities · communications
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = os.path.expanduser("~/Desktop/REX/CC_lead_connector.db")

app = FastAPI(
    title="GHS Lead Connector",
    description="Local CRM + pipeline for Gold Health Systems (GOJ & BBG)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    for key in ("tags", "custom_fields", "stages", "metadata"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    return d


def rows_to_list(rows) -> List[Dict[str, Any]]:
    return [row_to_dict(r) for r in rows]


# ── DB init + seed ────────────────────────────────────────────────────────────

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name    TEXT    NOT NULL DEFAULT '',
            last_name     TEXT    DEFAULT '',
            phone         TEXT,
            email         TEXT,
            tags          TEXT    DEFAULT '[]',
            source        TEXT,
            pipeline_id   INTEGER,
            stage_id      TEXT,
            created_at    TEXT    DEFAULT (datetime('now')),
            notes         TEXT,
            custom_fields TEXT    DEFAULT '{}',
            business      TEXT    DEFAULT 'OTHER',
            status        TEXT    DEFAULT 'lead',
            deleted_at    TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pipelines (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            business   TEXT DEFAULT 'OTHER',
            stages     TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id  INTEGER,
            pipeline_id INTEGER,
            stage_id    TEXT,
            value       REAL    DEFAULT 0,
            title       TEXT,
            notes       TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now')),
            won_at      TEXT,
            lost_at     TEXT,
            status      TEXT    DEFAULT 'open',
            FOREIGN KEY (contact_id)  REFERENCES contacts(id),
            FOREIGN KEY (pipeline_id) REFERENCES pipelines(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id  INTEGER,
            deal_id     INTEGER,
            type        TEXT,
            content     TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            created_by  TEXT DEFAULT 'system'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS communications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id  INTEGER,
            channel     TEXT,
            direction   TEXT,
            content     TEXT,
            status      TEXT DEFAULT 'received',
            created_at  TEXT DEFAULT (datetime('now')),
            metadata    TEXT DEFAULT '{}'
        )
    """)

    conn.commit()

    # Seed default pipelines once
    c.execute("SELECT COUNT(*) FROM pipelines")
    if c.fetchone()[0] == 0:
        goj_stages = json.dumps([
            {"id": "new_lead",       "name": "New Lead",       "order": 1, "color": "#3b82f6"},
            {"id": "auth_submitted", "name": "Auth Submitted", "order": 2, "color": "#8b5cf6"},
            {"id": "auth_pending",   "name": "Auth Pending",   "order": 3, "color": "#f59e0b"},
            {"id": "auth_active",    "name": "Auth Active",    "order": 4, "color": "#0066cc"},
            {"id": "renewal_due",    "name": "Renewal Due",    "order": 5, "color": "#ef4444"},
            {"id": "expired",        "name": "Expired",        "order": 6, "color": "#6b7280"},
        ])
        bbg_stages = json.dumps([
            {"id": "inquiry",         "name": "Inquiry",         "order": 1, "color": "#f59e0b"},
            {"id": "interested",      "name": "Interested",      "order": 2, "color": "#10b981"},
            {"id": "reservation",     "name": "Reservation",     "order": 3, "color": "#3b82f6"},
            {"id": "confirmed",       "name": "Confirmed",       "order": 4, "color": "#8b5cf6"},
            {"id": "attended",        "name": "Attended",        "order": 5, "color": "#06b6d4"},
            {"id": "repeat_customer", "name": "Repeat Customer", "order": 6, "color": "#f59e0b"},
        ])
        c.execute(
            "INSERT INTO pipelines (name, business, stages) VALUES (?, ?, ?)",
            ("GOJ Authorization Pipeline", "GOJ", goj_stages),
        )
        c.execute(
            "INSERT INTO pipelines (name, business, stages) VALUES (?, ?, ?)",
            ("BBG Events Pipeline", "BBG", bbg_stages),
        )
        conn.commit()

    conn.close()


@app.on_event("startup")
async def startup_event():
    init_db()


# ── Pydantic models ───────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    first_name:    str
    last_name:     Optional[str]  = ""
    phone:         Optional[str]  = None
    email:         Optional[str]  = None
    tags:          Optional[List[str]] = []
    source:        Optional[str]  = None
    pipeline_id:   Optional[int]  = None
    stage_id:      Optional[str]  = None
    notes:         Optional[str]  = None
    custom_fields: Optional[Dict[str, Any]] = {}
    business:      str = "OTHER"   # GOJ | BBG | OTHER
    status:        str = "lead"    # lead | active | closed | lost


class ContactUpdate(BaseModel):
    first_name:    Optional[str]  = None
    last_name:     Optional[str]  = None
    phone:         Optional[str]  = None
    email:         Optional[str]  = None
    tags:          Optional[List[str]] = None
    source:        Optional[str]  = None
    pipeline_id:   Optional[int]  = None
    stage_id:      Optional[str]  = None
    notes:         Optional[str]  = None
    custom_fields: Optional[Dict[str, Any]] = None
    business:      Optional[str]  = None
    status:        Optional[str]  = None


class NoteCreate(BaseModel):
    content:    str
    created_by: Optional[str] = "Kato"


class PipelineCreate(BaseModel):
    name:     str
    business: Optional[str] = "OTHER"
    stages:   List[Dict[str, Any]]


class DealCreate(BaseModel):
    contact_id:  int
    pipeline_id: int
    stage_id:    str
    value:       Optional[float] = 0
    title:       str
    notes:       Optional[str] = None


class DealUpdate(BaseModel):
    stage_id: Optional[str]   = None
    value:    Optional[float] = None
    title:    Optional[str]   = None
    notes:    Optional[str]   = None
    status:   Optional[str]   = None


class DealMove(BaseModel):
    stage_id: str
    notes:    Optional[str] = None


class InboundComm(BaseModel):
    channel:      str              # sms | email | voice | instagram_dm | telegram
    from_number:  Optional[str] = None
    from_email:   Optional[str] = None
    content:      str
    metadata:     Optional[Dict[str, Any]] = {}


# ── Contacts ──────────────────────────────────────────────────────────────────

@app.get("/contacts", summary="List contacts")
def list_contacts(
    search:      Optional[str] = Query(None, description="Full-text search across name/phone/email"),
    business:    Optional[str] = Query(None, description="GOJ | BBG | OTHER"),
    status:      Optional[str] = Query(None),
    tag:         Optional[str] = Query(None),
    pipeline_id: Optional[int] = Query(None),
    stage_id:    Optional[str] = Query(None),
    limit:       int = Query(50, ge=1, le=500),
    offset:      int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    where = "WHERE deleted_at IS NULL"
    params: List[Any] = []

    if search:
        where += " AND (first_name LIKE ? OR last_name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        s = f"%{search}%"
        params += [s, s, s, s]
    if business:
        where += " AND business = ?"
        params.append(business)
    if status:
        where += " AND status = ?"
        params.append(status)
    if pipeline_id:
        where += " AND pipeline_id = ?"
        params.append(pipeline_id)
    if stage_id:
        where += " AND stage_id = ?"
        params.append(stage_id)
    if tag:
        where += " AND tags LIKE ?"
        params.append(f'%"{tag}"%')

    total = db.execute(f"SELECT COUNT(*) FROM contacts {where}", params).fetchone()[0]
    rows  = db.execute(
        f"SELECT * FROM contacts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return {"contacts": rows_to_list(rows), "total": total, "limit": limit, "offset": offset}


@app.post("/contacts", status_code=201, summary="Create contact")
def create_contact(data: ContactCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        """INSERT INTO contacts
           (first_name, last_name, phone, email, tags, source,
            pipeline_id, stage_id, notes, custom_fields, business, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.first_name, data.last_name or "",
            data.phone, data.email,
            json.dumps(data.tags or []),
            data.source,
            data.pipeline_id, data.stage_id,
            data.notes,
            json.dumps(data.custom_fields or {}),
            data.business, data.status,
        ),
    )
    db.commit()
    cid = cur.lastrowid
    db.execute(
        "INSERT INTO activities (contact_id, type, content, created_by) VALUES (?, 'note', ?, 'system')",
        (cid, f"Contact created. Source: {data.source or 'Manual entry'}."),
    )
    db.commit()
    return row_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone())


@app.get("/contacts/{contact_id}", summary="Get contact")
def get_contact(contact_id: int, db: sqlite3.Connection = Depends(get_db)):
    contact = row_to_dict(
        db.execute("SELECT * FROM contacts WHERE id = ? AND deleted_at IS NULL", (contact_id,)).fetchone()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@app.put("/contacts/{contact_id}", summary="Update contact")
def update_contact(contact_id: int, data: ContactUpdate, db: sqlite3.Connection = Depends(get_db)):
    if not db.execute(
        "SELECT id FROM contacts WHERE id = ? AND deleted_at IS NULL", (contact_id,)
    ).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")

    updates: Dict[str, Any] = {}
    if data.first_name    is not None: updates["first_name"]    = data.first_name
    if data.last_name     is not None: updates["last_name"]     = data.last_name
    if data.phone         is not None: updates["phone"]         = data.phone
    if data.email         is not None: updates["email"]         = data.email
    if data.tags          is not None: updates["tags"]          = json.dumps(data.tags)
    if data.source        is not None: updates["source"]        = data.source
    if data.pipeline_id   is not None: updates["pipeline_id"]   = data.pipeline_id
    if data.stage_id      is not None: updates["stage_id"]      = data.stage_id
    if data.notes         is not None: updates["notes"]         = data.notes
    if data.custom_fields is not None: updates["custom_fields"] = json.dumps(data.custom_fields)
    if data.business      is not None: updates["business"]      = data.business
    if data.status        is not None: updates["status"]        = data.status

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = ?",
            list(updates.values()) + [contact_id],
        )
        db.commit()

    return row_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())


@app.delete("/contacts/{contact_id}", summary="Soft-delete contact")
def delete_contact(contact_id: int, db: sqlite3.Connection = Depends(get_db)):
    if not db.execute(
        "SELECT id FROM contacts WHERE id = ? AND deleted_at IS NULL", (contact_id,)
    ).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")
    db.execute(
        "UPDATE contacts SET deleted_at = datetime('now') WHERE id = ?", (contact_id,)
    )
    db.commit()
    return {"deleted": True, "id": contact_id}


@app.get("/contacts/{contact_id}/timeline", summary="Full activity + comms timeline")
def get_timeline(contact_id: int, db: sqlite3.Connection = Depends(get_db)):
    if not db.execute(
        "SELECT id FROM contacts WHERE id = ? AND deleted_at IS NULL", (contact_id,)
    ).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")

    activities = rows_to_list(db.execute(
        "SELECT *, 'activity' AS record_type FROM activities WHERE contact_id = ?",
        (contact_id,),
    ).fetchall())

    comms = rows_to_list(db.execute(
        "SELECT *, 'communication' AS record_type FROM communications WHERE contact_id = ?",
        (contact_id,),
    ).fetchall())

    timeline = activities + comms
    timeline.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"timeline": timeline, "contact_id": contact_id}


@app.post("/contacts/{contact_id}/note", summary="Add note to contact")
def add_note(contact_id: int, data: NoteCreate, db: sqlite3.Connection = Depends(get_db)):
    if not db.execute(
        "SELECT id FROM contacts WHERE id = ? AND deleted_at IS NULL", (contact_id,)
    ).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")
    cur = db.execute(
        "INSERT INTO activities (contact_id, type, content, created_by) VALUES (?, 'note', ?, ?)",
        (contact_id, data.content, data.created_by or "Kato"),
    )
    db.commit()
    return row_to_dict(db.execute("SELECT * FROM activities WHERE id = ?", (cur.lastrowid,)).fetchone())


@app.post("/contacts/import/goj", summary="Import GOJ clients into Lead Connector")
def import_goj_contacts(db: sqlite3.Connection = Depends(get_db)):
    """
    Read-only pull from auth_tracker.db → creates copies in LC contacts.
    Safe to run repeatedly — skips duplicates by first_name + last_name + business=GOJ.
    """
    goj_db = os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db")
    if not os.path.exists(goj_db):
        raise HTTPException(status_code=404, detail=f"GOJ database not found at {goj_db}")

    goj_conn = sqlite3.connect(goj_db)
    goj_conn.row_factory = sqlite3.Row

    pipeline = db.execute("SELECT id FROM pipelines WHERE business = 'GOJ' LIMIT 1").fetchone()
    pipeline_id = pipeline["id"] if pipeline else None

    STATUS_TO_STAGE = {
        "ACTIVE":          "auth_active",
        "PENDING RENEWAL": "auth_pending",
        "EXPIRED":         "expired",
    }

    try:
        clients = goj_conn.execute("""
            SELECT c.id   AS goj_id,
                   c.first_name,
                   c.last_name,
                   c.phone,
                   c.medicaid_id,
                   a.status           AS auth_status,
                   a.service_end_date AS service_end_date
            FROM clients c
            LEFT JOIN authorization a ON a.client_id = c.id
            WHERE (c.deleted_at IS NULL OR c.deleted_at = '')
        """).fetchall()
    except Exception as e:
        goj_conn.close()
        raise HTTPException(status_code=500, detail=f"GOJ DB read error: {e}")

    imported = skipped = 0

    for client in clients:
        exists = db.execute(
            "SELECT id FROM contacts WHERE first_name = ? AND last_name = ? AND business = 'GOJ' AND deleted_at IS NULL",
            (client["first_name"] or "", client["last_name"] or ""),
        ).fetchone()
        if exists:
            skipped += 1
            continue

        stage_id       = STATUS_TO_STAGE.get(client["auth_status"] or "", "new_lead")
        contact_status = "active" if client["auth_status"] == "ACTIVE" else "lead"

        cur = db.execute(
            """INSERT INTO contacts
               (first_name, last_name, phone, tags, source,
                pipeline_id, stage_id, business, status, custom_fields)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'GOJ', ?, ?)""",
            (
                client["first_name"] or "",
                client["last_name"]  or "",
                client["phone"]      or None,
                json.dumps(["goj_client"]),
                "GOJ Import",
                pipeline_id,
                stage_id,
                contact_status,
                json.dumps({
                    "goj_client_id":    client["goj_id"],
                    "medicaid_id":      client["medicaid_id"],
                    "auth_status":      client["auth_status"],
                    "service_end_date": client["service_end_date"],
                }),
            ),
        )
        cid = cur.lastrowid
        db.execute(
            "INSERT INTO activities (contact_id, type, content, created_by) VALUES (?, 'note', ?, 'system')",
            (cid, f"Imported from GOJ DB. Auth: {client['auth_status']}. Expires: {client['service_end_date']}."),
        )
        imported += 1

    db.commit()
    goj_conn.close()
    return {"imported": imported, "skipped": skipped, "total": imported + skipped}


# ── Pipelines ─────────────────────────────────────────────────────────────────

@app.get("/pipelines", summary="List all pipelines")
def list_pipelines(db: sqlite3.Connection = Depends(get_db)):
    pipelines = rows_to_list(db.execute("SELECT * FROM pipelines ORDER BY id").fetchall())
    for pipeline in pipelines:
        for stage in pipeline.get("stages") or []:
            stage["deal_count"] = db.execute(
                "SELECT COUNT(*) FROM deals WHERE pipeline_id = ? AND stage_id = ? AND status = 'open'",
                (pipeline["id"], stage["id"]),
            ).fetchone()[0]
    return {"pipelines": pipelines}


@app.post("/pipelines", status_code=201, summary="Create pipeline")
def create_pipeline(data: PipelineCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO pipelines (name, business, stages) VALUES (?, ?, ?)",
        (data.name, data.business, json.dumps(data.stages)),
    )
    db.commit()
    return row_to_dict(db.execute("SELECT * FROM pipelines WHERE id = ?", (cur.lastrowid,)).fetchone())


@app.get("/pipelines/{pipeline_id}/board", summary="Kanban board data")
def get_pipeline_board(pipeline_id: int, db: sqlite3.Connection = Depends(get_db)):
    pipeline = row_to_dict(db.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone())
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    columns = []
    for stage in pipeline.get("stages") or []:
        deals = rows_to_list(db.execute(
            """SELECT d.*, c.first_name, c.last_name, c.phone, c.email, c.business
               FROM deals d
               JOIN contacts c ON d.contact_id = c.id
               WHERE d.pipeline_id = ? AND d.stage_id = ? AND d.status = 'open'
               ORDER BY d.updated_at DESC""",
            (pipeline_id, stage["id"]),
        ).fetchall())
        columns.append({
            "stage":       stage,
            "deals":       deals,
            "total_value": sum(d.get("value") or 0 for d in deals),
            "count":       len(deals),
        })

    return {"pipeline": pipeline, "columns": columns}


# ── Deals ─────────────────────────────────────────────────────────────────────

@app.get("/deals", summary="List deals")
def list_deals(
    pipeline_id: Optional[int] = None,
    contact_id:  Optional[int] = None,
    status:      Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
):
    query  = "SELECT d.*, c.first_name, c.last_name FROM deals d JOIN contacts c ON d.contact_id = c.id WHERE 1=1"
    params: List[Any] = []
    if pipeline_id:
        query += " AND d.pipeline_id = ?"; params.append(pipeline_id)
    if contact_id:
        query += " AND d.contact_id = ?";  params.append(contact_id)
    if status:
        query += " AND d.status = ?";      params.append(status)
    query += " ORDER BY d.updated_at DESC"
    return {"deals": rows_to_list(db.execute(query, params).fetchall())}


@app.post("/deals", status_code=201, summary="Create deal")
def create_deal(data: DealCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO deals (contact_id, pipeline_id, stage_id, value, title, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (data.contact_id, data.pipeline_id, data.stage_id, data.value, data.title, data.notes),
    )
    db.commit()
    did = cur.lastrowid
    db.execute(
        "INSERT INTO activities (contact_id, deal_id, type, content, created_by) VALUES (?, ?, 'stage_change', ?, 'system')",
        (data.contact_id, did, f"Deal created: '{data.title}'. Stage: {data.stage_id}."),
    )
    db.commit()
    return row_to_dict(db.execute("SELECT * FROM deals WHERE id = ?", (did,)).fetchone())


@app.get("/deals/{deal_id}", summary="Get deal")
def get_deal(deal_id: int, db: sqlite3.Connection = Depends(get_db)):
    deal = row_to_dict(db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone())
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@app.put("/deals/{deal_id}", summary="Update deal")
def update_deal(deal_id: int, data: DealUpdate, db: sqlite3.Connection = Depends(get_db)):
    deal = row_to_dict(db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone())
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    updates: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
    if data.stage_id is not None: updates["stage_id"] = data.stage_id
    if data.value    is not None: updates["value"]    = data.value
    if data.title    is not None: updates["title"]    = data.title
    if data.notes    is not None: updates["notes"]    = data.notes
    if data.status   is not None: updates["status"]   = data.status
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE deals SET {set_clause} WHERE id = ?", list(updates.values()) + [deal_id])
    db.commit()
    return row_to_dict(db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone())


@app.post("/deals/{deal_id}/move", summary="Move deal to new stage")
def move_deal(deal_id: int, data: DealMove, db: sqlite3.Connection = Depends(get_db)):
    deal = row_to_dict(db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone())
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    old_stage = deal["stage_id"]
    now       = datetime.utcnow().isoformat()

    updates: Dict[str, Any] = {"stage_id": data.stage_id, "updated_at": now}
    terminal = {"won": ("won_at", "won"), "lost": ("lost_at", "lost")}
    if data.stage_id in terminal:
        ts_col, new_status = terminal[data.stage_id]
        updates[ts_col]   = now
        updates["status"] = new_status

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE deals SET {set_clause} WHERE id = ?", list(updates.values()) + [deal_id])

    note_suffix = f" — {data.notes}" if data.notes else ""
    db.execute(
        "INSERT INTO activities (contact_id, deal_id, type, content, created_by) VALUES (?, ?, 'stage_change', ?, 'system')",
        (deal["contact_id"], deal_id, f"Moved '{old_stage}' → '{data.stage_id}'.{note_suffix}"),
    )
    db.commit()
    return row_to_dict(db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone())


# ── Communications ────────────────────────────────────────────────────────────

@app.post("/communications/inbound", summary="Inbound webhook (Masha, SMS, IG DM, Telegram)")
def inbound_communication(data: InboundComm, db: sqlite3.Connection = Depends(get_db)):
    contact_id: Optional[int] = None

    # Lookup or auto-create contact
    if data.from_number:
        row = db.execute(
            "SELECT id FROM contacts WHERE phone = ? AND deleted_at IS NULL", (data.from_number,)
        ).fetchone()
        if row:
            contact_id = row["id"]
        else:
            cur = db.execute(
                "INSERT INTO contacts (first_name, phone, tags, source, business, status) VALUES ('Unknown', ?, ?, ?, 'OTHER', 'lead')",
                (data.from_number, json.dumps([data.channel]), f"{data.channel} inbound"),
            )
            db.commit()
            contact_id = cur.lastrowid

    elif data.from_email:
        row = db.execute(
            "SELECT id FROM contacts WHERE email = ? AND deleted_at IS NULL", (data.from_email,)
        ).fetchone()
        if row:
            contact_id = row["id"]
        else:
            cur = db.execute(
                "INSERT INTO contacts (first_name, email, tags, source, business, status) VALUES ('Unknown', ?, ?, ?, 'OTHER', 'lead')",
                (data.from_email, json.dumps([data.channel]), f"{data.channel} inbound"),
            )
            db.commit()
            contact_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO communications (contact_id, channel, direction, content, status, metadata) VALUES (?, ?, 'inbound', ?, 'received', ?)",
        (contact_id, data.channel, data.content, json.dumps(data.metadata or {})),
    )
    db.commit()
    comm_id = cur.lastrowid

    if contact_id:
        db.execute(
            "INSERT INTO activities (contact_id, type, content, created_by) VALUES (?, ?, ?, 'system')",
            (contact_id, data.channel, f"Inbound {data.channel}: {data.content[:300]}"),
        )
        db.commit()

    return {"communication_id": comm_id, "contact_id": contact_id, "status": "received"}


@app.get("/communications", summary="List communications")
def list_communications(
    contact_id: Optional[int] = None,
    channel:    Optional[str] = None,
    limit:      int = Query(50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
):
    q = """SELECT cm.*, c.first_name, c.last_name
           FROM communications cm
           LEFT JOIN contacts c ON cm.contact_id = c.id
           WHERE 1=1"""
    p: List[Any] = []
    if contact_id:
        q += " AND cm.contact_id = ?"; p.append(contact_id)
    if channel:
        q += " AND cm.channel = ?";    p.append(channel)
    q += " ORDER BY cm.created_at DESC LIMIT ?"
    p.append(limit)
    return {"communications": rows_to_list(db.execute(q, p).fetchall())}


# ── Outbound SMS (Twilio) — the texting GoHighLevel used to do ─────────────────
import urllib.request as _urlreq
import urllib.parse as _urlparse
import base64 as _b64
from pathlib import Path as _Path

def _hermes_env(key: str, default: str = "") -> str:
    v = os.environ.get(key, "")
    if v:
        return v
    for p in (_Path.home() / ".hermes/.env", _Path.home() / ".hermes-cloud/.env"):
        try:
            for line in p.read_text().splitlines():
                s = line.strip()
                if s.startswith(f"{key}=") and not s.startswith("#"):
                    return s.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
    return default

def _twilio_send_sms(to: str, body: str) -> dict:
    sid = _hermes_env("TWILIO_ACCOUNT_SID")
    tok = _hermes_env("TWILIO_AUTH_TOKEN")
    frm = _hermes_env("TWILIO_NUMBER") or "+18777682887"
    if not (sid and tok and frm):
        raise HTTPException(status_code=503, detail="Twilio not configured (SID/token/number)")
    payload = _urlparse.urlencode({"To": to, "From": frm, "Body": body}).encode()
    auth = _b64.b64encode(f"{sid}:{tok}".encode()).decode()
    req = _urlreq.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=payload,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with _urlreq.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

class SendSMS(BaseModel):
    to: str
    body: str
    contact_id: Optional[int] = None

@app.post("/communications/send", summary="Send outbound SMS via Twilio + log it")
def send_communication(data: SendSMS, db: sqlite3.Connection = Depends(get_db)):
    to = (data.to or "").strip()
    if not to or not data.body:
        raise HTTPException(status_code=400, detail="to and body required")
    try:
        res = _twilio_send_sms(to, data.body)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Twilio send failed: {e}")
    msg_sid = res.get("sid")
    status = res.get("status", "queued")
    cid = data.contact_id
    if cid is None:
        row = db.execute("SELECT id FROM contacts WHERE phone = ? AND deleted_at IS NULL", (to,)).fetchone()
        cid = row["id"] if row else None
    db.execute(
        "INSERT INTO communications (contact_id, channel, direction, content, status, metadata) "
        "VALUES (?, 'sms', 'outbound', ?, ?, ?)",
        (cid, data.body, status, json.dumps({"twilio_sid": msg_sid, "to": to})),
    )
    if cid:
        db.execute(
            "INSERT INTO activities (contact_id, type, content, created_by) VALUES (?, 'sms', ?, 'system')",
            (cid, f"Sent SMS: {data.body[:300]}"),
        )
    db.commit()
    return {"ok": True, "twilio_sid": msg_sid, "status": status, "contact_id": cid}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard/stats", summary="Aggregate dashboard statistics")
def dashboard_stats(db: sqlite3.Connection = Depends(get_db)):
    def count(q, p=()):
        return db.execute(q, p).fetchone()[0]

    total_contacts  = count("SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL")
    active_contacts = count("SELECT COUNT(*) FROM contacts WHERE status = 'active' AND deleted_at IS NULL")
    goj_contacts    = count("SELECT COUNT(*) FROM contacts WHERE business = 'GOJ' AND deleted_at IS NULL")
    bbg_contacts    = count("SELECT COUNT(*) FROM contacts WHERE business = 'BBG' AND deleted_at IS NULL")

    pipeline_value = db.execute(
        "SELECT COALESCE(SUM(value),0) FROM deals WHERE status = 'open'"
    ).fetchone()[0]
    open_deals = count("SELECT COUNT(*) FROM deals WHERE status = 'open'")
    won_deals  = count("SELECT COUNT(*) FROM deals WHERE status = 'won'")
    lost_deals = count("SELECT COUNT(*) FROM deals WHERE status = 'lost'")
    total_closed   = won_deals + lost_deals
    conversion_rate = round(won_deals / total_closed * 100, 1) if total_closed else 0

    today = datetime.utcnow().date().isoformat()
    todays_comms = count("SELECT COUNT(*) FROM communications WHERE created_at LIKE ?", (f"{today}%",))

    recent_activities = rows_to_list(db.execute(
        """SELECT a.*, c.first_name, c.last_name
           FROM activities a
           LEFT JOIN contacts c ON a.contact_id = c.id
           ORDER BY a.created_at DESC LIMIT 10"""
    ).fetchall())

    # GOJ stage breakdown
    goj_pipeline = db.execute("SELECT id FROM pipelines WHERE business = 'GOJ' LIMIT 1").fetchone()
    stage_breakdown = []
    if goj_pipeline:
        pl = row_to_dict(db.execute("SELECT * FROM pipelines WHERE id = ?", (goj_pipeline["id"],)).fetchone())
        for stage in pl.get("stages") or []:
            n = count(
                "SELECT COUNT(*) FROM contacts WHERE pipeline_id = ? AND stage_id = ? AND deleted_at IS NULL",
                (goj_pipeline["id"], stage["id"]),
            )
            stage_breakdown.append({"stage": stage["name"], "count": n, "color": stage["color"]})

    return {
        "total_contacts":        total_contacts,
        "active_contacts":       active_contacts,
        "goj_contacts":          goj_contacts,
        "bbg_contacts":          bbg_contacts,
        "total_pipeline_value":  pipeline_value,
        "open_deals":            open_deals,
        "won_deals":             won_deals,
        "lost_deals":            lost_deals,
        "conversion_rate":       conversion_rate,
        "todays_communications": todays_comms,
        "recent_activities":     recent_activities,
        "goj_stage_breakdown":   stage_breakdown,
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check")
def health():
    return {"status": "ok", "service": "GHS Lead Connector", "version": "1.0.0", "port": 8002}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("CC_lead_connector_api:app", host="0.0.0.0", port=8002, reload=True)
