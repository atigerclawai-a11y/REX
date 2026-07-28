"""
rex_edi.py — 837 / 835 EDI Receiver & Interpreter
====================================================
Handles the two most critical EDI transaction sets for a Medicaid
home health agency like Gold Health Systems / GOJ:

  837P  — Professional Claim Submission
          (what GOJ sends to Medicaid to bill for HHA / CDPAP services)

  835   — Electronic Remittance Advice (ERA)
          (what Medicaid sends back: payments, denials, adjustments)

Usage:
  from backend.rex_edi import parse_837, parse_835, EDIInterpreter
  result = parse_835(open('remittance.835').read())

API endpoints (registered in main.py):
  POST /api/edi/upload          — Upload an 837 or 835 file for parsing
  GET  /api/edi/claims          — List parsed 837 claims
  GET  /api/edi/remittances     — List parsed 835 remittances
  GET  /api/edi/summary         — Revenue summary (billed vs paid vs denied)
  POST /api/edi/match           — Match 835 payments to 837 claims

EDI 837/835 basics:
  • Files are pipe-delimited or ~ delimited segments
  • Each segment starts with a 2-3 letter identifier
  • ISA = interchange envelope, GS = functional group, ST = transaction set
  • 837: CLM = claim, NM1 = name/ID, SV1 = service line, DTP = date
  • 835: CLP = claim payment, SVC = service payment, CAS = adjustment, PLB = provider adj
"""

import re
import json
import logging
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger("rex.edi")

# ── EDI parsing utilities ─────────────────────────────────────────────────────

def _detect_delimiters(raw: str) -> Tuple[str, str, str]:
    """
    Extract delimiters from ISA segment.
    ISA is always 106 chars: positions 3=element, 104=subelement, 105=segment terminator.
    Returns (element_sep, subelement_sep, segment_terminator)
    """
    isa_start = raw.find("ISA")
    if isa_start == -1:
        return ("|", ":", "~")   # defaults
    isa = raw[isa_start:isa_start+106]
    element_sep     = isa[3]   if len(isa) > 3   else "|"
    subelement_sep  = isa[104] if len(isa) > 104 else ":"
    segment_term    = isa[105] if len(isa) > 105 else "~"
    return (element_sep, subelement_sep, segment_term)


def _split_segments(raw: str) -> List[List[str]]:
    """Split EDI text into segments, then each segment into elements."""
    elem_sep, sub_sep, seg_term = _detect_delimiters(raw)
    # Normalize line endings
    raw = raw.replace("\r\n", "").replace("\r", "").replace("\n", "")
    segments = []
    for seg in raw.split(seg_term):
        seg = seg.strip()
        if seg:
            elements = seg.split(elem_sep)
            segments.append(elements)
    return segments


def _el(seg: List[str], idx: int, default: str = "") -> str:
    """Safely get element from a segment."""
    try:
        return (seg[idx] or "").strip()
    except IndexError:
        return default


def _date(yyyymmdd: str) -> str:
    """Format 8-digit date YYYYMMDD → MM/DD/YYYY for display."""
    if len(yyyymmdd) == 8:
        try:
            return f"{yyyymmdd[4:6]}/{yyyymmdd[6:8]}/{yyyymmdd[:4]}"
        except Exception:
            pass
    return yyyymmdd


def _money(val: str) -> float:
    """Parse a dollar string to float."""
    try:
        return round(float(val.replace(",", "")), 2)
    except Exception:
        return 0.0


# ── Service codes commonly used in home health ────────────────────────────────

SERVICE_DESCRIPTIONS = {
    "T1019": "Personal Care Services",
    "T1020": "CDPAP — Consumer Directed Personal Assistance",
    "T1021": "Home Health Aide (HHA) — Per Visit",
    "S9122": "Home Health Aide (HHA) — Per Hour",
    "G0154": "Direct Skilled Nursing — 15-min increment",
    "G0156": "Home Health Aide — Medicaid",
    "G0299": "Direct Skilled Nursing (per visit)",
    "S9123": "Nursing Care — RN",
    "S9124": "Nursing Care — LPN",
    "99341": "Home Visit — New Patient (Low complexity)",
    "99342": "Home Visit — New Patient (Moderate complexity)",
    "W7310": "CDPAP Fiscal Intermediary Services",
    "W1771": "Home Health Aide — Medicaid MLTC",
    # Transportation
    "A0100": "Non-Emergency Medical Transport — Taxi",
    "A0080": "Non-Emergency Medical Transport — Per Mile",
    # Common rejection codes
}

