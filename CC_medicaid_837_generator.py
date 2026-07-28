#!/usr/bin/env python3
"""
CC_medicaid_837_generator.py — 837P Professional Claim GENERATOR
=================================================================
KEYSTONE of the Tiger Claw billing platform.

Pure-python generator that turns a list of claim dicts into a valid X12
837P (005010X222A1) EDI string. The output is designed to round-trip
cleanly through the LIVE parser at backend/rex_edi.py (parse_837) — that
parser is the ground truth; this generator mirrors the segment ordering
and delimiters of SAMPLE_837P_CLAIMS.edi exactly.

   ~  segment terminator
   *  element separator
   :  component (sub-element) separator

PHASE SCOPE (hard rules):
  • FIXTURES / SYNTHETIC DATA ONLY. No live DB reads. No submission. No PHI.
  • --selftest builds a fake 3-claim dataset and writes /tmp/test_837p.edi.
  • CONFIG placeholders below are flagged "# KATO:" — must be replaced with
    real values before this is ever used against real Medicaid.

WHAT KATO MUST SUPPLY BEFORE REAL USE (see CONFIG):
  • Real billing NPI (10-digit), real Tax ID / EIN
  • Real submitter / receiver EDI trading-partner IDs (payer/clearinghouse)
  • Real payer name + payer ID for each MLTC / Medicaid plan
  • Clearinghouse ISA qualifiers + interchange IDs (ISA05/07 + ISA06/08)
  • Provider taxonomy code (PRV) if different from default

Public API:
  generate_837p(claims: list[dict], config: dict) -> str

CLI:
  python CC_medicaid_837_generator.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Insurance payer config DB (gates real-claim generation) ───────────────────
# auth_tracker.db.insurance_payers holds the billing parameters per MLTC/Medicaid
# plan. A plan must be COMPLETE before any claim can be generated for it. The
# --selftest path is synthetic and NEVER touches this DB (guarded below).
AUTH_TRACKER_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"


# ── Delimiters (must match SAMPLE_837P_CLAIMS.edi exactly) ────────────────────
SEG_TERM = "~"   # segment terminator
ELEM_SEP = "*"   # element separator
COMP_SEP = ":"   # component / sub-element separator


# ── CONFIG (placeholder values flagged for Kato) ──────────────────────────────
# Real values come from env vars (CC837_*) — placeholders are the fallback.
# Clearinghouse = AVAILITY (Kato 2026-06-12). Fill ~/Desktop/REX/.env.837 (see .env.837.example),
# then `set -a; source ~/Desktop/REX/.env.837; set +a` before generating real claims.
def _cfg(env_key: str, placeholder: str) -> str:
    return os.environ.get(env_key, placeholder)

DEFAULT_CONFIG: Dict[str, Any] = {
    # Submitter (1000A) / billing entity
    "submitter_name":      _cfg("CC837_LEGAL_NAME", "TESTORG HOME HEALTH LLC"),   # KATO: real legal name
    "submitter_etin":      _cfg("CC837_SUBMITTER_ETIN", "1234567890"),            # KATO: Availity submitter/ETIN
    "submitter_contact":   "BILLING DEPT",
    "submitter_phone":     _cfg("CC837_BILLING_PHONE", "0000000000"),             # KATO: real billing phone

    # Receiver (1000B) — payer / clearinghouse
    "receiver_name":       _cfg("CC837_PAYER_NAME", "NEW YORK STATE MEDICAID"),
    "receiver_id":         _cfg("CC837_RECEIVER_ID", "AVAILITY"),                 # Availity clearinghouse

    # Billing provider (2000A / 2010AA)
    "billing_name":        _cfg("CC837_LEGAL_NAME", "TESTORG HOME HEALTH LLC"),   # KATO: real legal name
    "billing_npi":         _cfg("CC837_NPI", "9999999999"),                       # KATO: real NPI (incoming)
    "billing_tax_id":      _cfg("CC837_TAX_ID", "00-0000000"),                    # KATO: real Tax ID / EIN
    "billing_taxonomy":    _cfg("CC837_TAXONOMY", "363A00000X"),                  # KATO: confirm provider taxonomy
    "billing_addr1":       _cfg("CC837_ADDR1", "1 TEST STREET"),                  # KATO: real service address
    "billing_city":        _cfg("CC837_CITY", "BROOKLYN"),
    "billing_state":       _cfg("CC837_STATE", "NY"),
    "billing_zip":         _cfg("CC837_ZIP", "11201"),

    # Payer (2000B / 2010BB)
    "payer_name":          _cfg("CC837_PAYER_NAME", "NEW YORK STATE MEDICAID"),   # KATO: real payer name per plan
    "payer_id":            _cfg("CC837_PAYER_ID", "NYSMEDICAID"),                 # KATO: real payer ID per MLTC plan

    # Interchange envelope (ISA/GS)
    "isa_sender_qual":     _cfg("CC837_ISA_SENDER_QUAL", "ZZ"),                   # KATO: Availity-assigned qual
    "isa_sender_id":       _cfg("CC837_ISA_SENDER_ID", "TESTORG"),               # KATO: real ISA sender ID (<=15)
    "isa_receiver_qual":   _cfg("CC837_ISA_RECEIVER_QUAL", "ZZ"),                 # KATO: Availity-assigned qual
    "isa_receiver_id":     _cfg("CC837_ISA_RECEIVER_ID", "AVAILITY"),             # Availity ISA receiver ID
    "isa_usage_indicator": _cfg("CC837_USAGE", "P"),                             # P=production T=test (selftest -> T)
    "gs_app_sender":       _cfg("CC837_GS_SENDER", "TESTORG"),                    # KATO: real GS application sender
    "gs_app_receiver":     _cfg("CC837_GS_RECEIVER", "AVAILITY"),                 # Availity GS receiver

    # Service line defaults
    "default_service_code": "H2015",   # NY MLTC/home-health bundled — parser-recognized
    "default_unit_type":    "UN",
    "place_of_service":     "11",      # 11 = office; 12 = home (set per claim if needed)
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _seg(*elements: str) -> str:
    """Join elements with the element separator + segment terminator."""
    return ELEM_SEP.join(str(e) for e in elements) + SEG_TERM


def _money(val: Any) -> str:
    """Format a numeric charge as a plain dollar string (no commas)."""
    return f"{float(val):.2f}"


def _yyyymmdd(d: str) -> str:
    """
    Normalize a date to YYYYMMDD. Accepts YYYYMMDD, YYYY-MM-DD, MM/DD/YYYY.
    """
    d = str(d).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(d, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    # last resort: strip non-digits
    digits = "".join(ch for ch in d if ch.isdigit())
    if len(digits) == 8:
        return digits
    raise ValueError(f"Unrecognized date format: {d!r}")


def _split_name(full: str) -> tuple[str, str, str]:
    """
    Split a subscriber name into (last, first, middle).
    Accepts 'LAST, FIRST' or 'FIRST LAST' or 'FIRST MIDDLE LAST'.
    """
    full = (full or "").strip()
    if not full:
        return ("DOE", "JOHN", "")
    if "," in full:
        last, rest = full.split(",", 1)
        parts = rest.strip().split()
        first = parts[0] if parts else ""
        middle = parts[1] if len(parts) > 1 else ""
        return (last.strip().upper(), first.upper(), middle.upper())
    parts = full.split()
    if len(parts) == 1:
        return (parts[0].upper(), "", "")
    if len(parts) == 2:
        return (parts[1].upper(), parts[0].upper(), "")
    # FIRST MIDDLE LAST
    return (parts[-1].upper(), parts[0].upper(), parts[1].upper())


def _build_isa(config: Dict[str, Any], control_number: str, now: datetime) -> str:
    """
    Build the fixed-width ISA segment. Mirrors SAMPLE layout: each ISA element
    is space-padded to its X12-mandated width. Segment content (before ~) is
    exactly 105 chars so isa[105] == '~' for the parser's delimiter sniff.
    """
    isa_date = now.strftime("%y%m%d")   # YYMMDD
    isa_time = now.strftime("%H%M")     # HHMM
    fields = [
        "ISA",
        "00",                                              # 01 auth info qual
        " " * 10,                                          # 02 auth info
        "00",                                              # 03 security info qual
        " " * 10,                                          # 04 security info
        config["isa_sender_qual"].ljust(2)[:2],            # 05
        config["isa_sender_id"].ljust(15)[:15],            # 06 (15)
        config["isa_receiver_qual"].ljust(2)[:2],          # 07
        config["isa_receiver_id"].ljust(15)[:15],          # 08 (15)
        isa_date,                                          # 09 date YYMMDD
        isa_time,                                          # 10 time HHMM
        "^",                                               # 11 repetition sep
        "00501",                                           # 12 version
        control_number.rjust(9, "0")[:9],                  # 13 interchange control #
        "0",                                               # 14 ack requested
        config["isa_usage_indicator"][:1],                 # 15 usage P/T
        COMP_SEP,                                           # 16 component sep
    ]
    return ELEM_SEP.join(fields) + SEG_TERM


# ── core generator ────────────────────────────────────────────────────────────

def generate_837p(claims: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """
    Generate a complete 837P EDI string from a list of claim dicts.

    Each claim dict supports:
        client_name / subscriber_name : str  (LAST, FIRST or FIRST LAST)
        member_id                     : str  (Medicaid member ID)
        date_of_service               : str  (YYYYMMDD / YYYY-MM-DD / MM/DD/YYYY)
        date_of_service_to            : str  (optional; defaults to date_of_service)
        units                         : int/float
        charge                        : float (claim + line charge)
        service_code                  : str  (default config['default_service_code'])
        claim_id                      : str  (optional; auto-generated if absent)
        diagnosis_code                : str  (optional ICD-10; default 'Z748')
        addr1/city/state/zip          : str  (optional subscriber address)
        dob                           : str  (optional; default synthetic)
        gender                        : 'M'/'F'/'U' (optional; default 'U')
        place_of_service              : str  (optional; default config)

    Returns the full EDI text (segments separated by '~').
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if not claims:
        raise ValueError("generate_837p requires at least one claim")

    now = datetime.now()
    ctrl = "000000001"                       # interchange/group/set control number
    st_ctrl = "0001"
    date8 = now.strftime("%Y%m%d")
    time4 = now.strftime("%H%M")

    out: List[str] = []

    # ── Interchange + functional group ────────────────────────────────────────
    out.append(_build_isa(cfg, ctrl, now))
    out.append(_seg("GS", "HC", cfg["gs_app_sender"], cfg["gs_app_receiver"],
                    date8, time4, "1", "X", "005010X222A1"))

    # ── Transaction set header (ST..SE). Count segments from ST through SE. ───
    tx: List[str] = []
    tx.append(_seg("ST", "837", st_ctrl, "005010X222A1"))
    tx.append(_seg("BHT", "0019", "00", date8 + time4, date8, time4, "CH"))

    # 1000A Submitter
    tx.append(_seg("NM1", "41", "2", cfg["submitter_name"].upper(),
                   "", "", "", "", "46", cfg["submitter_etin"]))
    tx.append(_seg("PER", "IC", cfg["submitter_contact"].upper(),
                   "TE", cfg["submitter_phone"]))
    # 1000B Receiver
    tx.append(_seg("NM1", "40", "2", cfg["receiver_name"].upper(),
                   "", "", "", "", "46", cfg["receiver_id"]))

    # ── 2000A Billing provider HL ─────────────────────────────────────────────
    hl_counter = 1
    billing_hl = hl_counter
    tx.append(_seg("HL", billing_hl, "", "20", "1"))
    tx.append(_seg("PRV", "BI", "PXC", cfg["billing_taxonomy"]))
    tx.append(_seg("NM1", "85", "2", cfg["billing_name"].upper(),
                   "", "", "", "", "XX", cfg["billing_npi"]))
    tx.append(_seg("N3", cfg["billing_addr1"].upper()))
    tx.append(_seg("N4", cfg["billing_city"].upper(),
                   cfg["billing_state"].upper(), cfg["billing_zip"]))
    tx.append(_seg("REF", "EI", cfg["billing_tax_id"]))

    # ── 2000B Subscriber loops (one HL per claim) ─────────────────────────────
    for idx, claim in enumerate(claims, start=1):
        hl_counter += 1
        subscriber_hl = hl_counter

        name = claim.get("client_name") or claim.get("subscriber_name") or ""
        last, first, middle = _split_name(name)
        member_id = str(claim.get("member_id", "")).strip() or f"MBR{idx:03d}"
        claim_id = str(claim.get("claim_id") or f"CLM-{now.strftime('%Y%m%d')}-{idx:03d}")
        charge = claim.get("charge", 0.0)
        units = claim.get("units", 0)
        svc_code = str(claim.get("service_code") or cfg["default_service_code"]).upper()
        unit_type = cfg["default_unit_type"]
        pos = str(claim.get("place_of_service") or cfg["place_of_service"])
        dx = str(claim.get("diagnosis_code") or "Z748").upper()
        dos_from = _yyyymmdd(claim.get("date_of_service"))
        dos_to = _yyyymmdd(claim.get("date_of_service_to", claim.get("date_of_service")))
        dob = _yyyymmdd(claim.get("dob", "19700101"))
        gender = str(claim.get("gender", "U")).upper()[:1] or "U"

        addr1 = str(claim.get("addr1", "1 PATIENT WAY")).upper()
        city = str(claim.get("city", cfg["billing_city"])).upper()
        state = str(claim.get("state", cfg["billing_state"])).upper()
        zipc = str(claim.get("zip", cfg["billing_zip"]))

        # Subscriber HL (child of billing provider HL)
        tx.append(_seg("HL", subscriber_hl, billing_hl, "22", "0"))
        # SBR — subscriber is the patient (relationship 18 implied), Medicaid
        tx.append(_seg("SBR", "P", "", "MEDICAID", "", "", "", "", "MC"))

        # ── 2300 Claim ────────────────────────────────────────────────────────
        # The LIVE parser (rex_edi.parse_837) only creates `current_claim` on the
        # CLM segment and attaches NM1*IL / NM1*PR to whatever claim is current.
        # CLM is therefore emitted BEFORE the subscriber/payer NM1 loop so those
        # names bind to the correct (current) claim — parser is ground truth.
        # CLM05 = facility code : facility qual : frequency  (e.g. 11:B:1)
        clm05 = f"{pos}{COMP_SEP}B{COMP_SEP}1"
        tx.append(_seg("CLM", claim_id, _money(charge), "", "", clm05,
                       "Y", "A", "Y", "I"))

        # 2010BA Subscriber name (IL) — parser reads [3]last [4]first [9]id
        tx.append(_seg("NM1", "IL", "1", last, first, middle, "", "", "MI", member_id))
        tx.append(_seg("N3", addr1))
        tx.append(_seg("N4", city, state, zipc))
        tx.append(_seg("DMG", "D8", dob, gender))
        # 2010BB Payer (PR) — parser reads [3]name [9]id
        tx.append(_seg("NM1", "PR", "2", cfg["payer_name"].upper(),
                       "", "", "", "", "PI", cfg["payer_id"]))

        # DTP*434 statement date range + HI diagnosis (after claim is established)
        tx.append(_seg("DTP", "434", "RD8", f"{dos_from}-{dos_to}"))
        tx.append(_seg("HI", f"ABK{COMP_SEP}{dx}"))

        # ── 2400 Service line ──────────────────────────────────────────────────
        tx.append(_seg("LX", "1"))
        # SV1 — [1] HC:code [2] charge [3] unit_type [4] units ... [9] dx ptr
        sv1_proc = f"HC{COMP_SEP}{svc_code}"
        tx.append(_seg("SV1", sv1_proc, _money(charge), unit_type,
                       str(units), "", "", "1"))
        # DTP*472 service date — THIS is what parse_837 extracts for dates
        if dos_from == dos_to:
            tx.append(_seg("DTP", "472", "D8", dos_from))
        else:
            tx.append(_seg("DTP", "472", "RD8", f"{dos_from}-{dos_to}"))

    # ── SE trailer: count = ST..SE inclusive ──────────────────────────────────
    se_count = len(tx) + 1   # +1 for the SE segment itself
    tx.append(_seg("SE", str(se_count), st_ctrl))

    out.extend(tx)

    # ── GE / IEA trailers ─────────────────────────────────────────────────────
    out.append(_seg("GE", "1", "1"))
    out.append(_seg("IEA", "1", ctrl.rjust(9, "0")))

    return "".join(out)


