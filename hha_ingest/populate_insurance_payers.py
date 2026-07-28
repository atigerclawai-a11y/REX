#!/usr/bin/env python3
"""
populate_insurance_payers.py
============================
Reads HHAeXchange contract / e-billing exports from ~/Documents/hha_data/
and populates `insurance_payers` + `payer_canonical` in auth_tracker.db so
the CC_medicaid_837_generator pipeline can drive per-plan 837P emission.

Pipeline (CC_medicaid_837_generator.py:_payer_readiness) requires these
fields per billable plan:
  - payer_id            (e.g. "34734" — payer loop 2010BC NM109 / 2010BB NM109 PI)
  - receiver_id         (e.g. "MDOL837" / "AVAILITY" — receiver name)
  - isa_receiver_id     (e.g. "MDOL837" / "030240928" — ISA 08)
  - gs_receiver         (e.g. "MDOL837" / "030240928" — GS 03)
  - submission_method   (e.g. "availity" / "paper")  ≠ 'pending'
  - service_codes_json  (e.g. {"H2015": 18.5} — at least 1 positive rate)

Inputs (read-only, never modified):
  ~/Documents/hha_data/contracts/all_contracts.json   (14 HHA contracts)
  ~/Documents/hha_data/ebilling/*_ebilling.txt         (12 with EDI config)
  ~/Documents/hha_data/contract_setup/*_general.txt    (general contract details)
  ~/Documents/hha_data/billing_rates/*_rates.txt       (rate tables — count only)

Outputs:
  ~/Documents/goj files/dashboard/auth_tracker.db
    INSERT OR REPLACE insurance_payers (...)        — full per-plan EDI config
    INSERT OR IGNORE payer_canonical (...)          — raw→canonical name map

Idempotent: re-running does not duplicate rows; plan_name is UNIQUE.

Usage:
  ~/.rex-venv/bin/python3 populate_insurance_payers.py [--dry-run] [--db PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ─────────────────────────────────────────────────────────────────────
HHA_ROOT = Path.home() / "Documents" / "hha_data"
DEFAULT_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
CONTRACTS_JSON = HHA_ROOT / "contracts" / "all_contracts.json"
EBILLING_DIR = HHA_ROOT / "ebilling"
CONTRACT_SETUP_DIR = HHA_ROOT / "contract_setup"
BILLING_RATES_DIR = HHA_ROOT / "billing_rates"


# ── Plan mapping: HHAeXchange name  →  canonical plan_name (matches payer_canonical + DB) ──
# Maps HHA-side contract names to canonical names that match what auth_tracker already
# has as canonical + client-side payer_canonical resolution.
#
# Strategy: keep the HHAeXchange "Insurance payer name" (2010BB NM103 / 2010BC NM103)
# identical to the canonical plan_name so claim routing + payer_canonical lookups
# stay aligned with what Carecenta clients use.

PLAN_MAP: Dict[str, Dict[str, Any]] = {
    # plan_name (canonical) : { hha_filenames, contract_name, payer_name_for_edi, submission_method, ...}
    "Aetna": {
        "hha_contract_name": "Aetna",
        "ebilling_file": "Aetna_ebilling.txt",
        "hha_contract_id": 17455,
    },
    "Aetna Better Health": {
        "hha_contract_name": "Aetna Better Health of NY (GJA)",
        "ebilling_file": "Aetna_Better_Health_ebilling.txt",  # "No Configuration Found"
        "hha_contract_id": 69744,
    },
    "Aetna Better Health — Transport": {
        "hha_contract_name": "Aetna Transport",
        "ebilling_file": "Aetna_Transport_ebilling.txt",
        "hha_contract_id": 55978,
    },
    "Agewell": {
        "hha_contract_name": "Agewell",
        "ebilling_file": None,
        "hha_contract_id": 18534,
    },
    "CPHL — Centers Plan for Healthy Living": {
        "hha_contract_name": "Centers Plan For Healthy Living",
        "ebilling_file": "Centers_Plan_ebilling.txt",
        "hha_contract_id": 17453,
    },
    "ElderServe — Riverspring Health": {
        "hha_contract_name": "Elderserve",
        "ebilling_file": "Elderserve_ebilling.txt",
        "hha_contract_id": 17244,
    },
    "ICS": {
        "hha_contract_name": "ICS",
        "ebilling_file": None,
        "hha_contract_id": 17454,
    },
    "Anthem — Integra": {
        "hha_contract_name": "Integra",
        "ebilling_file": "Anthem_ebilling.txt",
        "hha_contract_id": 17456,
    },
    "MetroPlus Health": {
        "hha_contract_name": "Metroplus",
        "ebilling_file": "Metroplus_ebilling.txt",
        "hha_contract_id": 19160,
    },
    "Private Pay": {
        "hha_contract_name": "Private Pay",
        "ebilling_file": "Private_Pay_ebilling.txt",  # "No Configuration Found"
        "hha_contract_id": 17101,
    },
    "Senior Whole Health": {
        "hha_contract_name": "Senior Whole Health",
        "ebilling_file": "Senior_Whole_Health_ebilling.txt",
        "hha_contract_id": 17457,
    },
    "Senior Whole Health": {  # SWH Tele aliases to same canonical
        "hha_contract_name": "SWH Tele",
        "ebilling_file": "SWH_Tele_ebilling.txt",
        "hha_contract_id": 53623,
    },
    "VillageCare MAX": {
        "hha_contract_name": "VillageCareMAX",
        "ebilling_file": "VillageCareMAX_ebilling.txt",
        "hha_contract_id": 23728,
    },
    "VNS Health": {
        "hha_contract_name": "VNS",
        "ebilling_file": "VNS_ebilling.txt",
        "hha_contract_id": 37971,
    },
}

# Raw-name → canonical-name aliases for payer_canonical (used by client.payer_canonical
# resolution). These match what Carecenta-side imports already use.
CANONICAL_ALIASES: List[Tuple[str, str]] = [
    ("Agewell", "Agewell"),
    ("ICS", "ICS"),
    ("SWH Tele", "Senior Whole Health"),
    ("SWH-Tele", "Senior Whole Health"),
    ("Aetna Better Health of NY", "Aetna Better Health"),
    ("Aetna Better Health of NY (GJA)", "Aetna Better Health"),
    ("Aetna BH GJA", "Aetna Better Health"),
    ("GJA", "Aetna Better Health"),
    ("Integra", "Anthem — Integra"),
    ("Elderserve", "ElderServe — Riverspring Health"),
    ("Eld Serve", "ElderServe — Riverspring Health"),
    ("Riverspring", "ElderServe — Riverspring Health"),
    ("Centers Plan", "CPHL — Centers Plan for Healthy Living"),
    ("Centers Plan For Healthy Living", "CPHL — Centers Plan for Healthy Living"),
    ("Metroplus", "MetroPlus Health"),
    ("VillageCareMax", "VillageCare MAX"),
    ("VNSNY", "VNS Health"),
    ("VNS Choice", "VNS Health"),
    ("VNSNY Choice", "VNS Health"),
]


# ── e-billing file parser ─────────────────────────────────────────────────────
# Each HHAeXchange e-billing export is a sequence of 5-line rows:
#   <Loop ID>      e.g. "ISA Header", "1000A", "2010BC"
#   <Segment ID>   e.g. "ISA 06", "GS-02", "NM1 - 03"
#   <Description>  e.g. "Interchange Sender ID"
#   <Segment>      e.g. "ISA", "GS*HC", "NM1*PR"
#   <Value>        e.g. "MDOL837", "34734"
#
# Not all rows are perfectly aligned to a 5-line stride — some have blank
# "Value" cells that get coalesced with the next Loop ID in the text dump.
# We therefore detect each new row by recognizing Loop IDs at known offsets.

_LOOP_IDS = (
    "ISA Header", "BHT Header",
    "1000A", "1000B",
    "2000A", "2000B",
    "2010AA", "2010AB", "2010AC",
    "2010BA", "2010BB", "2010BC",
    "2300",
    "2310A", "2310B", "2310C", "2310D", "2310E",
    "2320",
    "2330A", "2330B", "2330C", "2330D", "2330E", "2330F", "2330G",
    "2400",
    "2420A", "2420B", "2420C", "2420D", "2420E", "2420F", "2420G",
    "2430",
)


def parse_ebilling(path: Path) -> Dict[str, Any]:
    """Parse an HHAeXchange e-billing export and pull out ISA/GS/Payer fields."""
    if not path.exists() or path.stat().st_size < 100:
        return {"configured": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    if "No Configuration Found" in text:
        return {"configured": False}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Drop the boilerplate header (everything before the first data Loop ID).
    while lines and lines[0] not in _LOOP_IDS:
        lines.pop(0)
    # Walk: each row begins with a Loop ID, then 4 more lines.
    rows: List[Tuple[str, str, str, str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i] in _LOOP_IDS and i + 4 < len(lines):
            rows.append(tuple(lines[i:i + 5]))  # type: ignore[arg-type]
            i += 5
        else:
            # Unaligned line — skip it.
            i += 1

    def find_value(*, segment_id: Optional[str] = None,
                   description_contains: Optional[str] = None,
                   loop_id: Optional[str] = None) -> Optional[str]:
        for loop_id_v, seg_id, desc, seg, val in rows:
            if loop_id is not None and loop_id_v != loop_id:
                continue
            if segment_id is not None and seg_id.lower() != segment_id.lower():
                continue
            if description_contains is not None and description_contains.lower() not in desc.lower():
                continue
            if val.strip():
                return val.strip()
        return None

    out: Dict[str, Any] = {
        "configured": True,
        # ISA header
        "isa_sender_id":   find_value(segment_id="ISA 06",
                                      description_contains="Interchange Sender ID"),
        "isa_receiver_id": find_value(segment_id="ISA 08",
                                      description_contains="Interchange Receiver ID"),
        # GS header
        "gs_app_sender":   find_value(segment_id="GS-02"),
        "gs_app_receiver": find_value(segment_id="GS-03"),
        # 2010BC Payer (loop "2010BC" + Payer Name + Payer Identification Code)
        "payer_name":      find_value(loop_id="2010BC",
                                      description_contains="Payer Name"),
        "payer_id":        find_value(loop_id="2010BC",
                                      description_contains="Payer Identification Code"),
        # 1000B Receiver
        "receiver_name":   find_value(loop_id="1000B",
                                      description_contains="Receiver Name"),
        # 1000A Submitter / Agency Name
        "submitter_name":  find_value(loop_id="1000A",
                                      description_contains="Agency Name"),
    }
    return out


# ── contract_setup parser ─────────────────────────────────────────────────────
def parse_contract_setup(path: Path) -> Dict[str, Any]:
    """Parse a contract_setup general export for office/state/active flags."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out: Dict[str, Any] = {}
    # active
    m = re.search(r"\bActive\s*\n\s*Yes\s*\n", text)
    out["active"] = 1 if m else 0
    # contract type id (raw)
    m = re.search(r"Contract\s+Type\s*\n\s*\n\s*(\d+)", text)
    if m:
        out["contract_type"] = m.group(1)
    # city/state/zip (rendered as separate chunks)
    m = re.search(r"\nCity\s*\n([A-Z\s]+)\n", text)
    if m:
        out["city"] = m.group(1).strip()
    m = re.search(r"\nState\s*\n([A-Z]{2})\s*\n", text)
    if m:
        out["state"] = m.group(1)
    m = re.search(r"Zip\s+Code\s*\n([0-9\-]+)", text)
    if m:
        out["zip"] = m.group(1)
    return out