ADJUSTMENT_REASON_CODES = {
    "1":   "Deductible amount",
    "2":   "Coinsurance amount",
    "3":   "Co-payment amount",
    "4":   "Late filing penalty",
    "16":  "Claim/service lacks info or has submission/billing error",
    "18":  "Duplicate claim/service",
    "22":  "This care may be covered by another payer",
    "23":  "Charges exceed your contracted/legislated fee arrangement",
    "26":  "Expenses incurred prior to coverage",
    "27":  "Expenses incurred after coverage terminated",
    "29":  "Claim denied — limit reached",
    "31":  "Patient not eligible on DOS",
    "45":  "Charges exceed fee schedule/maximum allowable",
    "50":  "Non-covered service",
    "55":  "Procedure code/modifier mismatch",
    "56":  "Prior authorization absent",
    "57":  "Prior authorization expired",
    "58":  "Service not authorized",
    "96":  "Non-covered charge(s)",
    "97":  "Payment already adjusted",
    "109": "Claim not covered by this payer — routing error",
    "110": "Billing date predates service date",
    "119": "Benefit maximum for this time period has been reached",
    "150": "Payer deems information submitted does not support this service",
    "151": "Payment adjusted because claim/service was not reasonable/necessary",
    "170": "Payment is denied when performed/billed by this type of provider",
    "226": "Information requested from the member was not provided",
    "252": "Prior authorization required",
    "B7":  "Provider was not certified/eligible on DOS",
    "CO":  "Contractual obligation — plan adj",
    "OA":  "Other adjustment",
    "PI":  "Payer initiated reduction",
    "PR":  "Patient responsibility",
}

CLAIM_STATUS_CODES = {
    "1":  "Processed as Primary",
    "2":  "Processed as Secondary",
    "3":  "Processed as Tertiary",
    "4":  "Denied",
    "19": "Processed as Primary — Forward to Secondary",
    "20": "Processed as Secondary — Forward to Tertiary",
    "21": "Reverse of Previous Payment",
    "22": "Reversal of Previous Payment",
    "23": "Not our Claim — Forwarded to another payer",
}


# ── 837 Parser ────────────────────────────────────────────────────────────────

