#!/usr/bin/env python3
"""
CC_billing_payers.py — MLTC Payer Configuration Bridge
======================================================
Hardcoded from HHAeXchange e-billing screens (2026-06-18 extraction).
Maps every active MLTC/Medicaid plan to its 837P routing parameters
so CC_medicaid_837_generator.py produces correct EDI per payer.

Source: ~/Documents/hha_data/ebilling/*_ebilling.txt (24 files, 12 payers)
Ground truth: HHAeXchange app.hhaexchange.com Contract → E-Billing tab (June 2026)

Two clearinghouses:
  - Availity → DHS: Most MLTC plans (VillageCareMAX, Integra, Elderserve, MetroPlus, VNS, SWH...)
  - MDOn-Line: Aetna only (direct payer portal)

HCPCS Codes Used:
  T1019 — Personal care services, per 15 minutes
  T1020 — Personal care services, per diem
  H2015 — NY MLTC home-health bundled service
  A0425 — Ground mileage, per statute mile (transport)
  S0201 — Partial hospitalization, less than 24 hours (adult day care)

Rate Types:
  Visit  — per day (clients attend X days/week)
  Daily  — per occurrence (telehealth, meals, etc.)
  Transport — 2 units per visit (pickup + dropoff)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Taxonomy Codes (critical for claim acceptance) ────────────────────────────
# 251E00000X = Home Health (HHAE default for SADC/adult day care)
# 363A00000X = Physician Assistant (current .env.837 default — likely WRONG)
# 261QA0600X = Adult Day Care (specialty code — use this for 837P CMS-1500)
TAXONOMY_ADULT_DAY_CARE = "251E00000X"  # HHAeXchange default for GOJ
TAXONOMY_HOME_HEALTH = "251E00000X"

# ── Common config shared by all Availity-routed plans ─────────────────────────
AVAILITY_BASE = {
    "isa_sender_qual":     "ZZ",
    "isa_sender_id":       "AV09311993",
    "isa_receiver_qual":   "01",
    "isa_receiver_id":     "030240928",
    "gs_app_sender":       "725850",
    "gs_app_receiver":     "030240928",
    "isa_usage_indicator": "P",
    "receiver_name":       "AVAILITY",
    "receiver_id":         "AVAILITY",
    "submitter_etin":      "725850",
    "submitter_contact":   "FISCAL SERV DEPT",
    "submitter_phone":     "",  # from PER*EM (email preferred)
}

# ── GOJ/REX common identity ───────────────────────────────────────────────────
GOJ_IDENTITY = {
    "billing_npi":      "1124475900",
    "billing_taxonomy": TAXONOMY_ADULT_DAY_CARE,
    "billing_name":     "GOJ INC DBA GARDEN OF JOY SADC",
    "billing_addr1":    "4120 OCEAN AVE",
    "billing_city":     "BROOKLYN",
    "billing_state":    "NY",
    "billing_zip":      "11235",
    "billing_tax_id":   "812185964",  # vault: GOJ Billing System — Integration.md (VendorID 1167)
}

# ── Per-payer config — hardcoded from HHAX e-billing screens ──────────────────
# Fields: payer_name, payer_id, default_service_code, rate_visit, rate_transport,
#         rate_daily, additional_rates, notes

PAYER_CONFIGS: Dict[str, Dict[str, Any]] = {
    # ── Availity → DHS (ISA 030240928) ────────────────────────────────────────
    "VillageCareMAX": {
        **AVAILITY_BASE,
        "payer_name":            "VILLAGECAREMAX",
        "payer_id":              "26545",
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,   # VCM visit — per day attendance
        "rate_transport":        25.00,   # VCM transport — 2 units/day
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",  "unit_type": "UN", "units": 1},
            "A0425": {"rate": 25.00, "desc": "Day Care Transport", "unit_type": "UN", "units": 2},
        },
        "notes": "Availity → DHS. VCM visit + transport billed separately per visit day.",
    },
    # ── Availity → DHS (ISA 030240928) ────────────────────────────────────────
    "Anthem": {
        **AVAILITY_BASE,
        "payer_name":            "INTEGRA MANAGED LONG TERM CARE",
        "payer_id":              "45302",
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,   # Day Care Visit
        "rate_transport":        25.00,   # Day Care Transport
        "rate_daily_tele":       25.00,   # tele — daily
        "rate_daily_food":       20.00,   # Food — daily
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
            "A0425": {"rate": 25.00, "desc": "Day Care Transport","unit_type": "UN", "units": 2},
            "S0201": {"rate": 25.00, "desc": "Telehealth",       "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Formerly Integra MLTC. CPHL plan folded in March 2026 (191 clients). Payer ID 45302.",
    },

    "Elderserve": {
        # MDOn-Line direct — per auth_tracker.insurance_payers (HHAX e-billing
        # export 2026-06-18), NOT Availity. payer_id 05178 from same export.
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "812185964",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "MDOL837",
        "gs_app_sender":       "812185964",
        "gs_app_receiver":     "MDOL837",
        "isa_usage_indicator": "P",
        "receiver_name":       "MDON-LINE",
        "receiver_id":         "MDOL837",
        "submitter_name":      "Garden of Joy",
        "submitter_etin":      "812185964",
        "submitter_contact":   "FISCAL SERV DEPT",
        "submitter_phone":     "",
        "payer_name":            "ELDERSERVE — RIVERSPRING HEALTH",
        "payer_id":              "05178",
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,
        "rate_transport":        25.00,
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Payer ID TBD — check HHAX e-billing screen.",
    },

    "MetroPlus": {
        # MDOn-Line direct — per auth_tracker.insurance_payers (HHAX e-billing
        # export 2026-06-18), NOT Availity. payer_id not in export — Kato to supply.
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "812185964",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "MDOL837",
        "gs_app_sender":       "812185964",
        "gs_app_receiver":     "MDOL837",
        "isa_usage_indicator": "P",
        "receiver_name":       "MDON-LINE",
        "receiver_id":         "MDOL837",
        "submitter_name":      "Garden of Joy",
        "submitter_etin":      "812185964",
        "submitter_contact":   "FISCAL SERV DEPT",
        "submitter_phone":     "",
        "payer_name":            "METROPLUS HEALTH",
        "payer_id":              "",  # KATO: not in HHAX export
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,
        "rate_transport":        25.00,
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Payer ID TBD.",
    },

    "VNS_Health": {
        **AVAILITY_BASE,
        "payer_name":            "VNS HEALTH",
        "payer_id":              "77073",  # from auth_tracker.insurance_payers (HHAX export 2026-06-18)
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,
        "rate_transport":        25.00,
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Payer ID TBD.",
    },

    "Senior_Whole_Health": {
        **AVAILITY_BASE,
        # Envelope overrides per HHAX export row 4: gs sender AV09311993,
        # submitter is Homecare Software Solutions LLC (SWH's vendor).
        "gs_app_sender":       "AV09311993",
        "submitter_name":      "Homecare Software Solutions LLC",
        "payer_name":            "SENIOR WHOLE HEALTH",
        "payer_id":              "SWHNY",  # from auth_tracker.insurance_payers (HHAX export 2026-06-18)
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,
        "rate_transport":        25.00,
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Payer ID TBD. Also has tele rate via SWH_Tele config.",
    },

    "SWH_Tele": {
        **AVAILITY_BASE,
        "payer_name":            "SENIOR WHOLE HEALTH — TELEHEALTH",
        "payer_id":              "SWHNY",  # same payer family as SWH (HHAX export 2026-06-18)
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_daily_tele":       25.00,
        "units_per_visit":       1,
        "service_codes": {
            "T1019": {"rate": 25.00, "desc": "Telehealth Visit",  "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Telehealth-only plan under SWH. Separate from in-person.",
    },

    "Centers_Plan": {
        # MDOn-Line direct — CPHL bills on its OWN rail (payer CPLHI), NOT the
        # Integra/Anthem rail (45302/Availity). Per insurance_payers row 14
        # (HHAX e-billing export 2026-06-18) + Jul 7 audit: CPHL→MDOL837.
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "812185964",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "MDOL837",
        "gs_app_sender":       "812185964",
        "gs_app_receiver":     "MDOL837",
        "isa_usage_indicator": "P",
        "receiver_name":       "MDON-LINE",
        "receiver_id":         "MDOL837",
        "submitter_name":      "GOJ inc. dba Garden Of Joy SADC",
        "submitter_etin":      "812185964",
        "submitter_contact":   "FISCAL SERV DEPT",
        "submitter_phone":     "",
        "payer_name":            "CENTERS PLAN FOR HEALTHY LIVING",
        "payer_id":              "CPLHI",  # from auth_tracker.insurance_payers (HHAX export 2026-06-18)
        "default_service_code":  "T1019",
        "claim_filing_code":     "CI",
        "rate_visit":            70.00,
        "rate_transport":        25.00,
        "units_per_visit":       1,
        "units_per_transport":   2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "Availity → DHS. Payer ID TBD.",
    },

    # ── MDOn-Line direct (NO Availity) ────────────────────────────────────────
    "Aetna": {
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "812185964",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "MDOL837",
        "gs_app_sender":       "812185964",
        "gs_app_receiver":     "MDOL837",
        "isa_usage_indicator": "P",
        "receiver_name":       "MDON-LINE",
        "receiver_id":         "MDOL837",
        "submitter_name":      "GOJ INC",
        "submitter_etin":      "812185964",
        "submitter_contact":   "FISCAL SERV DEPT",
        "submitter_phone":     "",
        "payer_name":          "AETNA",
        "payer_id":            "34734",
        "default_service_code":"T1019",
        "claim_filing_code":   "CI",
        "rate_visit":          70.00,
        "rate_transport":      25.00,
        "units_per_visit":     1,
        "units_per_transport": 2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "MDOn-Line direct (NOT Availity). Type of Bill: 89. Payer ID 34734.",
    },

    "Aetna_Better_Health": {
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "812185964",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "MDOL837",
        "gs_app_sender":       "812185964",
        "gs_app_receiver":     "MDOL837",
        "isa_usage_indicator": "P",
        "receiver_name":       "MDON-LINE",
        "receiver_id":         "MDOL837",
        "submitter_name":      "GOJ INC",
        "submitter_etin":      "812185964",
        "submitter_contact":   "FISCAL SERV DEPT",
        "submitter_phone":     "",
        "payer_name":          "AETNA BETTER HEALTH",
        "payer_id":            "",  # KATO: different from main Aetna?
        "default_service_code":"T1019",
        "claim_filing_code":   "CI",
        "rate_visit":          70.00,
        "rate_transport":      25.00,
        "units_per_visit":     1,
        "units_per_transport": 2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "MDOn-Line direct. Aetna Better Health of NY / GJA. Payer ID TBD.",
    },

    "Aetna_Transport": {
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "812185964",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "MDOL837",
        "gs_app_sender":       "812185964",
        "gs_app_receiver":     "MDOL837",
        "isa_usage_indicator": "P",
        "receiver_name":       "MDON-LINE",
        "receiver_id":         "MDOL837",
        "submitter_name":      "GOJ INC",
        "submitter_etin":      "812185964",
        "submitter_contact":   "FISCAL SERV DEPT",
        "submitter_phone":     "",
        "payer_name":          "AETNA TRANSPORT",
        "payer_id":            "",
        "default_service_code":"A0425",
        "claim_filing_code":   "CI",
        "rate_transport":      25.00,
        "units_per_transport": 2,
        "service_codes": {
            "A0425": {"rate": 25.00, "desc": "Transport Only", "unit_type": "UN", "units": 2},
        },
        "notes": "MDOn-Line direct. Transport-only billing under Aetna — separate from visit claims.",
    },

    # ── Private Pay / Non-Medicaid ────────────────────────────────────────────
    "Private_Pay": {
        "isa_sender_qual":     "ZZ",
        "isa_sender_id":       "PRIVATEPAY",
        "isa_receiver_qual":   "ZZ",
        "isa_receiver_id":     "PRIVATEPAY",
        "gs_app_sender":       "PRIVATEPAY",
        "gs_app_receiver":     "PRIVATEPAY",
        "isa_usage_indicator": "T",  # Test — private pay doesn't go through clearinghouse
        "receiver_name":       "PRIVATE PAY",
        "receiver_id":         "PRIVATEPAY",
        "submitter_name":      "GOJ INC DBA GARDEN OF JOY SADC",
        "submitter_etin":      "PRIVATEPAY",
        "submitter_contact":   "BILLING DEPT",
        "submitter_phone":     "",
        "payer_name":          "PRIVATE PAY",
        "payer_id":            "PRIVATE",
        "default_service_code":"T1019",
        "claim_filing_code":   "CI",
        "rate_visit":          70.00,
        "rate_transport":      25.00,
        "units_per_visit":     1,
        "units_per_transport": 2,
        "service_codes": {
            "T1019": {"rate": 70.00, "desc": "Day Care Visit",    "unit_type": "UN", "units": 1},
        },
        "notes": "Private pay — no clearinghouse. EDI is for internal records only.",
    },
}

# ── Payer name aliases — maps canonical DB values to config keys ──────────────
PAYER_ALIASES = {
    "anthem":                        "Integra",
    "integ ra":                      "Integra",
    "villagecare max":               "VillageCareMAX",
    "villagecaremax":                "VillageCareMAX",
    "village care max":              "VillageCareMAX",
    "vcm":                          "VillageCareMAX",
    "villagecare":                  "VillageCareMAX",  # 2026-07-27 — 27 ACTIVE auths use this exact payer_canonical value
    "village care":                 "VillageCareMAX",
    "elderserve — riverspring health": "Elderserve",  # em-dash variant from clients.plan_canonical (87 active clients)
    "metroplus health":             "MetroPlus",
    "empire bluecross blueshield":  "Private_Pay",
    "aetna":                         "Aetna",
    "aetna better health":           "Aetna_Better_Health",
    "aetna betterhealth":            "Aetna_Better_Health",
    "aetna transport":               "Aetna_Transport",
    "elderserve":                    "Elderserve",
    "riverspring":                   "Elderserve",
    "riverspring health":            "Elderserve",
    "river spring":                  "Elderserve",
    "elder serve":                   "Elderserve",
    "metroplus":                     "MetroPlus",
    "metro plus":                    "MetroPlus",
    "vns":                           "VNS_Health",
    "vns health":                    "VNS_Health",
    "vnshealth":                     "VNS_Health",
    "senior whole health":           "Senior_Whole_Health",
    "senior wholehealth":            "Senior_Whole_Health",
    "swh":                           "Senior_Whole_Health",
    "swh tele":                      "SWH_Tele",
    "swh teleh":                     "SWH_Tele",
    "centers plan":                  "Centers_Plan",
    "centers plan for healthy living":"Centers_Plan",
    "centersplan":                   "Centers_Plan",
    "private pay":                   "Private_Pay",
    "privatepay":                    "Private_Pay",
    "private":                       "Private_Pay",
    "empire":                        "Private_Pay",  # BCBS → private pay for now
    "empire bluecross":              "Private_Pay",
    "bluecross":                     "Private_Pay",
}

# ── Public API ────────────────────────────────────────────────────────────────

def resolve_payer(plan_name: str) -> Optional[str]:
    """
    Resolve a payer name from the DB (which may be abbreviated or variant)
    to the canonical PAYER_CONFIGS key. Returns None if unrecognized.
    """
    normalized = plan_name.strip().lower()
    # Exact key match
    if normalized in {k.lower() for k in PAYER_CONFIGS}:
        for k in PAYER_CONFIGS:
            if k.lower() == normalized:
                return k
    # Alias match
    if normalized in PAYER_ALIASES:
        return PAYER_ALIASES[normalized]
    return None


def get_payer_config(plan_name: str) -> Optional[Dict[str, Any]]:
    """
    Return full 837 config for a payer. Uses aliases to resolve DB values.
    Merges GOJ identity into the config. Returns None if plan is unknown.
    """
    resolved = resolve_payer(plan_name)
    if not resolved:
        return None
    if resolved in PAYER_CONFIGS:
        cfg = {**GOJ_IDENTITY, **PAYER_CONFIGS[resolved]}
        cfg["plan_name"] = resolved
        cfg["plan_name_raw"] = plan_name  # preserve original for display
        return cfg
    return None


def get_all_payers() -> List[str]:
    """Return sorted list of configured payer names."""
    return sorted(PAYER_CONFIGS.keys())


def get_clearinghouse(plan_name: str) -> str:
    """
    Return the clearinghouse routing path for a plan.
    Returns 'Availity → DHS', 'MDOn-Line', or 'Unknown'.
    """
    cfg = get_payer_config(plan_name)
    if not cfg:
        return "Unknown"
    if cfg.get("isa_receiver_id") == "MDOL837":
        return "MDOn-Line (direct)"
    if cfg.get("isa_receiver_id") == "030240928":
        return "Availity → DHS"
    return "Unknown"


def get_rate(plan_name: str, rate_type: str = "visit") -> float:
    """
    Get per-unit rate for a payer. rate_type: visit, transport, tele, food.
    """
    cfg = get_payer_config(plan_name)
    if not cfg:
        return 0.0
    key = f"rate_{rate_type}"
    return float(cfg.get(key, 0.0) or 0.0)


def payer_readiness() -> Dict[str, Any]:
    """
    Report which payers are ready for 837 generation vs missing IDs.
    """
    ready = []
    blocked = []
    for name in PAYER_CONFIGS:
        cfg = PAYER_CONFIGS[name]
        missing = []
        if not cfg.get("payer_id", "").strip():
            missing.append("payer_id")
        if not GOJ_IDENTITY.get("billing_tax_id", "").strip():
            missing.append("billing_tax_id (GOJ EIN)")
        if missing:
            blocked.append({"name": name, "missing": missing})
        else:
            ready.append(name)
    return {
        "ready": ready,
        "blocked": blocked,
        "total": len(PAYER_CONFIGS),
        "ready_count": len(ready),
        "blocked_count": len(blocked),
    }


def build_837_config(plan_name: str) -> Dict[str, Any]:
    """
    Build the full 837 generator config dict for CC_medicaid_837_generator.py.
    Merges GOJ identity + payer routing + rate codes.
    """
    plan = get_payer_config(plan_name)
    if not plan:
        raise ValueError(f"Unknown payer: {plan_name}")

    config = {
        # Submitter (1000A)
        "submitter_name":      plan.get("submitter_name", GOJ_IDENTITY["billing_name"]),
        "submitter_etin":      plan.get("submitter_etin", ""),
        "submitter_contact":   plan.get("submitter_contact", "BILLING DEPT"),
        "submitter_phone":     plan.get("submitter_phone", ""),

        # Receiver (1000B) — clearinghouse
        "receiver_name":       plan.get("receiver_name", "AVAILITY"),
        "receiver_id":         plan.get("receiver_id", "AVAILITY"),

        # Billing provider (2010AA)
        "billing_name":        plan.get("billing_name", GOJ_IDENTITY["billing_name"]),
        "billing_npi":         plan.get("billing_npi", GOJ_IDENTITY["billing_npi"]),
        "billing_tax_id":      plan.get("billing_tax_id", GOJ_IDENTITY["billing_tax_id"]),
        "billing_taxonomy":    plan.get("billing_taxonomy", GOJ_IDENTITY["billing_taxonomy"]),
        "billing_addr1":       plan.get("billing_addr1", GOJ_IDENTITY["billing_addr1"]),
        "billing_city":        plan.get("billing_city", GOJ_IDENTITY["billing_city"]),
        "billing_state":       plan.get("billing_state", GOJ_IDENTITY["billing_state"]),
        "billing_zip":         plan.get("billing_zip", GOJ_IDENTITY["billing_zip"]),

        # Payer (2010BB)
        "payer_name":          plan.get("payer_name", ""),
        "payer_id":            plan.get("payer_id", ""),

        # ISA envelope
        "isa_sender_qual":     plan.get("isa_sender_qual", "ZZ"),
        "isa_sender_id":       plan.get("isa_sender_id", ""),
        "isa_receiver_qual":   plan.get("isa_receiver_qual", "ZZ"),
        "isa_receiver_id":     plan.get("isa_receiver_id", ""),
        "isa_usage_indicator": plan.get("isa_usage_indicator", "T"),
        "gs_app_sender":       plan.get("gs_app_sender", ""),
        "gs_app_receiver":     plan.get("gs_app_receiver", ""),

        # Service line defaults
        "default_service_code": plan.get("default_service_code", "T1019"),
        "default_unit_type":    "UN",
        "place_of_service":     "11",  # office/ADC facility
    }
    return config


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    print("=== CC_billing_payers.py — Payer Config Bridge ===\n")
    print(f"Configured payers: {len(PAYER_CONFIGS)}\n")

    for name in sorted(PAYER_CONFIGS.keys()):
        ch = get_clearinghouse(name)
        rid = PAYER_CONFIGS[name].get("payer_id", "") or "MISSING"
        rate = get_rate(name, "visit")
        print(f"  {name:30s}  {rate:6.0f}/day  PID:{rid:10s}  → {ch}")

    print(f"\n--- Readiness ---")
    r = payer_readiness()
    print(json.dumps(r, indent=2))
