#!/usr/bin/env python3
"""
CC_schedule_to_837.py — Attendance → Billable 837 Claim Bridge
=============================================================
Reads auth_tracker.db attendance_log and authorization tables,
joins against client plan assignments, and produces claim dicts
ready for CC_medicaid_837_generator.py.

Pipeline:
  biometric sign-in → attendance_log
  → authorizations (validates eligibility)
  → CC_schedule_to_837.py (groups by payer + date range)
  → CC_medicaid_837_generator.py (produces X12 837P EDI)
  → Availity clearinghouse (submit)
  → claims_837 table (track)
  → payments_835 table (remittance)

Authorization Rules (hardcoded from HHA Exchange / MLTC contracts):
  • 1 visit = 1 billable day (unit: UN, per visit)
  • Transport = +2 billable units (pickup + dropoff, code A0425)
  • Telehealth = 1 unit/day (if payer allows)
  • Food/meals = 1 unit/day (if payer allows)
  • Authorization MUST be ACTIVE on the service date
  • Payer plan determines rate, ISA routing, and clearinghouse path

Output: List[Dict] — claim dicts with all fields required by generate_837p()
"""

from pathlib import Path
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from CC_billing_payers import (
    get_payer_config,
    build_837_config,
    GOJ_IDENTITY,
)

DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

# Day code mapping: GOJ schema → column suffix
DAY_COLUMNS = {
    "M":  "day_M_actual",
    "T":  "day_T_actual",
    "W":  "day_W_actual",
    "TH": "day_TH_actual",
    "F":  "day_F_actual",
    "Sa": "day_Sa_actual",
    "Su": "day_Su_actual",
}

DAY_NAME = {"M": "Mon", "T": "Tue", "W": "Wed", "TH": "Thu", "F": "Fri", "Sa": "Sat", "Su": "Sun"}


def _db() -> sqlite3.Connection:
    """Open read-only connection to auth_tracker.db."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_active_authorizations(
    for_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Return all active authorizations valid on `for_date` (default: today).
    Joins clients table for demographics, plan, transport, address.
    """
    if for_date is None:
        for_date = date.today()
    date_str = for_date.isoformat()

    conn = _db()
    try:
        rows = conn.execute("""
            SELECT
                a.client_name,
                a.payer_raw,
                a.payer_canonical,
                a.service_start_date as auth_start,
                a.service_end_date as auth_end,
                a.member_id,
                a.service_codes,
                a.authorization_number,
                c.name,
                c.active,
                c.plan_raw,
                c.plan_canonical,
                c.transportation,
                c.address
            FROM authorization a
            LEFT JOIN clients c ON c.name = a.client_name
            WHERE a.service_end_date >= ?
              AND a.service_start_date <= ?
              AND a.status = 'ACTIVE'
              AND c.active = 1
            ORDER BY a.payer_canonical, a.client_name
        """, (date_str, date_str))
        return [dict(r) for r in rows.fetchall()]
    finally:
        conn.close()