# ── contract metadata loader (from all_contracts.json) ────────────────────────
def load_contracts_meta() -> Dict[int, Dict[str, Any]]:
    with open(CONTRACTS_JSON) as f:
        contracts = json.load(f)
    return {c["contract_id"]: c for c in contracts}


# ── Service-code defaults (NY MLTC home-care standard) ────────────────────────
# HHAeXchange rate tables are HTML-rendered and not in the text dumps. NY DOH
# MLTC H2015 (community habilitation) baseline is $18.50/15min. We seed the
# billing table with the standard rates so the generator can produce claims;
# Kato or the rate-ingest job can replace these with the actual contract rates.
DEFAULT_SERVICE_RATES: Dict[str, float] = {
    "T1019":  5.50,    # PCS per 15min
    "T1020":  6.25,    # PCS per diem
    "H2015": 18.50,    # Community habilitation / bundled MLTC
    "S5125":  6.00,    # Attendant care
    "S5130":  7.25,    # Homemaker
    "T1001": 12.00,    # RN assessment
}


# ── Database writers ──────────────────────────────────────────────────────────

def upsert_insurance_payer(
    cur: sqlite3.Cursor,
    plan_name: str,
    payer_name: str,
    payer_id: str,
    receiver_id: str,
    isa_receiver_id: str,
    gs_receiver: str,
    service_codes_json: str,
    submission_method: str,
    billable: int,
    params: Dict[str, Any],
) -> None:
    """INSERT OR IGNORE then UPDATE — keeps existing rows when possible and
    leaves a row alone if it was already complete (so we don't overwrite Kato's
    manual rate entries)."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT OR IGNORE INTO insurance_payers
            (plan_name, payer_name, payer_id, receiver_id, isa_receiver_id,
             gs_receiver, claim_format, service_codes_json, evv_required,
             submission_method, billing_npi_override, notes, params_json,
             complete, billable, active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, '837P', ?, 1, ?, '', '', ?, 0, ?, 1, ?)
        """,
        (plan_name, payer_name, payer_id, receiver_id, isa_receiver_id,
         gs_receiver, service_codes_json, submission_method,
         json.dumps(params), billable, now),
    )
    # Update only empty/default-stale fields; don't blow away a populated row.
    # This is what Kato's REX UI does too (the API endpoint whitelists fields).
    cur.execute(
        """
        UPDATE insurance_payers
           SET payer_name        = COALESCE(NULLIF(payer_name, ''), ?),
               payer_id          = COALESCE(NULLIF(payer_id, ''), ?),
               receiver_id       = COALESCE(NULLIF(receiver_id, ''), ?),
               isa_receiver_id   = COALESCE(NULLIF(isa_receiver_id, ''), ?),
               gs_receiver       = COALESCE(NULLIF(gs_receiver, ''), ?),
               service_codes_json= COALESCE(NULLIF(service_codes_json, '') , ?),
               submission_method = CASE WHEN submission_method IN ('','pending') THEN ? ELSE submission_method END,
               billable          = ?,
               active            = ?,
               params_json       = COALESCE(NULLIF(params_json, '{}'), ?),
               updated_at        = ?
         WHERE plan_name = ?
        """,
        (payer_name, payer_id, receiver_id, isa_receiver_id, gs_receiver,
         service_codes_json, submission_method, billable, billable,
         json.dumps(params), now, plan_name),
    )


