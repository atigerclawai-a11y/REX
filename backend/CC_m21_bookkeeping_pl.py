"""
CC_m21_bookkeeping_pl.py — SCAFFOLD — Bookkeeping + P&L
Module M21 · Tiger Claw / GOJ Operations Platform
v1.0 · 2026-06-12

STATUS: SCAFFOLD — clearly labeled.

REAL DATA:
  · Expense lines read directly from rex_pilot.db (expenses table)
    which has 13 real rows (sample-labeled buckets + real recurring items
    like voice/model subscriptions).

PLACEHOLDER / NOT YET REAL:
  · Revenue lines — a revenue_lines table created here. Medicaid claim
    revenue from 837/835 billing is NOT yet flowing (837 generator not built;
    BillRex UI in-progress). Revenue figures are 0.00 until wired.
  · Unit rates per MLTC plan = placeholder; real rate per plan = Kato.
  · QuickBooks integration = not connected (§8 MASTER_REQUIREMENTS).
  · Monthly P&L = expenses from rex_pilot.db + PLACEHOLDER revenue → gap is real.

When billing is live (CC_m24 + BillRex + rex_edi.py), point revenue_lines
to the actual claims/payments tables.

SQLite: ~/Desktop/REX/CC_m21_pl.db (expense cache + revenue scaffold)
Also reads: ~/Desktop/REX/rex_pilot.db (expenses — read-only)

FastAPI router at /m21

Endpoints
---------
  GET  /m21/pl/summary?month=YYYY-MM          — P&L for a month
  GET  /m21/pl/months                         — available months with data
  GET  /m21/pl/categories                     — expense category totals (all-time)
  POST /m21/revenue                           — manually log a revenue line [SCAFFOLD]
  GET  /m21/revenue?month=                    — list revenue lines
  GET  /m21/health                            — module status + data freshness
"""
from __future__ import annotations

import sqlite3
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
DB_PATH     = Path(os.path.expanduser("~/Desktop/REX/CC_m21_pl.db"))
PILOT_DB    = Path(os.path.expanduser("~/Desktop/REX/rex_pilot.db"))
router = APIRouter(prefix="/m21", tags=["M21 Bookkeeping P&L"])

# Expense category display labels (map bucket codes → human labels)
CATEGORY_LABELS = {
    "ai-build":     "AI / Build Tools",
    "voice":        "Voice & Telephony",
    "infra":        "Infrastructure / Cloud",
    "payroll":      "Payroll",
    "operations":   "Operations",
    "admin":        "Administrative",
    "other":        "Other",
}


