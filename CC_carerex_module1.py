"""
CC_carerex_module1.py — CareRex Phase 21: Scheduling Engine
Gold Health Systems · Garden of Joy · Built: 2026-06-04

Module 1 of 6: Atomic 7-table schedule cascade.
When a client changes day or calls sick, all 7 tables update or none:
  Calendar → Attendance → Driver list → Kitchen list →
  Distribution logs → Sign-in sheets → Client menu

HARD RULE: Larry never appears on any driver list. Enforced at DB write.

Integrates with auth_tracker.db (read) and carerex.db (write).
FastAPI router — mount into REX backend via:
  from CC_carerex_module1 import router as carerex_router
  app.include_router(carerex_router, prefix="/api/carerex")

Or run standalone:
  uvicorn CC_carerex_module1:app --port 8002
"""

import sqlite3
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, APIRouter, HTTPException, Body
from pydantic import BaseModel, field_validator

# ── Paths ─────────────────────────────────────────────────────────────────────
AUTH_DB   = str(Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db")
CAREREX_DB = str(Path.home() / "Desktop" / "REX" / "carerex.db")

# ── Forbidden driver list ──────────────────────────────────────────────────────
# Larry never appears on any transport or driver list — not in any context,
# not under any instruction. This is enforced at the DB write level.
FORBIDDEN_DRIVERS = {"larry"}

# ── FastAPI setup ──────────────────────────────────────────────────────────────
app = FastAPI(title="CareRex Module 1 — Scheduling Engine", version="1.0.0")
router = APIRouter()


# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
-- CareRex Module 1 tables.
-- All writes go through cascade_schedule_change() — never direct inserts.

CREATE TABLE IF NOT EXISTS cr_calendar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL,
    service_date    TEXT NOT NULL,          -- YYYY-MM-DD
    day_of_week     TEXT NOT NULL,          -- Mon/Tue/Wed/Thu/Fri/Sat
    status          TEXT NOT NULL DEFAULT 'SCHEDULED',
                                            -- SCHEDULED | SICK | CANCELLED | MAKEUP
    note            TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client_id, service_date)
);

CREATE TABLE IF NOT EXISTS cr_attendance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL,
    service_date    TEXT NOT NULL,
    scheduled       INTEGER NOT NULL DEFAULT 1,
    present         INTEGER,                -- NULL until day-of
    arrival_time    TEXT,
    departure_time  TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client_id, service_date)
);

CREATE TABLE IF NOT EXISTS cr_driver_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_date    TEXT NOT NULL,
    driver_name     TEXT NOT NULL,
    client_id       INTEGER NOT NULL,
    pickup_order    INTEGER NOT NULL,
    address         TEXT,
    pickup_window   TEXT,                   -- e.g. "8:00-8:30"
    active          INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(service_date, driver_name, client_id)
);

CREATE TABLE IF NOT EXISTS cr_kitchen_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_date    TEXT NOT NULL,
    client_id       INTEGER NOT NULL,
    meal_type       TEXT NOT NULL DEFAULT 'standard',
    dietary_notes   TEXT,
    active          INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(service_date, client_id)
);

CREATE TABLE IF NOT EXISTS cr_distribution_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_date    TEXT NOT NULL,
    client_id       INTEGER NOT NULL,
    item_type       TEXT NOT NULL,          -- meal | snack | supplement
    quantity        INTEGER NOT NULL DEFAULT 1,
    distributed     INTEGER,                -- NULL until day-of
    active          INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cr_signin_sheets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_date    TEXT NOT NULL,
    client_id       INTEGER NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    signed_in       INTEGER,
    signed_in_time  TEXT,
    signed_out      INTEGER,
    signed_out_time TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(service_date, client_id)
);