def parse_837(raw: str) -> Dict[str, Any]:
    """
    Parse an 837P (Professional) EDI claim file.
    Returns a structured dict with all claims and service lines.
    """
    segments = _split_segments(raw)
    result = {
        "transaction_type": "837P",
        "interchange_id":   "",
        "submission_date":  "",
        "sender_id":        "",
        "receiver_id":      "",
        "claims":           [],
        "total_claims":     0,
        "total_billed":     0.0,
        "raw_segments":     len(segments),
        "parse_warnings":   [],
    }

    current_claim: Optional[Dict]    = None
    current_service: Optional[Dict]  = None
    billing_npi   = ""
    billing_name  = ""
    submitter_id  = ""
    subscriber_last  = ""
    subscriber_first = ""
    subscriber_id    = ""
    payer_name    = ""
    payer_id      = ""

    for seg in segments:
        if not seg:
            continue
        tag = _el(seg, 0)

        if tag == "ISA":
            result["sender_id"]        = _el(seg, 6)
            result["receiver_id"]      = _el(seg, 8)
            result["interchange_id"]   = _el(seg, 13)
            result["submission_date"]  = _date(_el(seg, 9))

        elif tag == "NM1":
            nm1_type = _el(seg, 1)
            if nm1_type == "41":   # Submitter
                submitter_id = _el(seg, 9)
            elif nm1_type == "85": # Billing provider
                billing_name = f"{_el(seg, 3)} {_el(seg, 4)}".strip()
                billing_npi  = _el(seg, 9)
            elif nm1_type == "QC" and current_claim:   # Patient
                current_claim["patient_last"]  = _el(seg, 3)
                current_claim["patient_first"] = _el(seg, 4)
                current_claim["patient_id"]    = _el(seg, 9)
            elif nm1_type == "IL":   # Subscriber (may appear before CLM)
                subscriber_last  = _el(seg, 3)
                subscriber_first = _el(seg, 4)
                subscriber_id    = _el(seg, 9)
                if current_claim:
                    current_claim["subscriber_last"]  = subscriber_last
                    current_claim["subscriber_first"] = subscriber_first
                    current_claim["subscriber_id"]    = subscriber_id
                    current_claim["payer_id"]         = ""
            elif nm1_type == "PR":   # Payer (may appear before CLM)
                payer_name = _el(seg, 3)
                payer_id   = _el(seg, 9)
                if current_claim:
                    current_claim["payer_name"] = payer_name
                    current_claim["payer_id"]   = payer_id

        elif tag == "CLM":
            # Save previous claim
            if current_claim:
                if current_service:
                    current_claim["services"].append(current_service)
                    current_service = None
                result["claims"].append(current_claim)

            claim_id    = _el(seg, 1)
            billed_amt  = _money(_el(seg, 2))
            place       = _el(seg, 5).split(":")[0] if ":" in _el(seg, 5) else _el(seg, 5)
            current_claim = {
                "claim_id":          claim_id,
                "billed_amount":     billed_amt,
                "place_of_service":  place,
                "billing_npi":       billing_npi,
                "billing_name":      billing_name,
                "submitter_id":      submitter_id,
                "patient_first":     "",
                "patient_last":      "",
                "patient_id":        "",
                "subscriber_first":  subscriber_first,
                "subscriber_last":   subscriber_last,
                "subscriber_id":     subscriber_id,
                "payer_name":        payer_name,
                "payer_id":          payer_id,
                "service_date_from": "",
                "service_date_to":   "",
                "diagnosis_codes":   [],
                "services":          [],
                "status":            "submitted",
            }

        elif tag == "DTP" and current_claim:
            dtp_qual = _el(seg, 1)
            dtp_date = _el(seg, 3)
            if dtp_qual == "472":   # Service date range
                if "-" in dtp_date:
                    parts = dtp_date.split("-")
                    current_claim["service_date_from"] = _date(parts[0])
                    current_claim["service_date_to"]   = _date(parts[1]) if len(parts) > 1 else _date(parts[0])
                else:
                    current_claim["service_date_from"] = _date(dtp_date)
                    current_claim["service_date_to"]   = _date(dtp_date)

        elif tag == "HI" and current_claim:
            # Diagnosis codes
            for i in range(1, len(seg)):
                code_seg = _el(seg, i)
                if code_seg and ":" in code_seg:
                    parts = code_seg.split(":")
                    if len(parts) >= 2 and parts[1]:
                        current_claim["diagnosis_codes"].append(parts[1])

        elif tag == "SV1":
            # Service line
            if current_service and current_claim:
                current_claim["services"].append(current_service)
            svc_code_seg = _el(seg, 1)
            svc_code = svc_code_seg.split(":")[1] if ":" in svc_code_seg else svc_code_seg
            current_service = {
                "procedure_code":   svc_code,
                "description":      SERVICE_DESCRIPTIONS.get(svc_code, f"Procedure {svc_code}"),
                "charge_amount":    _money(_el(seg, 2)),
                "units":            _el(seg, 4),
                "unit_type":        _el(seg, 3),
                "modifiers":        [x for x in [_el(seg,5),_el(seg,6),_el(seg,7),_el(seg,8)] if x],
                "diagnosis_ptrs":   _el(seg, 9),
            }

    # Finalize last claim
    if current_claim:
        if current_service:
            current_claim["services"].append(current_service)
        result["claims"].append(current_claim)

    result["total_claims"] = len(result["claims"])
    result["total_billed"]  = round(sum(c["billed_amount"] for c in result["claims"]), 2)
    return result


# ── 835 Parser ────────────────────────────────────────────────────────────────