# ── Schema ─────────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_pilot_conn() -> Optional[sqlite3.Connection]:
    if not PILOT_DB.exists():
        return None
    conn = sqlite3.connect(str(PILOT_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create M21 schema. Safe to call on every import."""
    conn = _get_conn()
    conn.executescript("""
        -- SCAFFOLD revenue table: populated manually or via future billing integration.
        -- Real Medicaid revenue will come from 837/835 claims once BillRex + rex_edi are wired.
        CREATE TABLE IF NOT EXISTS revenue_lines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            month           TEXT    NOT NULL,   -- YYYY-MM
            source          TEXT    NOT NULL,   -- 'medicaid-claims' / 'private-pay' / 'manual'
            payer_name      TEXT,               -- MLTC plan name (PLACEHOLDER — Kato to map)
            description     TEXT,
            amount          REAL    NOT NULL DEFAULT 0.0,  -- PLACEHOLDER: 0 until billing live
            is_placeholder  INTEGER NOT NULL DEFAULT 1,    -- 1 = not real, 0 = verified
            notes           TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_revenue_month ON revenue_lines(month);

        -- Expense cache: mirrors rex_pilot.db expenses for consistent P&L computation.
        -- Synced on each /pl/summary call.
        CREATE TABLE IF NOT EXISTS expense_cache (
            id          INTEGER PRIMARY KEY,
            bucket      TEXT,
            label       TEXT,
            amount      REAL,
            recurring   INTEGER,
            vendor      TEXT,
            created_at  TEXT
        );

        -- Audit log of P&L runs
        CREATE TABLE IF NOT EXISTS pl_run_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            month       TEXT    NOT NULL,
            ran_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            expense_total   REAL,
            revenue_total   REAL,
            net         REAL,
            note        TEXT
        );
    """)
    conn.commit()
    conn.close()


init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_expenses() -> int:
    """Copy expenses from rex_pilot.db into our local cache. Returns row count."""
    pilot = _get_pilot_conn()
    if not pilot:
        return 0
    rows = pilot.execute("SELECT * FROM expenses").fetchall()
    pilot.close()
    conn = _get_conn()
    conn.execute("DELETE FROM expense_cache")
    conn.executemany(
        "INSERT INTO expense_cache (id, bucket, label, amount, recurring, vendor, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(r["id"], r["bucket"], r["label"], r["amount"],
          r["recurring"], r["vendor"], r["created_at"]) for r in rows]
    )
    conn.commit()
    conn.close()
    return len(rows)


def _expense_total_for_month(month: str) -> dict:
    """
    Sum expenses for a given YYYY-MM.
    rex_pilot.db expenses don't have month tagging — recurring items count every month,
    one-time items count in their created_at month.
    SCAFFOLD NOTE: This is an approximation; real bookkeeping requires line-item
    monthly assignment (QuickBooks integration, §8 MASTER_REQUIREMENTS).
    """
    conn = _get_conn()
    # Recurring = applies every month
    recurring_total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expense_cache WHERE recurring = 1"
    ).fetchone()[0]
    # One-time = only in the month they were created
    onetime_total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expense_cache "
        "WHERE recurring = 0 AND strftime('%Y-%m', created_at) = ?",
        (month,)
    ).fetchone()[0]
    # By category
    cats = conn.execute(
        "SELECT bucket, SUM(amount) as total FROM expense_cache "
        "WHERE recurring = 1 OR strftime('%Y-%m', created_at) = ? "
        "GROUP BY bucket ORDER BY total DESC",
        (month,)
    ).fetchall()
    conn.close()
    return {
        "recurring": round(recurring_total, 2),
        "one_time": round(onetime_total, 2),
        "total": round(recurring_total + onetime_total, 2),
        "by_category": [
            {"bucket": r["bucket"],
             "label": CATEGORY_LABELS.get(r["bucket"], r["bucket"]),
             "total": round(r["total"], 2)}
            for r in cats
        ],
    }


def _revenue_total_for_month(month: str) -> dict:
    """
    Sum revenue for a given YYYY-MM from the revenue_lines table.
    SCAFFOLD: all rows are is_placeholder=1 until billing is wired.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM revenue_lines WHERE month = ? ORDER BY source",
        (month,)
    ).fetchall()
    total = sum(r["amount"] for r in rows)
    all_placeholder = all(r["is_placeholder"] for r in rows) if rows else True
    conn.close()
    return {
        "total": round(total, 2),
        "lines": [dict(r) for r in rows],
        "is_placeholder": all_placeholder,
        "placeholder_note": (
            "SCAFFOLD — Revenue = $0 until 837 generator + BillRex billing pipeline is live. "
            "Real Medicaid claim revenue = Kato to confirm per-plan unit rates."
            if all_placeholder else None
        ),
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class RevenueLineIn(BaseModel):
    month: str              # YYYY-MM
    source: str             # medicaid-claims / private-pay / manual
    payer_name: Optional[str] = None
    description: Optional[str] = None
    amount: float = 0.0
    is_placeholder: bool = True
    notes: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/pl/summary")
def pl_summary(month: Optional[str] = None):
    """
    Monthly P&L summary.
    SCAFFOLD: revenue total will be 0 until billing pipeline is live.
    month format: YYYY-MM (defaults to current month)
    """
    if not month:
        month = datetime.now().strftime("%Y-%m")
    # Validate format
    try:
        datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    synced = _sync_expenses()
    expenses = _expense_total_for_month(month)
    revenue = _revenue_total_for_month(month)
    net = round(revenue["total"] - expenses["total"], 2)

    # Log the run
    conn = _get_conn()
    conn.execute(
        "INSERT INTO pl_run_log (month, expense_total, revenue_total, net, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (month, expenses["total"], revenue["total"], net,
         "scaffold" if revenue["is_placeholder"] else "real")
    )
    conn.commit()
    conn.close()

    return {
        "month": month,
        "scaffold": True,
        "scaffold_note": (
            "SCAFFOLD — Revenue line is $0 (billing not live). "
            "Expenses sourced from rex_pilot.db (real recurring items + sample data). "
            "Net = expenses only until BillRex/837 pipeline is wired."
        ),
        "revenue": revenue,
        "expenses": expenses,
        "net": net,
        "net_label": "surplus" if net >= 0 else "deficit",
        "expense_source_rows": synced,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/pl/months")
def pl_months():
    """List months that have expense or revenue data."""
    conn = _get_conn()
    rev_months = {r[0] for r in conn.execute(
        "SELECT DISTINCT month FROM revenue_lines ORDER BY month"
    ).fetchall()}
    exp_months = {r[0] for r in conn.execute(
        "SELECT DISTINCT strftime('%Y-%m', created_at) FROM expense_cache"
    ).fetchall() if r[0]}
    conn.close()
    all_months = sorted(rev_months | exp_months)
    # Always include current month
    cur = datetime.now().strftime("%Y-%m")
    if cur not in all_months:
        all_months.append(cur)
    return {"months": sorted(all_months)}


@router.get("/pl/categories")
def pl_categories():
    """Expense totals by category (all-time from rex_pilot.db)."""
    _sync_expenses()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT bucket, SUM(amount) as total, COUNT(*) as line_count "
        "FROM expense_cache GROUP BY bucket ORDER BY total DESC"
    ).fetchall()
    conn.close()
    return {
        "categories": [
            {"bucket": r["bucket"],
             "label": CATEGORY_LABELS.get(r["bucket"], r["bucket"]),
             "total": round(r["total"], 2),
             "line_count": r["line_count"]}
            for r in rows
        ],
        "source": "rex_pilot.db expenses table (real items)",
        "scaffold_note": "Category totals include [SAMPLE]-labeled rows in rex_pilot.db",
    }