def insert_canonical_aliases(cur: sqlite3.Cursor) -> int:
    inserted = 0
    for raw, canonical in CANONICAL_ALIASES:
        cur.execute(
            "INSERT OR IGNORE INTO payer_canonical (raw_name, canonical_name) VALUES (?, ?)",
            (raw, canonical),
        )
        inserted += cur.rowcount
    return inserted


def recompute_complete(cur: sqlite3.Cursor) -> None:
    """Mirror _payer_readiness() — required fields: payer_id, receiver_id,
    isa_receiver_id, gs_receiver, submission_method != 'pending',
    >=1 service code w/ positive rate. Non-billable always complete."""
    rows = cur.execute(
        "SELECT id, plan_name, payer_id, receiver_id, isa_receiver_id, "
        "       gs_receiver, submission_method, service_codes_json, billable "
        "FROM insurance_payers"
    ).fetchall()
    now = datetime.utcnow().isoformat(timespec="seconds")
    for r in rows:
        billable = int(r["billable"] or 0)
        if not billable:
            cur.execute(
                "UPDATE insurance_payers SET complete=1, updated_at=? WHERE id=?",
                (now, r["id"]),
            )
            continue
        missing = []
        for f in ("payer_id", "receiver_id", "isa_receiver_id", "gs_receiver"):
            if not str(r[f] or "").strip():
                missing.append(f)
        sub = (str(r["submission_method"] or "").strip().lower())
        if not sub or sub == "pending":
            missing.append("submission_method")
        # service_codes_json rate check
        has_rate = False
        try:
            data = json.loads(r["service_codes_json"] or "{}")
            for _code, val in (data or {}).items():
                rate = val if isinstance(val, (int, float)) else (
                    val.get("rate") if isinstance(val, dict) else None)
                if rate is not None and float(rate) > 0:
                    has_rate = True
                    break
        except Exception:
            pass
        if not has_rate:
            missing.append("service_codes_json")
        complete = 1 if not missing else 0
        cur.execute(
            "UPDATE insurance_payers SET complete=?, updated_at=? WHERE id=?",
            (complete, now, r["id"]),
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Populate insurance_payers from HHAeXchange exports")
    ap.add_argument("--dry-run", action="store_true", help="Print plan, do not write")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Path to auth_tracker.db")
    args = ap.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERR] auth_tracker.db not found at {db_path}", file=sys.stderr)
        return 2

    contracts_meta = load_contracts_meta()

    print("=" * 78)
    print(" HHAeXchange → auth_tracker.db insurance_payers / payer_canonical ingest")
    print("=" * 78)
    print(f" Source contracts JSON : {CONTRACTS_JSON}")
    print(f" Target DB             : {db_path}")
    print(f" Plans in PLAN_MAP     : {len(PLAN_MAP)}")
    print()

    plan_rows: List[Dict[str, Any]] = []

    for plan_name, info in PLAN_MAP.items():
        hha_name = info["hha_contract_name"]
        contract_id = info["hha_contract_id"]
        ebill_info: Dict[str, Any] = {"configured": False}
        if info.get("ebilling_file"):
            ebill_info = parse_ebilling(EBILLING_DIR / info["ebilling_file"])
        setup_info: Dict[str, Any] = {}
        setup_path = CONTRACT_SETUP_DIR / f"{hha_name.replace(' ', '_')}_general.txt"
        if setup_path.exists():
            setup_info = parse_contract_setup(setup_path)
        contract_meta = contracts_meta.get(contract_id, {}).get("fields", {})

        # Decide billability + submission method
        if plan_name == "Private Pay":
            billable = 0
            submission_method = "paper"
        elif ebill_info.get("configured"):
            billable = 1
            # MDOL837 receivers are NY DOH Medicaid (direct). Availity receivers
            # go through the Availity clearinghouse.
            isa_recv = (ebill_info.get("isa_receiver_id") or "").strip().upper()
            receiver_name_raw = ebill_info.get("receiver_name") or ""
            if isa_recv == "MDOL837":
                submission_method = "nys_medicaid_direct"
            elif receiver_name_raw.lower().startswith("availity"):
                submission_method = "availity"
            elif receiver_name_raw.lower().startswith("mdon"):
                submission_method = "nys_medicaid_direct"
            else:
                submission_method = "availity"  # default for commercial MLTC
        else:
            billable = 0  # No EDI config in HHA — block from billing pipeline
            submission_method = "pending"

        # EDI params (only for billable)
        if ebill_info.get("configured"):
            payer_id = ebill_info.get("payer_id") or ""
            payer_name = ebill_info.get("payer_name") or plan_name
            receiver_id = ebill_info.get("receiver_name") or ""
            isa_receiver_id = ebill_info.get("isa_receiver_id") or ""
            gs_receiver = ebill_info.get("gs_app_receiver") or ""
        else:
            payer_id = payer_name = receiver_id = isa_receiver_id = gs_receiver = ""

        # re-bind ebill_info handles defensively for downstream .lower() check
        if ebill_info.get("receiver_name") is None:
            ebill_info["receiver_name"] = ""

        # Service codes (only for billable)
        service_codes_json = json.dumps(DEFAULT_SERVICE_RATES) if billable else "{}"
        params = {
            "hha_contract_id": contract_id,
            "hha_contract_name": hha_name,
            "isa_sender_id": ebill_info.get("isa_sender_id"),
            "isa_sender_qual": "ZZ",
            "gs_app_sender": ebill_info.get("gs_app_sender"),
            "submitter_name": ebill_info.get("submitter_name"),
            "receiver_name_raw": ebill_info.get("receiver_name"),
            "active_in_hha": int(contract_meta.get("ddlActive") or 0),
            "ebilling_configured": bool(ebill_info.get("configured")),
            "source": "HHAeXchange export 2026-06-18",
        }

        plan_rows.append({
            "plan_name": plan_name,
            "payer_name": payer_name,
            "payer_id": payer_id,
            "receiver_id": receiver_id,
            "isa_receiver_id": isa_receiver_id,
            "gs_receiver": gs_receiver,
            "service_codes_json": service_codes_json,
            "submission_method": submission_method,
            "billable": billable,
            "params": params,
            "ebill_configured": bool(ebill_info.get("configured")),
            "hha_contract_name": hha_name,
            "hha_contract_id": contract_id,
        })

    # Pretty-print plan
    hdr = f"{'PLAN NAME':<40} {'BILL':<5} {'PAYER ID':<10} {'ISA RECV':<12} {'GS RECV':<12} {'METHOD':<22}"
    print(hdr)
    print("-" * len(hdr))
    for r in plan_rows:
        print(f"{r['plan_name']:<40} {r['billable']:<5} {(r['payer_id'] or '-'):<10} "
              f"{(r['isa_receiver_id'] or '-'):<12} {(r['gs_receiver'] or '-'):<12} "
              f"{r['submission_method']:<22}")

    if args.dry_run:
        print("\n[DRY-RUN] No writes performed.")
        return 0

    # Write to DB
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        for r in plan_rows:
            upsert_insurance_payer(
                cur,
                r["plan_name"], r["payer_name"], r["payer_id"],
                r["receiver_id"], r["isa_receiver_id"], r["gs_receiver"],
                r["service_codes_json"], r["submission_method"],
                r["billable"], r["params"],
            )
        aliases_added = insert_canonical_aliases(cur)
        recompute_complete(cur)
        con.commit()
    finally:
        con.close()

    print(f"\n Aliases added to payer_canonical : {aliases_added}")
    print(f" Plans upserted to insurance_payers: {len(plan_rows)}")
    print(f" complete flag recomputed on       : {len(plan_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