def parse_835(raw: str) -> Dict[str, Any]:
    """
    Parse an 835 Electronic Remittance Advice (ERA) file.
    Returns structured payments, adjustments, denials, and totals.
    """
    segments  = _split_segments(raw)
    result = {
        "transaction_type":  "835",
        "payer_name":        "",
        "payer_id":          "",
        "payee_name":        "",
        "payee_npi":         "",
        "check_number":      "",
        "check_date":        "",
        "check_amount":      0.0,
        "payment_method":    "",
        "claims":            [],
        "total_claims":      0,
        "total_charged":     0.0,
        "total_paid":        0.0,
        "total_denied":      0.0,
        "total_adjusted":    0.0,
        "raw_segments":      len(segments),
        "parse_warnings":    [],
    }

    current_claim: Optional[Dict]   = None
    current_service: Optional[Dict] = None

    for seg in segments:
        if not seg:
            continue
        tag = _el(seg, 0)

        if tag == "N1":
            entity = _el(seg, 1)
            if entity == "PR":   # Payer
                result["payer_name"] = _el(seg, 2)
                result["payer_id"]   = _el(seg, 4)
            elif entity == "PE": # Payee
                result["payee_name"] = _el(seg, 2)
                result["payee_npi"]  = _el(seg, 4)

        elif tag == "TRN":
            result["check_number"]   = _el(seg, 2)
            result["payment_method"] = {"CHK":"Paper Check","EFT":"Electronic Funds Transfer","ACH":"ACH Transfer"}.get(_el(seg, 1), _el(seg, 1))

        elif tag == "DTM":
            qualifier = _el(seg, 1)
            if qualifier == "405":   # Production date / check date
                result["check_date"] = _date(_el(seg, 2))

        elif tag == "BPR":
            result["check_amount"]   = _money(_el(seg, 2))
            method = _el(seg, 3)
            result["payment_method"] = {"CHK":"Paper Check","EFT":"Electronic Funds Transfer","ACH":"ACH"}.get(method, method)

        elif tag == "CLP":
            # Save previous claim
            if current_claim:
                if current_service:
                    current_claim["services"].append(current_service)
                    current_service = None
                result["claims"].append(current_claim)

            claim_id    = _el(seg, 1)
            status_code = _el(seg, 2)
            charged     = _money(_el(seg, 3))
            paid        = _money(_el(seg, 4))
            patient_resp = _money(_el(seg, 5))
            payer_claim_id = _el(seg, 7)

            status_label = CLAIM_STATUS_CODES.get(status_code, f"Status {status_code}")
            is_denied    = status_code in ("4", "21", "22")

            current_claim = {
                "claim_id":           claim_id,
                "payer_claim_id":     payer_claim_id,
                "status_code":        status_code,
                "status_label":       status_label,
                "is_denied":          is_denied,
                "charged_amount":     charged,
                "paid_amount":        paid,
                "patient_responsibility": patient_resp,
                "patient_name":       "",
                "patient_id":         "",
                "services":           [],
                "adjustments":        [],
                "denial_reasons":     [],
                "action_needed":      "",
            }

            if is_denied:
                current_claim["action_needed"] = "⚠️ DENIED — Review and resubmit or appeal"

        elif tag == "NM1" and current_claim:
            nm1_type = _el(seg, 1)
            if nm1_type == "QC":   # Patient
                current_claim["patient_name"] = f"{_el(seg, 3)}, {_el(seg, 4)}".strip(", ")
                current_claim["patient_id"]   = _el(seg, 9)

        elif tag == "CAS" and current_claim:
            # Claim adjustment
            group_code = _el(seg, 1)
            # Each CAS can have up to 3 reason-code/amount pairs
            for i in range(2, min(len(seg), 14), 3):
                reason_code = _el(seg, i)
                amount      = _money(_el(seg, i+1))
                if reason_code and amount != 0.0:
                    desc = ADJUSTMENT_REASON_CODES.get(reason_code, f"Adj code {reason_code}")
                    adj = {
                        "group":       group_code,
                        "reason_code": reason_code,
                        "description": desc,
                        "amount":      amount,
                    }
                    current_claim["adjustments"].append(adj)
                    if current_claim["is_denied"] or reason_code in ("56","57","58","50","31"):
                        current_claim["denial_reasons"].append(f"{reason_code}: {desc}")

        elif tag == "SVC" and current_claim:
            # Save previous service
            if current_service:
                current_claim["services"].append(current_service)

            svc_seg   = _el(seg, 1)
            svc_code  = svc_seg.split(":")[1] if ":" in svc_seg else svc_seg
            charged   = _money(_el(seg, 2))
            paid      = _money(_el(seg, 3))
            units     = _el(seg, 5)

            current_service = {
                "procedure_code":  svc_code,
                "description":     SERVICE_DESCRIPTIONS.get(svc_code, f"Procedure {svc_code}"),
                "charged_amount":  charged,
                "paid_amount":     paid,
                "units":           units,
                "adjustments":     [],
                "variance":        round(charged - paid, 2),
            }

        elif tag == "CAS" and current_service:
            # Service-level adjustment
            group_code = _el(seg, 1)
            for i in range(2, min(len(seg), 14), 3):
                reason_code = _el(seg, i)
                amount      = _money(_el(seg, i+1))
                if reason_code and amount != 0.0:
                    desc = ADJUSTMENT_REASON_CODES.get(reason_code, f"Code {reason_code}")
                    current_service["adjustments"].append({
                        "group": group_code, "reason_code": reason_code,
                        "description": desc, "amount": amount,
                    })

    # Finalize last claim
    if current_claim:
        if current_service:
            current_claim["services"].append(current_service)
        result["claims"].append(current_claim)

    # Compute totals
    result["total_claims"]   = len(result["claims"])
    result["total_charged"]  = round(sum(c["charged_amount"] for c in result["claims"]), 2)
    result["total_paid"]     = round(sum(c["paid_amount"] for c in result["claims"]), 2)
    result["total_denied"]   = round(sum(c["charged_amount"] for c in result["claims"] if c["is_denied"]), 2)
    result["total_adjusted"] = round(result["total_charged"] - result["total_paid"], 2)

    return result


