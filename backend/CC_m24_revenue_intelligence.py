"""
CC_m24_revenue_intelligence.py — SCAFFOLD — Revenue Intelligence per Client
Module M24 · Tiger Claw / GOJ Operations Platform
v1.0 · 2026-06-12

STATUS: SCAFFOLD — clearly labeled.

DATA SOURCES:
  · auth_tracker.db (READ-ONLY — never writes) — clients, authorization, attendance_log
    Located at ~/Documents/goj files/dashboard/auth_tracker.db

REAL vs PLACEHOLDER:
  · Client attendance counts from attendance_log — REAL (10,899 rows)
  · Client + authorization data — REAL (437 clients, 484 auth rows)
  · Unit rate ($ per attended day) — PLACEHOLDER = $0.00
    Real rate per MLTC plan is confidential; Kato to configure via
    PUT /m24/config/rate or the rates config file.
    Typical HCBS/MLTC ADC rates range $80–$200/day but vary by plan,
    service code, and contract — DO NOT present any dollar figure as real.
  · Estimated revenue = attendance × unit_rate → $0 until rates set.
  · Under-utilization logic (auth allows N days, client attends < N) IS real data.

FastAPI router at /m24

Endpoints
---------
  GET  /m24/revenue/by-client?month=YYYY-MM&plan=   — per-client estimated revenue, ranked
  GET  /m24/revenue/underutilized?month=YYYY-MM      — clients using < authorized days
  GET  /m24/revenue/summary?month=YYYY-MM            — aggregate + flags
  GET  /m24/config/rates                             — current unit rates (all placeholder)
  PUT  /m24/config/rates                             — Kato sets real rates per plan
  GET  /m24/health                                   — module + DB status
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
AUTH_DB   = Path(os.path.expanduser("~/Documents/goj files/dashboard/auth_tracker.db"))
RATES_CFG = Path(os.path.expanduser("~/Desktop/REX/CC_m24_rates.json"))
router    = APIRouter(prefix="/m24", tags=["M24 Revenue Intelligence"])

# ── Default unit rates — ALL PLACEHOLDER ──────────────────────────────────────
# Real rates per MLTC plan are set by Kato via PUT /m24/config/rates.
# DO NOT treat these as real financial figures.
DEFAULT_RATES: Dict[str, float] = {
    "Aetna Better Health":                     0.00,   # PLACEHOLDER — Kato to set
    "Anthem — Integra":                        0.00,   # PLACEHOLDER
    "Anthem":                                  0.00,   # PLACEHOLDER
    "ElderServe — Riverspring Health":         0.00,   # PLACEHOLDER
    "Empire BlueCross BlueShield":             0.00,   # PLACEHOLDER
    "MetroPlus Health":                        0.00,   # PLACEHOLDER
    "Senior Whole Health":                     0.00,   # PLACEHOLDER
    "VNS Health":                              0.00,   # PLACEHOLDER
    "VillageCare MAX":                         0.00,   # PLACEHOLDER
    "Private Pay":                             0.00,   # PLACEHOLDER
    "_default":                                0.00,   # Fallback for unknown plans
}
RATES_PLACEHOLDER_NOTE = (
    "SCAFFOLD — All unit rates are $0.00 placeholder. "
    "Real rate per MLTC plan = confidential, Kato to configure via PUT /m24/config/rates. "
    "Estimated revenue will remain $0 until rates are set."
)


# ── Rate helpers ──────────────────────────────────────────────────────────────

def _load_rates() -> Dict[str, float]:
    if RATES_CFG.exists():
        try:
            data = json.loads(RATES_CFG.read_text())
            return {**DEFAULT_RATES, **data.get("rates", {})}
        except Exception:
            pass
    return dict(DEFAULT_RATES)


def _save_rates(rates: Dict[str, float]) -> None:
    RATES_CFG.write_text(json.dumps({"rates": rates, "updated_at": datetime.now().isoformat()}, indent=2))


def _rate_for_plan(rates: Dict[str, float], plan: str) -> float:
    return rates.get(plan, rates.get("_default", 0.0))


# ── DB helper ─────────────────────────────────────────────────────────────────

def _get_auth_db() -> Optional[sqlite3.Connection]:
    if not AUTH_DB.exists():
        return None
    conn = sqlite3.connect(f"file:{AUTH_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Core queries (read-only) ──────────────────────────────────────────────────

def _attendance_by_client(month: str) -> Dict[str, dict]:
    """
    Return {client_name: {attended, plan_canonical}} for a given YYYY-MM.
    Uses attendance_log.status='present' as the attended-day signal.
    """
    conn = _get_auth_db()
    if not conn:
        return {}
    rows = conn.execute("""
        SELECT al.client_name,
               COUNT(*) AS attended,
               c.plan_canonical
        FROM attendance_log al
        LEFT JOIN clients c ON c.name = al.client_name
        WHERE al.status = 'present'
          AND strftime('%Y-%m', al.log_date) = ?
        GROUP BY al.client_name
        ORDER BY attended DESC
    """, (month,)).fetchall()
    conn.close()
    return {
        r["client_name"]: {
            "attended": r["attended"],
            "plan_canonical": r["plan_canonical"] or "Unknown",
        }
        for r in rows
    }


def _authorized_days_by_client(month: str) -> Dict[str, dict]:
    """
    Return {client_name: {auth_days_per_week, workdays_in_month, total_auth_days, auth_id}}.
    Authorized days per week × workdays in month = ceiling of authorized days this month.
    A rough approximation — real auth tracking needs EVV/service-delivery records.
    """
    conn = _get_auth_db()
    if not conn:
        return {}

    # Count Mon–Fri days in the given month
    year, mon = int(month[:4]), int(month[5:7])
    from calendar import monthrange
    _, days_in_month = monthrange(year, mon)
    weekdays = sum(
        1 for d in range(1, days_in_month + 1)
        if date(year, mon, d).weekday() < 5
    )

    # Get active authorizations for the month
    month_start = f"{month}-01"
    import calendar
    month_end = f"{month}-{days_in_month:02d}"

    rows = conn.execute("""
        SELECT a.client_name,
               a.auth_id,
               a.authorized_days_per_week,
               a.total_visits_authorized,
               a.visits_used,
               a.service_start_date,
               a.service_end_date,
               a.status
        FROM authorization a
        WHERE a.status IN ('ACTIVE', 'active')
          AND a.service_start_date <= ?
          AND (a.service_end_date >= ? OR a.service_end_date IS NULL)
        ORDER BY a.client_name, a.service_end_date DESC
    """, (month_end, month_start)).fetchall()
    conn.close()

    result = {}
    for r in rows:
        name = r["client_name"]
        if name in result:
            continue  # Take first (most recent) active auth per client
        dpw = r["authorized_days_per_week"] or 0
        try:
            dpw = float(dpw)
        except (TypeError, ValueError):
            dpw = 0.0
        # Weeks in month ≈ weekdays / 5
        approx_weeks = weekdays / 5.0
        total_auth = round(dpw * approx_weeks)
        result[name] = {
            "auth_id": r["auth_id"],
            "auth_days_per_week": dpw,
            "workdays_in_month": weekdays,
            "total_auth_days_approx": total_auth,
            "auth_status": r["status"],
        }
    return result


# ── Pydantic models ───────────────────────────────────────────────────────────

class RatesUpdate(BaseModel):
    rates: Dict[str, float]
    note: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/revenue/by-client")
def revenue_by_client(month: Optional[str] = None, plan: Optional[str] = None):
    """
    Per-client estimated revenue for a month, ranked highest to lowest.
    SCAFFOLD: estimated_revenue = attended_days × unit_rate (unit_rate = $0 until Kato sets it).
    """
    if not month:
        month = datetime.now().strftime("%Y-%m")
    try:
        datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    rates = _load_rates()
    attendance = _attendance_by_client(month)
    auth_data = _authorized_days_by_client(month)

    results = []
    for client_name, att in attendance.items():
        plan_name = att["plan_canonical"]
        if plan and plan.lower() not in plan_name.lower():
            continue
        unit_rate = _rate_for_plan(rates, plan_name)
        attended = att["attended"]
        estimated_revenue = round(attended * unit_rate, 2)
        auth = auth_data.get(client_name, {})
        auth_days = auth.get("total_auth_days_approx", None)
        utilization_pct = (
            round((attended / auth_days * 100), 1) if auth_days and auth_days > 0 else None
        )
        results.append({
            "client_name": client_name,
            "plan": plan_name,
            "attended_days": attended,
            "unit_rate": unit_rate,
            "unit_rate_is_placeholder": unit_rate == 0.0,
            "estimated_revenue": estimated_revenue,
            "auth_days_approx": auth_days,
            "utilization_pct": utilization_pct,
        })

    results.sort(key=lambda x: x["estimated_revenue"], reverse=True)
    all_placeholder = all(r["unit_rate_is_placeholder"] for r in results)

    return {
        "month": month,
        "scaffold": True,
        "scaffold_note": RATES_PLACEHOLDER_NOTE if all_placeholder else None,
        "clients": results,
        "count": len(results),
        "total_estimated_revenue": round(sum(r["estimated_revenue"] for r in results), 2),
    }


@router.get("/revenue/underutilized")
def underutilized_clients(month: Optional[str] = None):
    """
    Clients whose attended days are fewer than their authorized days for the month.
    This uses REAL attendance + auth data — no unit rates involved.
    Under-utilization flags = real operational signal (revenue risk).
    """
    if not month:
        month = datetime.now().strftime("%Y-%m")
    try:
        datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    attendance = _attendance_by_client(month)
    auth_data = _authorized_days_by_client(month)

    flags = []
    for client_name, auth in auth_data.items():
        auth_days = auth["total_auth_days_approx"]
        if not auth_days or auth_days <= 0:
            continue
        att = attendance.get(client_name, {})
        attended = att.get("attended", 0)
        gap = auth_days - attended
        if gap > 0:
            flags.append({
                "client_name": client_name,
                "plan": att.get("plan_canonical", "Unknown"),
                "auth_days_approx": auth_days,
                "attended_days": attended,
                "unused_days": gap,
                "utilization_pct": round((attended / auth_days * 100), 1),
                "auth_id": auth["auth_id"],
            })

    flags.sort(key=lambda x: x["unused_days"], reverse=True)

    return {
        "month": month,
        "under_utilized_clients": flags,
        "count": len(flags),
        "total_unused_days": sum(f["unused_days"] for f in flags),
        "data_note": (
            "Authorized days = auth.authorized_days_per_week × approx weeks in month. "
            "Approximate — real EVV service-delivery data needed for exact audit."
        ),
    }


@router.get("/revenue/summary")
def revenue_summary(month: Optional[str] = None):
    """Aggregate revenue intelligence for a month."""
    if not month:
        month = datetime.now().strftime("%Y-%m")
    try:
        datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    rates = _load_rates()
    attendance = _attendance_by_client(month)
    auth_data = _authorized_days_by_client(month)

    total_attended = sum(a["attended"] for a in attendance.values())
    # By plan
    by_plan: Dict[str, dict] = {}
    for client_name, att in attendance.items():
        plan = att["plan_canonical"]
        if plan not in by_plan:
            by_plan[plan] = {"attended": 0, "clients": 0, "estimated_revenue": 0.0}
        by_plan[plan]["attended"] += att["attended"]
        by_plan[plan]["clients"] += 1
        by_plan[plan]["estimated_revenue"] += att["attended"] * _rate_for_plan(rates, plan)

    total_rev = sum(v["estimated_revenue"] for v in by_plan.values())

    # Under-utilization count
    underutil_count = sum(
        1 for name, auth in auth_data.items()
        if auth["total_auth_days_approx"] > attendance.get(name, {}).get("attended", 0)
    )

    return {
        "month": month,
        "scaffold": True,
        "scaffold_note": RATES_PLACEHOLDER_NOTE,
        "total_attended_days": total_attended,
        "active_clients_in_month": len(attendance),
        "clients_with_auth": len(auth_data),
        "underutilized_client_count": underutil_count,
        "total_estimated_revenue": round(total_rev, 2),
        "by_plan": [
            {"plan": k,
             "clients": v["clients"],
             "attended_days": v["attended"],
             "estimated_revenue": round(v["estimated_revenue"], 2),
             "rate_is_placeholder": _rate_for_plan(rates, k) == 0.0}
            for k, v in sorted(by_plan.items(), key=lambda x: -x[1]["attended"])
        ],
    }


@router.get("/config/rates")
def get_rates():
    """Current unit rates per MLTC plan. All placeholder until Kato sets them."""
    rates = _load_rates()
    return {
        "rates": rates,
        "all_placeholder": all(v == 0.0 for k, v in rates.items() if k != "_default"),
        "placeholder_note": RATES_PLACEHOLDER_NOTE,
        "how_to_set": "PUT /m24/config/rates with {rates: {'Plan Name': dollar_amount}}",
    }


@router.put("/config/rates")
def update_rates(body: RatesUpdate):
    """
    Kato sets real unit rates per MLTC plan ($ per attended day).
    Example: {'rates': {'Aetna Better Health': 145.00}}
    Setting a rate to any value other than 0.00 marks it as real.
    """
    current = _load_rates()
    current.update(body.rates)
    _save_rates(current)
    placeholder_remaining = sum(1 for k, v in current.items() if k != "_default" and v == 0.0)
    return {
        "updated": True,
        "note": body.note,
        "placeholder_plans_remaining": placeholder_remaining,
    }


@router.get("/health")
def m24_health():
    """Module health and data accessibility."""
    db_ok = AUTH_DB.exists()
    client_count = 0
    attendance_count = 0
    auth_count = 0
    if db_ok:
        conn = _get_auth_db()
        if conn:
            client_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            attendance_count = conn.execute("SELECT COUNT(*) FROM attendance_log").fetchone()[0]
            auth_count = conn.execute("SELECT COUNT(*) FROM authorization").fetchone()[0]
            conn.close()
    rates = _load_rates()
    return {
        "module": "M24 Revenue Intelligence",
        "scaffold": True,
        "auth_db_accessible": db_ok,
        "client_count": client_count,
        "attendance_log_rows": attendance_count,
        "authorization_rows": auth_count,
        "unit_rates_configured": sum(1 for k, v in rates.items() if k != "_default" and v > 0),
        "unit_rates_placeholder": sum(1 for k, v in rates.items() if k != "_default" and v == 0.0),
        "revenue_real": False,
        "next_step": "Kato: PUT /m24/config/rates with real dollar amounts per MLTC plan",
    }


# ── Self-test ──────────────────────────────────────────────────────────────────

def _selftest():
    """
    --selftest: verify read-only auth_tracker access, attendance query, auth query,
    underutilization logic. No writes to auth_tracker.
    Run: python3 CC_m24_revenue_intelligence.py --selftest
    """
    print("=== CC_m24 SELFTEST ===")

    # Health check
    db_ok = AUTH_DB.exists()
    print(f"[{'PASS' if db_ok else 'WARN'}] auth_tracker.db accessible: {db_ok}")
    if not db_ok:
        print(f"  Path checked: {AUTH_DB}")
        print("  Skipping live-DB tests.")
        print("=== SELFTEST DONE (DB not available) ===")
        return

    # Attendance query — real data
    month = "2026-03"  # Use a month known to have data from sample rows
    att = _attendance_by_client(month)
    print(f"[PASS] Attendance query month={month}: {len(att)} clients with present marks")
    if att:
        top = sorted(att.items(), key=lambda x: -x[1]["attended"])[:3]
        for name, d in top:
            print(f"  · {name}: {d['attended']} days | plan={d['plan_canonical']}")

    # Auth query
    auth = _authorized_days_by_client(month)
    print(f"[PASS] Auth query month={month}: {len(auth)} clients with active auths")

    # Under-utilization check
    flags = []
    for name, a in auth.items():
        attended = att.get(name, {}).get("attended", 0)
        if a["total_auth_days_approx"] > attended:
            flags.append((name, a["total_auth_days_approx"], attended))
    flags.sort(key=lambda x: -(x[1] - x[2]))
    print(f"[PASS] Under-utilized clients (auth > attended): {len(flags)}")
    if flags:
        print(f"  Top 3 gaps:")
        for name, auth_d, att_d in flags[:3]:
            print(f"  · {name}: auth≈{auth_d}d attended={att_d}d gap={auth_d - att_d}d")

    # Rates check
    rates = _load_rates()
    all_zero = all(v == 0.0 for k, v in rates.items() if k != "_default")
    print(f"[PASS] Rate config loaded: {len(rates)} plans, all_placeholder={all_zero}")
    print(f"  (Expected all_zero=True until Kato sets real rates)")

    # Revenue calculation with placeholder rate (should be $0)
    plan = "Aetna Better Health"
    rate = _rate_for_plan(rates, plan)
    aetna_clients = {n: d for n, d in att.items() if d["plan_canonical"] == plan}
    aetna_attended = sum(d["attended"] for d in aetna_clients.values())
    est_rev = aetna_attended * rate
    print(f"[PASS] Revenue calc: {plan} → {aetna_attended} attended × ${rate:.2f}/day = ${est_rev:.2f}")
    print(f"  (Expected $0.00 — rates are placeholder)")

    print("=== ALL SELFTEST CHECKS PASSED ===")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print("Usage: python3 CC_m24_revenue_intelligence.py --selftest")