CREATE TABLE IF NOT EXISTS cr_cascade_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cascade_id      TEXT NOT NULL,          -- UUID-ish
    client_id       INTEGER NOT NULL,
    service_date    TEXT NOT NULL,
    action          TEXT NOT NULL,          -- SCHEDULE | SICK | CANCEL | MAKEUP
    tables_updated  TEXT NOT NULL,          -- JSON array
    triggered_by    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cr_calendar_date    ON cr_calendar(service_date);
CREATE INDEX IF NOT EXISTS idx_cr_attendance_date  ON cr_attendance(service_date);
CREATE INDEX IF NOT EXISTS idx_cr_driver_date      ON cr_driver_list(service_date);
CREATE INDEX IF NOT EXISTS idx_cr_kitchen_date     ON cr_kitchen_list(service_date);
CREATE INDEX IF NOT EXISTS idx_cr_signin_date      ON cr_signin_sheets(service_date);
"""


# ── DB helpers ─────────────────────────────────────────────────────────────────

def init_carerex_db() -> None:
    """Create CareRex tables if they don't exist."""
    os.makedirs(os.path.dirname(CAREREX_DB), exist_ok=True)
    with sqlite3.connect(CAREREX_DB) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def carerex_conn():
    """WAL-mode connection to carerex.db with foreign-key enforcement."""
    conn = sqlite3.connect(CAREREX_DB)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def get_client_info(client_id: int) -> dict:
    """Pull name + address from auth_tracker.db."""
    if not os.path.exists(AUTH_DB):
        return {"name": f"Client {client_id}", "address": ""}
    with sqlite3.connect(AUTH_DB) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT full_name, address FROM clients WHERE id=?", (client_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Client {client_id} not found in auth_tracker.db")
    return dict(row)


def get_client_menu(client_id: int, week_start: str) -> str:
    """Return meal selection from auth_tracker.db client_menus table."""
    if not os.path.exists(AUTH_DB):
        return "standard"
    with sqlite3.connect(AUTH_DB) as conn:
        row = conn.execute(
            "SELECT main FROM client_menus WHERE client_id=? AND week_start=?",
            (client_id, week_start),
        ).fetchone()
    return row[0] if row else "standard"


def _guard_driver(driver_name: str) -> None:
    """Hard block: Larry never appears on any driver list."""
    if driver_name.strip().lower() in FORBIDDEN_DRIVERS:
        raise HTTPException(
            400,
            "That driver name cannot appear on any transport list. "
            "Assign a different driver."
        )


# ── Core: atomic 7-table cascade ───────────────────────────────────────────────

def _week_start_for(service_date: str) -> str:
    """Return Monday of the week containing service_date (YYYY-MM-DD)."""
    d = date.fromisoformat(service_date)
    return (d - timedelta(days=d.weekday())).isoformat()