# ── EDI Interpreter ───────────────────────────────────────────────────────────

class EDIInterpreter:
    """
    Human-readable interpretation layer for 837/835 data.
    Produces summaries, action items, and plain-English explanations
    that Kato/REX can read without knowing EDI spec.
    """

    @staticmethod
    def interpret_835(parsed: dict) -> dict:
        """Turn parsed 835 into a Chairman-friendly summary."""
        claims = parsed.get("claims", [])
        denied = [c for c in claims if c["is_denied"]]
        paid   = [c for c in claims if not c["is_denied"] and c["paid_amount"] > 0]
        zero   = [c for c in claims if not c["is_denied"] and c["paid_amount"] == 0]

        action_items = []
        denial_breakdown = {}

        for c in denied:
            for reason in c.get("denial_reasons", []):
                denial_breakdown[reason] = denial_breakdown.get(reason, 0) + 1
                # Map to plain-English actions
                code = reason.split(":")[0].strip()
                if code in ("56", "57", "252"):
                    action_items.append(f"📋 Get prior authorization for claim {c['claim_id']} ({c.get('patient_name','Unknown')})")
                elif code in ("31",):
                    action_items.append(f"🆔 Verify eligibility on DOS for {c.get('patient_name','Unknown')}")
                elif code in ("16", "4"):
                    action_items.append(f"📝 Resubmit with corrected info: claim {c['claim_id']}")
                elif code in ("18",):
                    action_items.append(f"⚠️ Duplicate claim — review {c['claim_id']}")
                elif code in ("50", "96"):
                    action_items.append(f"❌ Non-covered service on {c['claim_id']} — check benefits")
                elif code in ("58",):
                    action_items.append(f"🔐 Unauthorized service — obtain auth for {c['claim_id']}")

        reimbursement_rate = 0.0
        if parsed["total_charged"] > 0:
            reimbursement_rate = round((parsed["total_paid"] / parsed["total_charged"]) * 100, 1)

        return {
            "summary": {
                "payer":               parsed.get("payer_name", ""),
                "check_number":        parsed.get("check_number", ""),
                "check_date":          parsed.get("check_date", ""),
                "check_amount":        parsed.get("check_amount", 0.0),
                "payment_method":      parsed.get("payment_method", ""),
                "total_claims":        parsed["total_claims"],
                "paid_claims":         len(paid),
                "denied_claims":       len(denied),
                "zero_pay_claims":     len(zero),
                "total_charged":       parsed["total_charged"],
                "total_paid":          parsed["total_paid"],
                "total_denied":        parsed["total_denied"],
                "total_adjusted":      parsed["total_adjusted"],
                "reimbursement_rate":  reimbursement_rate,
            },
            "denial_breakdown": denial_breakdown,
            "action_items": list(set(action_items)),
            "plain_english": (
                f"You received a remittance from {parsed.get('payer_name','the payer')}.\n"
                f"Check #{parsed.get('check_number','?')} dated {parsed.get('check_date','?')} "
                f"for ${parsed.get('check_amount',0):,.2f} ({parsed.get('payment_method','')}).\n\n"
                f"Of {parsed['total_claims']} claims submitted:\n"
                f"  ✅ {len(paid)} paid totaling ${parsed['total_paid']:,.2f}\n"
                f"  ❌ {len(denied)} denied totaling ${parsed['total_denied']:,.2f}\n"
                f"  📊 Reimbursement rate: {reimbursement_rate}%\n\n"
                + (f"ACTION NEEDED:\n" + "\n".join(f"  {a}" for a in set(action_items)) if action_items else "✅ No immediate action required.")
            ),
        }

    @staticmethod
    def interpret_837(parsed: dict) -> dict:
        """Turn parsed 837 into a Chairman-friendly summary."""
        claims = parsed.get("claims", [])
        by_payer = {}
        for c in claims:
            p = c.get("payer_name", "Unknown Payer")
            by_payer.setdefault(p, {"count": 0, "total": 0.0})
            by_payer[p]["count"] += 1
            by_payer[p]["total"] += c["billed_amount"]

        return {
            "summary": {
                "submission_date": parsed.get("submission_date", ""),
                "sender_id":       parsed.get("sender_id", ""),
                "total_claims":    parsed["total_claims"],
                "total_billed":    parsed["total_billed"],
                "by_payer":        by_payer,
            },
            "plain_english": (
                f"Claim submission received — {parsed['total_claims']} claim(s) "
                f"totaling ${parsed['total_billed']:,.2f} submitted on {parsed.get('submission_date','?')}.\n"
                + "\n".join(f"  • {p}: {v['count']} claims, ${v['total']:,.2f}" for p, v in by_payer.items())
            ),
        }

    @staticmethod
    def match_835_to_837(era_parsed: dict, claim_parsed: dict) -> list:
        """
        Match ERA payment lines to submitted claims by claim_id.
        Returns a reconciliation report.
        """
        submitted = {c["claim_id"]: c for c in claim_parsed.get("claims", [])}
        reconciled = []

        for era_claim in era_parsed.get("claims", []):
            cid   = era_claim["claim_id"]
            match = submitted.get(cid)
            rec   = {
                "claim_id":      cid,
                "patient":       era_claim.get("patient_name", ""),
                "charged":       era_claim.get("charged_amount", 0.0),
                "paid":          era_claim.get("paid_amount", 0.0),
                "status":        era_claim.get("status_label", ""),
                "is_denied":     era_claim.get("is_denied", False),
                "matched":       match is not None,
                "original_billed": match["billed_amount"] if match else None,
                "variance":      round((match["billed_amount"] if match else 0.0) - era_claim.get("paid_amount", 0.0), 2),
                "action_needed": era_claim.get("action_needed", ""),
            }
            reconciled.append(rec)

        return reconciled