# ── payer config: load + readiness + per-plan claim gating ────────────────────

_REQUIRED_PAYER_FIELDS = ("payer_id", "receiver_id", "isa_receiver_id", "gs_receiver")


def _payer_has_rate(service_codes_json: Optional[str]) -> bool:
    """True if service_codes_json holds >=1 service code mapped to a positive
    rate. Accepts {"H2015": 18.5} or {"H2015": {"rate": 18.5}}."""
    if not service_codes_json:
        return False
    try:
        data = json.loads(service_codes_json)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict) or not data:
        return False
    for _code, val in data.items():
        rate = None
        if isinstance(val, (int, float)):
            rate = val
        elif isinstance(val, dict):
            rate = val.get("rate", val.get("amount"))
        elif isinstance(val, str):
            try:
                rate = float(val)
            except ValueError:
                rate = None
        try:
            if rate is not None and float(rate) > 0:
                return True
        except (ValueError, TypeError):
            continue
    return False


def _payer_missing_fields(row: Dict[str, Any]) -> List[str]:
    """missing required billing fields for a payer row dict. Non-billable plans
    (billable=0) are never required -> always []."""
    if not int(row.get("billable", 1) or 0):
        return []
    missing: List[str] = []
    for f in _REQUIRED_PAYER_FIELDS:
        if not str(row.get(f) or "").strip():
            missing.append(f)
    sub = str(row.get("submission_method") or "").strip().lower()
    if not sub or sub == "pending":
        missing.append("submission_method")
    if not _payer_has_rate(row.get("service_codes_json")):
        missing.append("service_codes_json")
    return missing


