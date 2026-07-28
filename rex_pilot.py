#!/usr/bin/env python3
"""
REX Pilot — Multi-entity expense copilot
FastAPI service on port 8093.
DB: ~/Desktop/REX/rex_pilot.db
Entities: all | ai-build | personal | bbg | goj
"""
import os
import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = Path.home() / "Desktop" / "REX" / "rex_pilot.db"

# ── Entity metadata ───────────────────────────────────────────────────────────
ENTITIES = {
    "ai-build": {"label": "🤖 AI Build",   "color": "#7C4DFF"},
    "personal":  {"label": "🧍 Personal",   "color": "#00BCD4"},
    "bbg":       {"label": "🍺 BBG",         "color": "#FF9800"},
    "goj":       {"label": "🌿 GOJ",         "color": "#4CAF50"},
}

VALID_BUCKETS = {"all", "ai-build", "personal", "bbg", "goj"}

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create schema and seed sample data if empty."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket      TEXT    NOT NULL CHECK(bucket IN ('ai-build','personal','bbg','goj')),
            label       TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            recurring   INTEGER NOT NULL DEFAULT 0,
            vendor      TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE VIEW IF NOT EXISTS subscriptions AS
        SELECT * FROM expenses WHERE recurring = 1
    """)

    # Seed sample data only if table is empty
    row = c.execute("SELECT COUNT(*) FROM expenses").fetchone()
    if row[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        this_month = datetime.utcnow().strftime("%Y-%m-01 00:00:00")
        samples = [
            # ai-build
            ("ai-build", "[SAMPLE] Claude Pro subscription",   20.00, 1, "Anthropic",    this_month),
            ("ai-build", "[SAMPLE] OpenAI API credits",        15.00, 0, "OpenAI",       this_month),
            ("ai-build", "[SAMPLE] GitHub Copilot",            10.00, 1, "GitHub",       this_month),
            ("ai-build", "[SAMPLE] Fly.io hosting",             5.00, 1, "Fly.io",       this_month),
            # personal
            ("personal", "[SAMPLE] iCloud+ 200GB",              2.99, 1, "Apple",        this_month),
            ("personal", "[SAMPLE] Spotify Premium",            9.99, 1, "Spotify",      this_month),
            ("personal", "[SAMPLE] Amazon Prime",              14.99, 1, "Amazon",       this_month),
            # bbg
            ("bbg",      "[SAMPLE] Square POS monthly fee",    60.00, 1, "Square",       this_month),
            ("bbg",      "[SAMPLE] Instagram Ads",             50.00, 0, "Meta",         this_month),
            ("bbg",      "[SAMPLE] Liquor delivery",          120.00, 0, "McLane",       this_month),
            # goj
            ("goj",      "[SAMPLE] myEZcare subscription",    299.00, 1, "myEZcare",     this_month),
            ("goj",      "[SAMPLE] Carecenta data export fee",  25.00, 0, "Carecenta",   this_month),
            ("goj",      "[SAMPLE] Telegram bot hosting",        5.00, 1, "DigitalOcean",this_month),
        ]
        c.executemany(
            "INSERT INTO expenses (bucket, label, amount, recurring, vendor, created_at) VALUES (?,?,?,?,?,?)",
            samples
        )
        conn.commit()

    conn.close()


# ── Pydantic models ───────────────────────────────────────────────────────────

class ExpenseIn(BaseModel):
    bucket: str
    label:  str
    amount: float
    recurring: int = 0
    vendor:    str = ""


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="REX Pilot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "rex-pilot", "port": 8093}


# ── /pilot/expenses ───────────────────────────────────────────────────────────

@app.get("/pilot/expenses")
def list_expenses(bucket: Optional[str] = None):
    """List expenses, optionally filtered by bucket."""
    conn = get_db()
    if bucket and bucket != "all":
        if bucket not in VALID_BUCKETS:
            raise HTTPException(400, f"Invalid bucket: {bucket}")
        rows = conn.execute(
            "SELECT * FROM expenses WHERE bucket=? ORDER BY created_at DESC", (bucket,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM expenses ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/pilot/expense")
def add_expense(exp: ExpenseIn):
    """Add a new expense."""
    if exp.bucket not in VALID_BUCKETS - {"all"}:
        raise HTTPException(400, f"Invalid bucket '{exp.bucket}'. Must be one of: ai-build, personal, bbg, goj")
    if exp.amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (bucket, label, amount, recurring, vendor) VALUES (?,?,?,?,?)",
        (exp.bucket, exp.label, exp.amount, int(exp.recurring), exp.vendor)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM expenses WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {"ok": True, "expense": dict(row)}


@app.delete("/pilot/expense/{expense_id}")
def delete_expense(expense_id: int):
    """Delete an expense by ID."""
    conn = get_db()
    row = conn.execute("SELECT id FROM expenses WHERE id=?", (expense_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Expense {expense_id} not found")
    conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "deleted_id": expense_id}


# ── /pilot/summary ────────────────────────────────────────────────────────────

def _month_range():
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start.strftime("%Y-%m-%d %H:%M:%S")


@app.get("/pilot/summary")
def get_summary(bucket: Optional[str] = None):
    """
    Monthly total + count + recent items per bucket.
    bucket=all  → renderRexAll shape
    bucket=<entity> → renderRexPilot shape
    """
    month_start = _month_range()
    conn = get_db()

    if not bucket or bucket == "all":
        return _build_all_summary(conn, month_start)
    else:
        if bucket not in VALID_BUCKETS:
            raise HTTPException(400, f"Invalid bucket: {bucket}")
        return _build_entity_dashboard(conn, month_start, bucket)


def _build_all_summary(conn, month_start: str) -> dict:
    """Shape for renderRexAll."""
    all_rows = conn.execute("SELECT bucket, amount, recurring FROM expenses").fetchall()
    month_rows = conn.execute(
        "SELECT bucket, SUM(amount) as total FROM expenses WHERE created_at >= ? GROUP BY bucket",
        (month_start,)
    ).fetchall()

    grand_total = sum(r["amount"] for r in all_rows)
    grand_month = sum(r["total"] for r in month_rows)
    # Estimated monthly = sum of all recurring expenses across all buckets
    grand_estimated = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE recurring=1"
    ).fetchone()[0]

    entities = {}
    for key, meta in ENTITIES.items():
        bucket_rows = [r for r in all_rows if r["bucket"] == key]
        bucket_spent = sum(r["amount"] for r in bucket_rows)
        bucket_month = next((r["total"] for r in month_rows if r["bucket"] == key), 0)
        entities[key] = {
            "label":        meta["label"],
            "color":        meta["color"],
            "total_spent":  round(bucket_spent, 2),
            "month_spend":  round(bucket_month, 2),
        }

    conn.close()
    return {
        "grand_total":              round(grand_total, 2),
        "grand_month":              round(grand_month, 2),
        "grand_estimated_monthly":  round(grand_estimated, 2),
        "entities":                 entities,
    }


def _build_entity_dashboard(conn, month_start: str, bucket: str) -> dict:
    """Shape for renderRexPilot."""
    all_rows = conn.execute(
        "SELECT * FROM expenses WHERE bucket=? ORDER BY created_at DESC", (bucket,)
    ).fetchall()
    month_rows = conn.execute(
        "SELECT * FROM expenses WHERE bucket=? AND created_at >= ? ORDER BY created_at DESC",
        (bucket, month_start)
    ).fetchall()

    total_spent = sum(r["amount"] for r in all_rows)
    month_spend = sum(r["amount"] for r in month_rows)
    # Estimated monthly = sum of recurring in this bucket
    estimated_monthly = sum(r["amount"] for r in all_rows if r["recurring"] == 1)
    active_services = sum(1 for r in all_rows if r["recurring"] == 1)
    total_payments = len(all_rows)

    # Top categories = top vendors by total spend
    vendor_totals: dict = {}
    for r in all_rows:
        v = r["vendor"] or r["label"]
        vendor_totals[v] = vendor_totals.get(v, 0) + r["amount"]

    categories = sorted(
        [{"name": k, "total": round(v, 2), "icon": "💳", "color": "#00BCD4"}
         for k, v in vendor_totals.items()],
        key=lambda x: x["total"], reverse=True
    )[:5]

    # Upcoming = recurring items (next billing ~same day next month)
    upcoming = []
    for r in all_rows:
        if r["recurring"] == 1:
            # Compute next billing date (same day next month)
            try:
                created = datetime.strptime(r["created_at"][:10], "%Y-%m-%d")
                now = datetime.utcnow()
                next_month = (now.month % 12) + 1
                next_year = now.year + (1 if now.month == 12 else 0)
                try:
                    next_date = now.replace(year=next_year, month=next_month, day=created.day)
                except ValueError:
                    import calendar
                    last_day = calendar.monthrange(next_year, next_month)[1]
                    next_date = now.replace(year=next_year, month=next_month, day=last_day)
                upcoming.append({
                    "name": r["vendor"] or r["label"],
                    "icon": "🔄",
                    "next": next_date.strftime("%b %d"),
                    "est":  r["amount"],
                })
            except Exception:
                pass
    upcoming = sorted(upcoming, key=lambda x: x["next"])[:5]

    conn.close()
    return {
        "bucket":             bucket,
        "month_spend":        round(month_spend, 2),
        "total_spent":        round(total_spent, 2),
        "estimated_monthly":  round(estimated_monthly, 2),
        "active_services":    active_services,
        "total_payments":     total_payments,
        "categories":         categories,
        "upcoming":           upcoming,
    }


# ── /pilot/alerts ─────────────────────────────────────────────────────────────

def _compute_alerts(conn) -> dict:
    """
    Compute spending alerts based on thresholds.
    Returns {alerts: [...], thresholds: {...}}
    """
    alerts = []
    thresholds = {
        "single": float(os.getenv("PILOT_ALERT_SINGLE", "200")),
        "monthly": float(os.getenv("PILOT_ALERT_MONTHLY", "1000")),
    }

    month_start = _month_range()

    # Alert A: Single expense > PILOT_ALERT_SINGLE
    large = conn.execute(
        f"SELECT * FROM expenses WHERE amount > ? ORDER BY amount DESC",
        (thresholds["single"],)
    ).fetchall()
    for row in large:
        alerts.append({
            "type": "large_expense",
            "label": row["label"],
            "amount": round(row["amount"], 2),
            "bucket": row["bucket"],
            "vendor": row["vendor"],
            "severity": "high" if row["amount"] > thresholds["single"] * 1.5 else "medium",
        })

    # Alert B: Monthly bucket total > PILOT_ALERT_MONTHLY
    month_buckets = conn.execute("""
        SELECT bucket, SUM(amount) as total FROM expenses
        WHERE created_at >= ?
        GROUP BY bucket
    """, (month_start,)).fetchall()

    for row in month_buckets:
        if row["total"] > thresholds["monthly"]:
            alerts.append({
                "type": "monthly_overage",
                "bucket": row["bucket"],
                "month_total": round(row["total"], 2),
                "limit": round(thresholds["monthly"], 2),
                "overage": round(row["total"] - thresholds["monthly"], 2),
                "severity": "high",
            })

    # Alert C: Recurring subscriptions list
    subscriptions = conn.execute(
        "SELECT vendor, label, amount FROM expenses WHERE recurring = 1 ORDER BY amount DESC"
    ).fetchall()

    if subscriptions:
        alerts.append({
            "type": "subscriptions",
            "count": len(subscriptions),
            "items": [
                {
                    "vendor": row["vendor"] or row["label"],
                    "amount": round(row["amount"], 2),
                }
                for row in subscriptions
            ],
            "total_monthly": round(sum(row["amount"] for row in subscriptions), 2),
        })

    return {"alerts": alerts, "thresholds": thresholds}


@app.get("/pilot/alerts")
def get_alerts():
    """
    Get spending alerts:
    - Large single expenses (> PILOT_ALERT_SINGLE, default 200)
    - Monthly overage per bucket (> PILOT_ALERT_MONTHLY, default 1000)
    - Recurring subscriptions list
    """
    conn = get_db()
    result = _compute_alerts(conn)
    conn.close()
    return result


# ── QuickBooks / Clover stubs ─────────────────────────────────────────────────

@app.get("/pilot/sync/quickbooks")
def sync_quickbooks():
    """Stub — live sync requires QuickBooks OAuth credentials (Kato's)."""
    return {"status": "needs_credentials", "provider": "QuickBooks Online",
            "note": "OAuth flow not yet configured. Provide QBO credentials to activate."}


@app.get("/pilot/sync/clover")
def sync_clover():
    """Stub — live sync requires Clover API key (Kato's BBG account)."""
    return {"status": "needs_credentials", "provider": "Clover POS",
            "note": "Clover API key not configured. Provide credentials to activate."}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("rex_pilot:app", host="127.0.0.1", port=8093, reload=False)