# ── Auto-detect file type ─────────────────────────────────────────────────────

def detect_and_parse(raw: str) -> dict:
    """
    Auto-detect whether this is an 837 or 835 file and parse it.
    Returns {"type": "837"|"835", "parsed": {...}, "interpreted": {...}}
    """
    # Look for transaction set type in ST segment
    for seg in _split_segments(raw):
        if seg and seg[0] == "ST":
            tx_type = seg[1] if len(seg) > 1 else ""
            if tx_type == "837":
                parsed      = parse_837(raw)
                interpreted = EDIInterpreter.interpret_837(parsed)
                return {"type": "837", "parsed": parsed, "interpreted": interpreted}
            elif tx_type == "835":
                parsed      = parse_835(raw)
                interpreted = EDIInterpreter.interpret_835(parsed)
                return {"type": "835", "parsed": parsed, "interpreted": interpreted}

    # Fallback: sniff content
    if "CLM*" in raw or "CLM|" in raw:
        parsed = parse_837(raw)
        return {"type": "837", "parsed": parsed, "interpreted": EDIInterpreter.interpret_837(parsed)}
    elif "CLP*" in raw or "CLP|" in raw:
        parsed = parse_835(raw)
        return {"type": "835", "parsed": parsed, "interpreted": EDIInterpreter.interpret_835(parsed)}

    return {"type": "unknown", "parsed": {}, "interpreted": {"error": "Could not detect EDI transaction type (837 or 835). Check file format."}}