def cascade_schedule_change(
    conn: sqlite3.Connection,
    client_id: int,
    service_date: str,
    action: str,              # SCHEDULE | SICK | CANCEL | MAKEUP
    driver_name: Optional[str] = None,
    pickup_order: Optional[int] = None,
    pickup_window: Optional[str] = None,
    meal_type: str = "standard",
    triggered_by: str = "system",
    cascade_id: Optional[str] = None,
) -> list[str]:
    """
    Single transaction across all 7 CareRex tables.
    Returns list of table names updated.
    All 7 update or none — caller must manage the transaction.
    """
    if driver_name:
        _guard_driver(driver_name)

    if cascade_id is None:
        cascade_id = f"CRX-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{client_id}"

    d = date.fromisoformat(service_date)
    dow = d.strftime("%a")  # Mon/Tue/Wed/Thu/Fri/Sat
    active = 1 if action in ("SCHEDULE", "MAKEUP") else 0
    week_start = _week_start_for(service_date)

    updated = []

    # 1. Calendar
    conn.execute("""
        INSERT INTO cr_calendar (client_id, service_date, day_of_week, status, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(client_id, service_date) DO UPDATE SET
            status=excluded.status,
            day_of_week=excluded.day_of_week,
            updated_at=datetime('now')
    """, (client_id, service_date, dow, action))
    updated.append("cr_calendar")

    # 2. Attendance
    conn.execute("""
        INSERT INTO cr_attendance (client_id, service_date, scheduled, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(client_id, service_date) DO UPDATE SET
            scheduled=excluded.scheduled,
            updated_at=datetime('now')
    """, (client_id, service_date, active))
    updated.append("cr_attendance")

    # 3. Driver list
    if driver_name and active:
        _guard_driver(driver_name)  # double-check inside transaction
        conn.execute("""
            INSERT INTO cr_driver_list
                (service_date, driver_name, client_id, pickup_order, pickup_window, active, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, datetime('now'))
            ON CONFLICT(service_date, driver_name, client_id) DO UPDATE SET
                pickup_order=excluded.pickup_order,
                pickup_window=excluded.pickup_window,
                active=1,
                updated_at=datetime('now')
        """, (service_date, driver_name, client_id, pickup_order or 99, pickup_window))
    else:
        # Mark inactive if cancelling/sick
        conn.execute("""
            UPDATE cr_driver_list
            SET active=0, updated_at=datetime('now')
            WHERE service_date=? AND client_id=?
        """, (service_date, client_id))
    updated.append("cr_driver_list")

    # 4. Kitchen list
    conn.execute("""
        INSERT INTO cr_kitchen_list (service_date, client_id, meal_type, active, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(service_date, client_id) DO UPDATE SET
            meal_type=excluded.meal_type,
            active=excluded.active,
            updated_at=datetime('now')
    """, (service_date, client_id, meal_type, active))
    updated.append("cr_kitchen_list")

    # 5. Distribution logs
    if active:
        # Ensure entries exist for meal + snack
        for item in ("meal", "snack"):
            conn.execute("""
                INSERT OR IGNORE INTO cr_distribution_logs
                    (service_date, client_id, item_type, active, updated_at)
                VALUES (?, ?, ?, 1, datetime('now'))
            """, (service_date, client_id, item))
    else:
        conn.execute("""
            UPDATE cr_distribution_logs
            SET active=0, updated_at=datetime('now')
            WHERE service_date=? AND client_id=?
        """, (service_date, client_id))
    updated.append("cr_distribution_logs")

    # 6. Sign-in sheets
    conn.execute("""
        INSERT INTO cr_signin_sheets (service_date, client_id, active, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(service_date, client_id) DO UPDATE SET
            active=excluded.active,
            updated_at=datetime('now')
    """, (service_date, client_id, active))
    updated.append("cr_signin_sheets")

    # 7. Client menu (read from auth_tracker.db, logged here)
    # Menu data lives in auth_tracker.db client_menus — we tag it in kitchen_list.meal_type
    menu_selection = get_client_menu(client_id, week_start)
    if menu_selection != meal_type:
        conn.execute("""
            UPDATE cr_kitchen_list
            SET meal_type=?, updated_at=datetime('now')
            WHERE service_date=? AND client_id=?
        """, (menu_selection, service_date, client_id))
    updated.append("client_menus(auth_tracker.db)")

    # Audit trail
    import json as _json
    conn.execute("""
        INSERT INTO cr_cascade_audit
            (cascade_id, client_id, service_date, action, tables_updated, triggered_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cascade_id, client_id, service_date, action,
          _json.dumps(updated), triggered_by))

    return updated


# ── Pydantic models ────────────────────────────────────────────────────────────

class ScheduleChangeRequest(BaseModel):
    client_id: int
    service_date: str           # YYYY-MM-DD
    action: str                 # SCHEDULE | SICK | CANCEL | MAKEUP
    driver_name: Optional[str] = None
    pickup_order: Optional[int] = None
    pickup_window: Optional[str] = None
    meal_type: str = "standard"
    triggered_by: str = "api"

    @field_validator("service_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        date.fromisoformat(v)  # raises ValueError if invalid
        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("SCHEDULE", "SICK", "CANCEL", "MAKEUP"):
            raise ValueError("action must be SCHEDULE | SICK | CANCEL | MAKEUP")
        return v


class BulkScheduleRequest(BaseModel):
    changes: list[ScheduleChangeRequest]


# ── API endpoints ──────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {
        "service": "CareRex Module 1 — Scheduling Engine",
        "status": "ok",
        "carerex_db": CAREREX_DB,
        "auth_tracker_db": AUTH_DB,
        "auth_tracker_exists": os.path.exists(AUTH_DB),
    }


@router.post("/schedule/change")
def schedule_change(req: ScheduleChangeRequest):
    """
    Atomic 7-table schedule change.
    Single client, single date.
    All 7 tables update or none.
    """
    if req.driver_name:
        _guard_driver(req.driver_name)

    with carerex_conn() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            tables = cascade_schedule_change(
                conn=conn,
                client_id=req.client_id,
                service_date=req.service_date,
                action=req.action,
                driver_name=req.driver_name,
                pickup_order=req.pickup_order,
                pickup_window=req.pickup_window,
                meal_type=req.meal_type,
                triggered_by=req.triggered_by,
            )
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, f"Cascade failed, rolled back: {e}")

    return {
        "ok": True,
        "cascade_id": f"CRX-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{req.client_id}",
        "client_id": req.client_id,
        "service_date": req.service_date,
        "action": req.action,
        "tables_updated": tables,
    }


@router.post("/schedule/bulk")
def bulk_schedule_change(req: BulkScheduleRequest):
    """
    Bulk atomic change — all clients in one transaction.
    Used for day-wide updates (e.g., 'Monday clients calling sick').
    All-or-nothing across all changes.
    """
    # Pre-validate all driver names before touching DB
    for change in req.changes:
        if change.driver_name:
            _guard_driver(change.driver_name)

    results = []
    with carerex_conn() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for change in req.changes:
                tables = cascade_schedule_change(
                    conn=conn,
                    client_id=change.client_id,
                    service_date=change.service_date,
                    action=change.action,
                    driver_name=change.driver_name,
                    pickup_order=change.pickup_order,
                    pickup_window=change.pickup_window,
                    meal_type=change.meal_type,
                    triggered_by=change.triggered_by,
                )
                results.append({
                    "client_id": change.client_id,
                    "service_date": change.service_date,
                    "action": change.action,
                    "tables_updated": tables,
                })
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, f"Bulk cascade failed, rolled back all: {e}")

    return {"ok": True, "processed": len(results), "changes": results}


@router.get("/schedule/day/{service_date}")
def get_day_schedule(service_date: str):
    """
    Full day view: all active clients for a date.
    Returns calendar, attendance, driver list, kitchen list together.
    """
    try:
        date.fromisoformat(service_date)
    except ValueError:
        raise HTTPException(400, "service_date must be YYYY-MM-DD")

    with carerex_conn() as conn:
        calendar_rows = conn.execute("""
            SELECT c.client_id, c.day_of_week, c.status,
                   d.driver_name, d.pickup_order, d.pickup_window,
                   k.meal_type
            FROM cr_calendar c
            LEFT JOIN cr_driver_list d
                ON d.service_date=c.service_date AND d.client_id=c.client_id AND d.active=1
            LEFT JOIN cr_kitchen_list k
                ON k.service_date=c.service_date AND k.client_id=c.client_id
            WHERE c.service_date=?
            ORDER BY d.pickup_order NULLS LAST, c.client_id
        """, (service_date,)).fetchall()

        attendance = conn.execute("""
            SELECT client_id, scheduled, present
            FROM cr_attendance WHERE service_date=?
        """, (service_date,)).fetchall()

    att_map = {r["client_id"]: dict(r) for r in attendance}

    return {
        "service_date": service_date,
        "client_count": len(calendar_rows),
        "active_count": sum(1 for r in calendar_rows if r["status"] in ("SCHEDULED", "MAKEUP")),
        "clients": [
            {
                "client_id": r["client_id"],
                "day_of_week": r["day_of_week"],
                "status": r["status"],
                "driver": r["driver_name"],
                "pickup_order": r["pickup_order"],
                "pickup_window": r["pickup_window"],
                "meal_type": r["meal_type"],
                "attendance": att_map.get(r["client_id"], {}),
            }
            for r in calendar_rows
        ],
    }


@router.get("/schedule/client/{client_id}")
def get_client_schedule(client_id: int, from_date: Optional[str] = None, days: int = 7):
    """Client's upcoming schedule for the next N days."""
    start = date.fromisoformat(from_date) if from_date else date.today()
    end = start + timedelta(days=days)

    with carerex_conn() as conn:
        rows = conn.execute("""
            SELECT c.service_date, c.day_of_week, c.status,
                   d.driver_name, d.pickup_window, k.meal_type
            FROM cr_calendar c
            LEFT JOIN cr_driver_list d
                ON d.service_date=c.service_date AND d.client_id=c.client_id AND d.active=1
            LEFT JOIN cr_kitchen_list k
                ON k.service_date=c.service_date AND k.client_id=c.client_id
            WHERE c.client_id=? AND c.service_date>=? AND c.service_date<?
            ORDER BY c.service_date
        """, (client_id, start.isoformat(), end.isoformat())).fetchall()

    return {
        "client_id": client_id,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "schedule": [dict(r) for r in rows],
    }


@router.get("/driver/{driver_name}/{service_date}")
def get_driver_route(driver_name: str, service_date: str):
    """
    Driver's route sheet for a date.
    Larry is blocked at write time — this endpoint is read-only.
    """
    with carerex_conn() as conn:
        rows = conn.execute("""
            SELECT d.client_id, d.pickup_order, d.address, d.pickup_window
            FROM cr_driver_list d
            WHERE d.driver_name=? AND d.service_date=? AND d.active=1
            ORDER BY d.pickup_order
        """, (driver_name, service_date)).fetchall()

    return {
        "driver": driver_name,
        "service_date": service_date,
        "stop_count": len(rows),
        "route": [dict(r) for r in rows],
    }


@router.get("/kitchen/{service_date}")
def get_kitchen_list(service_date: str):
    """Kitchen prep list for a date."""
    with carerex_conn() as conn:
        rows = conn.execute("""
            SELECT k.client_id, k.meal_type, k.dietary_notes
            FROM cr_kitchen_list k
            WHERE k.service_date=? AND k.active=1
            ORDER BY k.meal_type, k.client_id
        """, (service_date,)).fetchall()

    from collections import Counter
    meal_counts = Counter(r["meal_type"] for r in rows)
    return {
        "service_date": service_date,
        "total_meals": len(rows),
        "meal_summary": dict(meal_counts),
        "clients": [dict(r) for r in rows],
    }


@router.get("/signin/{service_date}")
def get_signin_sheet(service_date: str):
    """Sign-in/out sheet for a date."""
    with carerex_conn() as conn:
        rows = conn.execute("""
            SELECT s.client_id, s.signed_in, s.signed_in_time,
                   s.signed_out, s.signed_out_time, a.present
            FROM cr_signin_sheets s
            LEFT JOIN cr_attendance a
                ON a.service_date=s.service_date AND a.client_id=s.client_id
            WHERE s.service_date=? AND s.active=1
            ORDER BY s.client_id
        """, (service_date,)).fetchall()

    return {
        "service_date": service_date,
        "expected": len(rows),
        "signed_in": sum(1 for r in rows if r["signed_in"]),
        "clients": [dict(r) for r in rows],
    }


# Register router on standalone app
app.include_router(router)


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_carerex_db()


if __name__ == "__main__":
    import uvicorn
    init_carerex_db()
    uvicorn.run("CC_carerex_module1:app", host="0.0.0.0", port=8002, reload=False)