def get_attendance_for_range(
    start_date: date,
    end_date: date,
) -> List[Dict[str, Any]]:
    """
    Return all attendance records in date range.
    Tries attendance_log first, then falls back to attendance_staged_rows.
    """
    conn = _db()
    try:
        # Try attendance_log first
        rows = conn.execute("""
            SELECT client_name, log_date, shift, status, source, logged_at
            FROM attendance_log
            WHERE log_date BETWEEN ? AND ?
            ORDER BY log_date, client_name
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        if rows:
            return [dict(r) for r in rows]

        # Fall back to staged
        rows = conn.execute("""
            SELECT client_name, staged_at as log_date, '1' as shift
            FROM attendance_staged_rows
            WHERE staged_at BETWEEN ? AND ?
            ORDER BY staged_at, client_name
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_client_schedule(client_name: str, for_date: date) -> Tuple[int, bool]:
    """
    Returns (shift, has_transport) for a client on a given date.
    shift: 0=none, 1=shift1, 2=shift2
    has_transport: True if marked TR
    """
    conn = _db()
    try:
        goj_day = {"Mon": "M", "Tue": "T", "Wed": "W", "Thu": "TH",
                    "Fri": "F", "Sat": "Sa", "Sun": "Su"}.get(
            for_date.strftime("%a"), "M"
        )
        day_col = DAY_COLUMNS.get(goj_day, "day_M_actual")

        row = conn.execute(f"""
            SELECT {day_col} as shift, transportation
            FROM clients
            WHERE name = ?
        """, (client_name,)).fetchone()

        if row:
            shift = int(row["shift"] or 0)
            has_tr = str(row["transportation"] or "").upper() == "TR"
            return (shift, has_tr)
        return (0, False)
    finally:
        conn.close()


def build_claims(
    start_date: date,
    end_date: date,
    payer_filter: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Main entry point. Build claim dicts from attendance + authorization.

    Args:
        start_date, end_date: date range to bill
        payer_filter: only bill this payer (None = all)
        dry_run: if True, only validate — don't mark as submitted

    Returns:
        dict with claims list, summary, warnings, and EDI per payer
    """
    from CC_medicaid_837_generator import generate_837p

    auths = get_active_authorizations()
    attendance = get_attendance_for_range(start_date, end_date)

    if not attendance:
        return {
            "claims": [],
            "summary": {"total_claims": 0, "total_charge": 0.0, "by_payer": {}, "warnings": ["No attendance data found"]},
            "edi_by_payer": {},
            "date_range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        }

    # Index auths by client name for fast lookup
    auth_index: Dict[str, Dict] = {}
    for a in auths:
        name = (a.get("client_name") or "").strip()
        if name:
            auth_index[name] = a

    claims: List[Dict] = []
    warnings: List[str] = []
    seen: set = set()  # dedupe (client_name, date, plan_type)

    for att in attendance:
        client_name = (att.get("client_name") or "").strip()
        log_date_str = att.get("log_date") or ""
        if not client_name or not log_date_str:
            continue

        try:
            log_date = date.fromisoformat(log_date_str)
        except ValueError:
            continue

        if log_date < start_date or log_date > end_date:
            continue

        auth = auth_index.get(client_name)
        if not auth:
            warnings.append(f"No active authorization for {client_name} on {log_date_str}")
            continue

        # Use payer_canonical first, fall back to payer_raw
        plan_type = (auth.get("payer_canonical") or auth.get("payer_raw") or "").strip()
        if not plan_type or plan_type.upper() in ("PRIVATE PAY", "PRIVATE_PAY", "PRIVATE"):
            warnings.append(f"Private pay client {client_name} — no 837 claim generated")
            continue

        if payer_filter and plan_type.lower() != payer_filter.lower():
            continue

        payer_cfg = get_payer_config(plan_type)
        if not payer_cfg:
            warnings.append(f"No payer config for plan '{plan_type}' (client {client_name})")
            continue

        # Skip if missing payer IDs
        if not payer_cfg.get("payer_id", "").strip():
            warnings.append(f"Payer ID missing for {plan_type} — claim blocked for {client_name}")
            continue

        shift = int(att.get("shift", 1) or 1)
        transport = (auth.get("transportation") or "").upper() == "TR"
        member_id = auth.get("member_id") or f"GOJ-{client_name[:8].upper()}"

        dedupe_key = (client_name, log_date_str, plan_type)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        # Resolve payer name to canonical form for clean grouping
        from CC_billing_payers import resolve_payer
        canonical_plan = resolve_payer(plan_type) or plan_type

        # ── Visit claim ──
        visit_rate = payer_cfg.get("rate_visit", 70.0)
        visit_units = payer_cfg.get("units_per_visit", 1)
        svc_code = payer_cfg.get("default_service_code", "T1019")

        claim = {
            "client_name": client_name,
            "subscriber_name": client_name,
            "member_id": member_id,
            "date_of_service": log_date_str,
            "date_of_service_to": log_date_str,
            "units": visit_units,
            "charge": round(visit_units * visit_rate, 2),
            "service_code": svc_code,
            "diagnosis_code": "Z748",
            "claim_id": f"GOJ-{log_date_str}-{client_name[:4].upper()}-VISIT",
            "place_of_service": "11",
            "plan_type": canonical_plan,
            "transport_included": transport,
        }
        claims.append(claim)

        # ── Transport claim (separate, if applicable) ──
        if transport:
            tr_rate = payer_cfg.get("rate_transport", 0.0)
            if tr_rate > 0:
                tr_units = payer_cfg.get("units_per_transport", 2)
                tr_claim = {
                    "client_name": client_name,
                    "subscriber_name": client_name,
                    "member_id": member_id,
                    "date_of_service": log_date_str,
                    "date_of_service_to": log_date_str,
                    "units": tr_units,
                    "charge": round(tr_units * tr_rate, 2),
                    "service_code": "A0425",
                    "diagnosis_code": "Z748",
                    "claim_id": f"GOJ-{log_date_str}-{client_name[:4].upper()}-TRANS",
                    "place_of_service": "11",
                    "plan_type": canonical_plan,
                }
                claims.append(tr_claim)

    # ── Group by payer and generate EDI ──
    by_payer: Dict[str, List[Dict]] = {}
    for c in claims:
        pt = c.get("plan_type", "Unknown")
        by_payer.setdefault(pt, []).append(c)

    edi_by_payer: Dict[str, str] = {}
    for plan_name, plan_claims in by_payer.items():
        try:
            cfg = build_837_config(plan_name)
            edi = generate_837p(plan_claims, cfg)
            edi_by_payer[plan_name] = edi
        except Exception as e:
            warnings.append(f"EDI generation failed for {plan_name}: {e}")

    total_charge = sum(c["charge"] for c in claims)
    summary = {
        "total_claims": len(claims),
        "total_charge": round(total_charge, 2),
        "by_payer": {p: len(cl) for p, cl in by_payer.items()},
        "by_payer_charges": {p: round(sum(c["charge"] for c in cl), 2) for p, cl in by_payer.items()},
        "transport_claims": sum(1 for c in claims if c.get("service_code") == "A0425"),
        "visit_claims": sum(1 for c in claims if c.get("service_code") != "A0425"),
        "unique_clients": len(set(c["client_name"] for c in claims)),
        "warnings": warnings,
        "dry_run": dry_run,
    }

    return {
        "claims": claims,
        "summary": summary,
        "edi_by_payer": edi_by_payer,
        "date_range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
    }


def bill_week(week_start: Optional[date] = None, dry_run: bool = True) -> Dict[str, Any]:
    """
    Convenience: bill the week (Mon–Sat) containing week_start (default: this week).
    """
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday
    # GOJ runs Mon–Sat
    week_end = week_start + timedelta(days=5)  # Saturday
    return build_claims(week_start, week_end, dry_run=dry_run)


def bill_month(year: int, month: int, dry_run: bool = True) -> Dict[str, Any]:
    """Convenience: bill a full calendar month (Mon–Sat only)."""
    start = date(year, month, 1)
    # End of month
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return build_claims(start, end, dry_run=dry_run)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="GOJ Attendance → 837 Claim Bridge")
    parser.add_argument("--week", action="store_true", help="Bill current week (Mon–Sat)")
    parser.add_argument("--month", type=int, nargs=2, metavar=("YEAR", "MONTH"), help="Bill a full month")
    parser.add_argument("--from", dest="from_date", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--payer", type=str, help="Filter to specific payer plan")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Validate only (default)")
    parser.add_argument("--live", action="store_false", dest="dry_run", help="Mark as submitted (DANGER)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--edi", action="store_true", help="Show EDI output per payer")
    args = parser.parse_args()

    if args.month:
        year, month = args.month
        result = bill_month(year, month, dry_run=args.dry_run)
    elif args.week:
        result = bill_week(dry_run=args.dry_run)
    elif args.from_date and args.to_date:
        result = build_claims(
            date.fromisoformat(args.from_date),
            date.fromisoformat(args.to_date),
            payer_filter=args.payer,
            dry_run=args.dry_run,
        )
    else:
        # Default: this week
        result = bill_week(dry_run=args.dry_run)

    if args.json:
        if not args.edi:
            # Strip EDI for cleaner output
            result.pop("edi_by_payer", None)
            result.pop("claims", None)
        print(json.dumps(result, indent=2, default=str))
    else:
        s = result["summary"]
        print(f"=== 837 Claim Bridge — {'DRY RUN' if args.dry_run else 'LIVE'} ===")
        print(f"  Period: {result['date_range']['from']} → {result['date_range']['to']}")
        print(f"  Claims: {s['total_claims']} ({s['visit_claims']} visits + {s['transport_claims']} transport)")
        print(f"  Clients: {s['unique_clients']} unique")
        print(f"  Total: ${s['total_charge']:,.2f}")
        print(f"\n  By Payer:")
        for p, count in s.get("by_payer", {}).items():
            charge = s.get("by_payer_charges", {}).get(p, 0)
            print(f"    {p:30s}  {count:3d} claims  ${charge:,.2f}")

        if s.get("warnings"):
            print(f"\n  Warnings:")
            for w in s["warnings"]:
                print(f"    ⚠ {w}")

        if args.edi:
            print(f"\n=== EDI Output ===")
            for payer, edi in result.get("edi_by_payer", {}).items():
                print(f"\n--- {payer} ---")
                for seg in edi.split("~"):
                    if seg.strip():
                        print(f"  {seg}~")