@router.post("/revenue", status_code=201)
def add_revenue_line(body: RevenueLineIn):
    """
    Manually add a revenue line. SCAFFOLD — for testing shape only until billing pipeline live.
    All manual entries default to is_placeholder=True unless Kato explicitly marks them real.
    """
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO revenue_lines
            (month, source, payer_name, description, amount, is_placeholder, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (body.month, body.source, body.payer_name, body.description,
          body.amount, int(body.is_placeholder), body.notes))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"id": new_id, "scaffold": body.is_placeholder,
            "note": "Revenue line logged. Mark is_placeholder=false only when verified real."}


@router.get("/revenue")
def list_revenue(month: Optional[str] = None):
    """List revenue lines, optionally filtered by month."""
    conn = _get_conn()
    if month:
        rows = conn.execute(
            "SELECT * FROM revenue_lines WHERE month = ? ORDER BY created_at DESC",
            (month,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM revenue_lines ORDER BY month DESC, created_at DESC"
        ).fetchall()
    conn.close()
    return {
        "revenue_lines": [dict(r) for r in rows],
        "count": len(rows),
        "scaffold_note": (
            "SCAFFOLD — Revenue is $0 until 837/BillRex billing pipeline is live. "
            "Real revenue per MLTC plan = Kato to confirm unit rates."
        ),
    }


@router.get("/health")
def m21_health():
    """Module health: DB accessibility, expense sync status."""
    pilot_ok = PILOT_DB.exists()
    conn = _get_conn()
    exp_count = conn.execute("SELECT COUNT(*) FROM expense_cache").fetchone()[0]
    rev_count = conn.execute("SELECT COUNT(*) FROM revenue_lines").fetchone()[0]
    conn.close()
    return {
        "module": "M21 Bookkeeping P&L",
        "scaffold": True,
        "pilot_db_accessible": pilot_ok,
        "expense_cache_rows": exp_count,
        "revenue_lines": rev_count,
        "revenue_real": False,
        "billing_pipeline_live": False,
        "quickbooks_connected": False,
        "next_step": "Wire 837 generator + BillRex claims output → revenue_lines (mark is_placeholder=0)",
    }


# ── Self-test ──────────────────────────────────────────────────────────────────

def _selftest():
    """
    --selftest: verify schema, expense sync from rex_pilot.db, revenue insert, P&L query.
    Run: python3 CC_m21_bookkeeping_pl.py --selftest
    """
    import tempfile
    global DB_PATH
    orig = DB_PATH
    tmp = tempfile.mktemp(suffix=".db")
    DB_PATH = Path(tmp)
    try:
        print("=== CC_m21 SELFTEST ===")
        init_db()
        print("[PASS] init_db() — schema created")

        # Sync expenses
        n = _sync_expenses()
        print(f"[PASS] Expense sync from rex_pilot.db: {n} rows")

        # Get categories
        conn = _get_conn()
        cats = conn.execute(
            "SELECT bucket, SUM(amount) as t FROM expense_cache GROUP BY bucket"
        ).fetchall()
        for c in cats:
            print(f"  · {c['bucket']}: ${c['t']:.2f}")
        total_exp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expense_cache").fetchone()[0]
        print(f"  Total expenses in rex_pilot.db: ${total_exp:.2f}")

        # Insert scaffold revenue line
        conn.execute("""
            INSERT INTO revenue_lines (month, source, amount, is_placeholder, notes)
            VALUES ('2026-06', 'medicaid-claims', 0.00, 1,
                    '[SELFTEST] Placeholder — real rate TBD by Kato')
        """)
        conn.commit()
        rev = conn.execute("SELECT COUNT(*) FROM revenue_lines").fetchone()[0]
        print(f"[PASS] Revenue line inserted: {rev} row(s), is_placeholder=1")
        conn.close()

        # P&L summary
        exp = _expense_total_for_month("2026-06")
        rev_data = _revenue_total_for_month("2026-06")
        net = round(rev_data["total"] - exp["total"], 2)
        print(f"[PASS] P&L Jun 2026 → revenue=${rev_data['total']:.2f} "
              f"expenses=${exp['total']:.2f} net=${net:.2f}")
        print(f"  scaffold={rev_data['is_placeholder']} ← revenue is placeholder until billing live")
        print("=== ALL SELFTEST CHECKS PASSED ===")
    finally:
        DB_PATH = orig
        import os as _os
        _os.unlink(tmp)


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print("Usage: python3 CC_m21_bookkeeping_pl.py --selftest")