def _selftest():
    """Minimal selftest: parse sample 837/835 strings and verify extracted data."""
    # Build 106-char ISA segments with correct field padding
    def _isa(sender_id, receiver_id, ctrl_num):
        return (
            "ISA*00*" + " " * 10 + "*00*" + " " * 10
            + "*ZZ*" + sender_id.ljust(15) + "*ZZ*" + receiver_id.ljust(15)
            + "*250601*1200*U*00401*" + str(ctrl_num).zfill(9) + "*0*T*:"
        )

    isa_837 = _isa("GOLDHLTH", "NYMEDICAID", 1)
    sample_837 = (
        isa_837 + "~"
        "GS*HC*GOLDHLTH*NYMEDICAID*20250601*1200*1*X*004010X098A1~"
        "ST*837*0001~"
        "BHT*0019*00*CLAIM001*20250601*1200*CH~"
        "NM1*41*2*GOLD HEALTH SYSTEMS*****46*SUB001~"
        "NM1*85*2*GOLD HEALTH*****XX*1234567890~"
        "HL*1**20*1~"
        "NM1*IL*1*DOE*JOHN****MI*JDOE123~"
        "NM1*PR*2*NY MEDICAID*****PI*NYMCD001~"
        "CLM*CLM001*250.00***11:B:1*Y*A*Y*Y~"
        "DTP*472*RD8*20250501-20250501~"
        "HI*BK:Z1234*BF:Z5678~"
        "NM1*QC*1*DOE*JANE****MI*JDOE456~"
        "SV1*HC:T1019*150.00*UN*8***1:2:3~"
        "SV1*HC:S9122*100.00*UN*2***4~"
        "SE*16*0001~"
        "GE*1*1~"
        "IEA*1*000000001~"
    )

    print("=== EDI Selftest ===")
    parsed = parse_837(sample_837)

    # Verify basic structure
    assert parsed["transaction_type"] == "837P", f"Expected 837P, got {parsed['transaction_type']}"
    assert parsed["total_claims"] == 1, f"Expected 1 claim, got {parsed['total_claims']}"
    assert parsed["claims"], "No claims extracted"

    claim = parsed["claims"][0]
    assert claim["claim_id"] == "CLM001", f"Expected CLM001, got {claim['claim_id']}"
    assert claim["billed_amount"] == 250.00, f"Expected 250.00, got {claim['billed_amount']}"
    assert claim["patient_last"] == "DOE", f"Expected DOE, got {claim['patient_last']}"
    assert claim["patient_first"] == "JANE", f"Expected JANE, got {claim['patient_first']}"
    assert claim["subscriber_last"] == "DOE", f"Expected DOE, got {claim['subscriber_last']}"
    assert claim["payer_name"] == "NY MEDICAID", f"Expected NY MEDICAID, got {claim['payer_name']}"
    assert claim["billing_npi"] == "1234567890", f"Expected 1234567890, got {claim['billing_npi']}"
    assert claim["service_date_from"] == "05/01/2025", f"Expected 05/01/2025, got {claim['service_date_from']}"
    assert len(claim["diagnosis_codes"]) == 2, f"Expected 2 diagnosis codes, got {len(claim['diagnosis_codes'])}"
    assert len(claim["services"]) == 2, f"Expected 2 service lines, got {len(claim['services'])}"

    svc1 = claim["services"][0]
    assert svc1["procedure_code"] == "T1019", f"Expected T1019, got {svc1['procedure_code']}"
    assert svc1["charge_amount"] == 150.00, f"Expected 150.00, got {svc1['charge_amount']}"
    assert svc1["units"] == "8", f"Expected 8, got {svc1['units']}"
    assert "Personal Care" in svc1["description"], f"Expected Personal Care desc, got {svc1['description']}"

    svc2 = claim["services"][1]
    assert svc2["procedure_code"] == "S9122", f"Expected S9122, got {svc2['procedure_code']}"
    assert svc2["charge_amount"] == 100.00, f"Expected 100.00, got {svc2['charge_amount']}"

    assert parsed["total_billed"] == 250.00, f"Expected 250.00 total billed, got {parsed['total_billed']}"

    # Also test interpret_837
    interp = EDIInterpreter.interpret_837(parsed)
    assert interp["summary"]["total_claims"] == 1
    assert "plain_english" in interp

    # Test 835 parsing
    isa_835 = _isa("NYMEDICAID", "GOLDHLTH", 2)
    sample_835 = (
        isa_835 + "~"
        "GS*HP*NYMEDICAID*GOLDHLTH*20250601*1200*2*X*004010X091A1~"
        "ST*835*0002~"
        "BPR*C*500.00*C*CHK***20250601~"
        "TRN*1*CHK001*1234567890~"
        "DTM*405*20250601~"
        "N1*PR*NY MEDICAID~"
        "N1*PE*GOLD HEALTH SYSTEMS*XX*1234567890~"
        "CLP*CLM001*1*250.00*200.00*0.00*12*MC-REF001~"
        "NM1*QC*1*DOE*JANE****MI*JDOE456~"
        "CAS*CO*45*50.00~"
        "SVC*HC:T1019*150.00*120.00**8~"
        "CAS*CO*45*30.00~"
        "SVC*HC:S9122*100.00*80.00**2~"
        "SE*14*0002~"
        "GE*1*2~"
        "IEA*1*000000002~"
    )

    parsed835 = parse_835(sample_835)
    assert parsed835["transaction_type"] == "835", f"Expected 835, got {parsed835['transaction_type']}"
    assert parsed835["payer_name"] == "NY MEDICAID", f"Expected NY MEDICAID, got {parsed835['payer_name']}"
    assert parsed835["check_number"] == "CHK001"
    assert parsed835["check_amount"] == 500.00
    assert parsed835["total_claims"] == 1
    assert parsed835["total_charged"] == 250.00
    assert parsed835["total_paid"] == 200.00
    claim_835 = parsed835["claims"][0]
    assert claim_835["claim_id"] == "CLM001"
    assert claim_835["paid_amount"] == 200.00
    assert len(claim_835["adjustments"]) > 0
    assert len(claim_835["services"]) == 2

    interp835 = EDIInterpreter.interpret_835(parsed835)
    assert interp835["summary"]["reimbursement_rate"] == 80.0
    assert "plain_english" in interp835

    # Test auto-detect
    detected = detect_and_parse(sample_837)
    assert detected["type"] == "837", f"Expected 837, got {detected['type']}"
    detected = detect_and_parse(sample_835)
    assert detected["type"] == "835", f"Expected 835, got {detected['type']}"

    print("✅ All selftest assertions passed!")
    print(f"   837: {parsed['total_claims']} claim, ${parsed['total_billed']:.2f} billed, "
          f"{len(claim['services'])} services, {len(claim['diagnosis_codes'])} diagnoses")
    print(f"   835: {parsed835['total_claims']} claim, ${parsed835['total_paid']:.2f} paid, "
          f"rate: {interp835['summary']['reimbursement_rate']}%")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        _selftest()
        sys.exit(0)
    if len(sys.argv) < 2:
        print("Usage: python rex_edi.py <file.835|file.837>  or  python rex_edi.py --selftest")
        sys.exit(1)
    raw  = Path(sys.argv[1]).read_text()
    result = detect_and_parse(raw)
    print(f"\n{'='*60}")
    print(f"EDI Type: {result['type'].upper()}")
    print(f"{'='*60}")
    if "plain_english" in result.get("interpreted", {}):
        print(result["interpreted"]["plain_english"])
    if result["interpreted"].get("action_items"):
        print("\nACTION ITEMS:")
        for item in result["interpreted"]["action_items"]:
            print(f"  {item}")
    print(f"\nFull JSON: {json.dumps(result['parsed'], indent=2)[:2000]}...")