def payer_config_for(plan_name: str,
                     db_path: Path = AUTH_TRACKER_DB) -> Optional[Dict[str, Any]]:
    """Return the insurance_payers row for plan_name as a dict, or None if the
    plan is unknown or the DB is unavailable. Read-only, parameterized."""
    if not plan_name or not Path(db_path).exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            r = con.execute(
                "SELECT * FROM insurance_payers WHERE plan_name=?", (plan_name,)
            ).fetchone()
            return dict(r) if r is not None else None
        finally:
            con.close()
    except Exception:
        return None


def build_claim_for_plan(claim: Dict[str, Any], plan_name: str,
                         db_path: Path = AUTH_TRACKER_DB) -> Dict[str, Any]:
    """Generate an 837P for a single claim under plan_name — BUT block if the
    plan's billing parameters are incomplete.

    Returns either:
      {"blocked": True, "reason": "...", "plan": plan_name, "missing_fields":[...]}
        when the plan is missing/incomplete/has a blank payer_id  (NO EDI emitted)
      {"blocked": False, "plan": plan_name, "payer_id": "...", "edi": "<837P>"}
        when complete — config is overridden from the row and EDI is generated.
    """
    row = payer_config_for(plan_name, db_path=db_path)
    blocked_reason = (
        f"Missing billing parameters for plan '{plan_name}' — "
        f"fill them in the Insurance Params screen"
    )
    if row is None:
        return {"blocked": True, "reason": blocked_reason, "plan": plan_name,
                "missing_fields": ["<plan not configured>"]}
    if not int(row.get("complete", 0) or 0) or not str(row.get("payer_id") or "").strip():
        return {"blocked": True, "reason": blocked_reason, "plan": plan_name,
                "missing_fields": _payer_missing_fields(row)}

    # Complete -> override config from the row and generate normally.
    config = _config_from_payer_row(row)
    edi = generate_837p([claim], config)
    return {"blocked": False, "plan": plan_name,
            "payer_id": row.get("payer_id"), "edi": edi}


def _config_from_payer_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map an insurance_payers row onto generator CONFIG overrides. Only fields
    present + non-empty in the row override DEFAULT_CONFIG."""
    cfg: Dict[str, Any] = {}
    if str(row.get("payer_name") or "").strip():
        cfg["payer_name"] = row["payer_name"]
        cfg["receiver_name"] = row["payer_name"]
    if str(row.get("payer_id") or "").strip():
        cfg["payer_id"] = row["payer_id"]
    if str(row.get("receiver_id") or "").strip():
        cfg["receiver_id"] = row["receiver_id"]
    if str(row.get("isa_receiver_id") or "").strip():
        cfg["isa_receiver_id"] = row["isa_receiver_id"]
    if str(row.get("gs_receiver") or "").strip():
        cfg["gs_app_receiver"] = row["gs_receiver"]
    if str(row.get("billing_npi_override") or "").strip():
        cfg["billing_npi"] = row["billing_npi_override"]
    # First service code with a positive rate becomes the default service code.
    try:
        codes = json.loads(row.get("service_codes_json") or "{}")
        if isinstance(codes, dict):
            for code, val in codes.items():
                rate = val if isinstance(val, (int, float)) else (
                    val.get("rate", val.get("amount")) if isinstance(val, dict) else None)
                if rate is not None and float(rate) > 0:
                    cfg["default_service_code"] = str(code).upper()
                    break
    except (ValueError, TypeError, AttributeError):
        pass
    return cfg


def claim_readiness(db_path: Path = AUTH_TRACKER_DB) -> Dict[str, Any]:
    """Mirror of the /api/goj/insurance-payers/readiness endpoint, read from the
    table. {"ready_count","blocked_count","total","plans":[...]}."""
    if not Path(db_path).exists():
        return {"ready_count": 0, "blocked_count": 0, "total": 0, "plans": [],
                "error": "auth_tracker.db not found"}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM insurance_payers ORDER BY plan_name ASC").fetchall()]
    finally:
        con.close()
    plans = []
    ready_count = blocked_count = 0
    for row in rows:
        billable = int(row.get("billable", 1) or 0)
        missing = _payer_missing_fields(row)
        complete = (len(missing) == 0)
        readiness = ("non-billable" if not billable
                     else ("ready" if complete else "blocked"))
        if readiness == "blocked":
            blocked_count += 1
        else:
            ready_count += 1
        plans.append({"plan_name": row["plan_name"],
                      "complete": 1 if complete else 0,
                      "missing_fields": missing, "readiness": readiness})
    return {"ready_count": ready_count, "blocked_count": blocked_count,
            "total": len(plans), "plans": plans}


# ── self-test fixtures ────────────────────────────────────────────────────────

def _synthetic_claims() -> List[Dict[str, Any]]:
    """Three obviously-fake claims for round-trip verification."""
    return [
        {
            "client_name": "TESTCLIENT ALPHA",
            "member_id": "AA00000001",
            "date_of_service": "20260301",
            "date_of_service_to": "20260315",
            "units": 240,
            "charge": 1200.00,
            "service_code": "H2015",
            "diagnosis_code": "Z748",
            "dob": "19680415",
            "gender": "F",
            "claim_id": "TEST-CLM-001",
        },
        {
            "client_name": "TESTCLIENT BRAVO",
            "member_id": "BB00000002",
            "date_of_service": "20260308",
            "date_of_service_to": "20260315",
            "units": 85,
            "charge": 850.00,
            "service_code": "T1020",
            "diagnosis_code": "I10",
            "dob": "19520703",
            "gender": "M",
            "claim_id": "TEST-CLM-002",
        },
        {
            "client_name": "TESTCLIENT CHARLIE",
            "member_id": "CC00000003",
            "date_of_service": "20260301",
            "date_of_service_to": "20260331",
            "units": 420,
            "charge": 2100.00,
            "service_code": "T1019",
            "diagnosis_code": "G30",
            "dob": "19450922",
            "gender": "F",
            "claim_id": "TEST-CLM-003",
        },
    ]


def _selftest() -> int:
    out_path = "/tmp/test_837p.edi"
    cfg = {**DEFAULT_CONFIG, "isa_usage_indicator": "T"}   # T = test interchange
    edi = generate_837p(_synthetic_claims(), cfg)
    with open(out_path, "w") as f:
        f.write(edi)

    print("=" * 70)
    print(f"[1] SELFTEST — wrote {out_path}")
    print("=" * 70)
    # print one segment per line for readability
    for seg in edi.split(SEG_TERM):
        if seg:
            print(seg + SEG_TERM)
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="837P Professional claim generator (fixtures only)")
    parser.add_argument("--selftest", action="store_true",
                        help="Generate synthetic 3-claim 837P to /tmp/test_837p.edi")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
