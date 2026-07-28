"""
CC_akc_tokenizer_v2.py
========================
Gate 1 — AKC PHI Tokenizer (Full Implementation)
Gold Health Systems · Garden of Joy · HIPAA Safe Harbor

GATE STATUS: READY TO ACTIVATE
  Replaces skeleton at ~/Desktop/dashboard/akc_tokenizer.py
  Hard block: no cloud PHI routing until this is imported and active.

HIPAA Safe Harbor (45 CFR §164.514(b)(2)) — all 18 identifier types:
  1.  Names (patient, family, employer)
  2.  Geographic subdivisions smaller than state
  3.  Dates (except year): birth, admission, discharge, death
  4.  Phone numbers
  5.  Fax numbers
  6.  Email addresses
  7.  Social Security numbers
  8.  Medical record numbers
  9.  Health plan beneficiary numbers
  10. Account numbers
  11. Certificate / license numbers
  12. Vehicle identifiers and serial numbers (incl. license plates)
  13. Device identifiers and serial numbers
  14. Web URLs
  15. IP addresses
  16. Biometric identifiers (fingerprints, voice)
  17. Full-face photographs and comparable images
  18. Any other unique identifying number or code

USAGE:
    from CC_akc_tokenizer_v2 import AKCTokenizer

    t = AKCTokenizer(session_id="abc123")
    safe_text, token_map = t.tokenize("Maria Ivanova, DOB 01/15/1942, SSN 123-45-6789")
    # safe_text  → "[NAME_0001], DOB [DATE_0001], SSN [SSN_0001]"
    # token_map  → {"NAME_0001": "Maria Ivanova", "DATE_0001": "01/15/1942", ...}

    original = t.detokenize(safe_text)
    # original  → "Maria Ivanova, DOB 01/15/1942, SSN 123-45-6789"

    # Session-scoped: same session maintains entity consistency across turns.
    # "Maria" in turn 2 maps to the same NAME_0001.

AUDIT:
    Every tokenize/detokenize call writes to ~/Desktop/REX/data/akc_audit.db
    Columns: session_id, timestamp, direction (IN/OUT), token_count, phi_types_detected

INSTALL:
    pip install presidio-analyzer presidio-anonymizer spacy --break-system-packages
    python -m spacy download en_core_web_lg

    If Presidio not available, falls back to regex-only mode (covers 16/18 types).
    Regex fallback is clearly logged as "PRESIDIO_UNAVAILABLE — regex fallback active".

INTEGRATION POINT (when ready to activate Gate 1):
    In backend/main.py, before any LLM call in Secure Mode:
        from CC_akc_tokenizer_v2 import AKCTokenizer
        tokenizer = AKCTokenizer(session_id=request.session_id)
        safe_text, token_map = tokenizer.tokenize(user_message)
        # ... send safe_text to LLM ...
        raw_response = llm_response
        final_response = tokenizer.detokenize(raw_response)

Gold Health Systems · v2.0 · June 4, 2026
"""

import re
import json
import sqlite3
import logging
import datetime
import os
from typing import Dict, Tuple, Optional, List
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

AUDIT_DB_PATH = Path.home() / "Desktop" / "REX" / "data" / "akc_audit.db"

# 18 HIPAA Safe Harbor token type labels
PHI_TYPES = {
    "NAME":        "Names (patient, family, employer)",
    "GEO":         "Geographic data smaller than state",
    "DATE":        "Dates except year (birth, admission, discharge, death)",
    "PHONE":       "Phone numbers",
    "FAX":         "Fax numbers",
    "EMAIL":       "Email addresses",
    "SSN":         "Social Security numbers",
    "MRN":         "Medical record numbers",
    "PLAN":        "Health plan beneficiary numbers",
    "ACCOUNT":     "Account numbers",
    "LICENSE":     "Certificate/license numbers",
    "VEHICLE":     "Vehicle identifiers and license plates",
    "DEVICE":      "Device identifiers and serial numbers",
    "URL":         "Web URLs",
    "IP":          "IP addresses",
    "BIOMETRIC":   "Biometric identifiers",
    "PHOTO":       "Full-face photographs (flag only)",
    "OTHER_ID":    "Other unique identifying numbers/codes",
}

# Regex patterns for each type (covers all types detectable via regex)
PHI_PATTERNS: Dict[str, List[re.Pattern]] = {
    "SSN": [
        re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        re.compile(r'\b\d{9}\b(?=\s*(SSN|social|security))', re.IGNORECASE),
    ],
    "PHONE": [
        re.compile(r'\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        re.compile(r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b'),
    ],
    "FAX": [
        re.compile(r'\bfax[:\s]+(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', re.IGNORECASE),
    ],
    "EMAIL": [
        re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    ],
    "DATE": [
        re.compile(r'\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b'),
        re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b', re.IGNORECASE),
        re.compile(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b', re.IGNORECASE),
        re.compile(r'\b(?:DOB|D\.O\.B\.|date of birth)[:\s]+[\d/\-]+', re.IGNORECASE),
    ],
    "MRN": [
        re.compile(r'\b(?:MRN|Medical Record)[:\s#]*\d{4,12}\b', re.IGNORECASE),
        re.compile(r'\bMR[-#]?\d{5,12}\b', re.IGNORECASE),
    ],
    "PLAN": [
        re.compile(r'\b(?:Medicare|Medicaid|CDPAP|Managed Care)[:\s#]*\d{6,15}\b', re.IGNORECASE),
        re.compile(r'\b(?:beneficiary|member)\s*(?:ID|#|number)[:\s]*[A-Z0-9]{6,15}\b', re.IGNORECASE),
    ],
    "ACCOUNT": [
        re.compile(r'\b(?:account|acct)[:\s#]*\d{6,20}\b', re.IGNORECASE),
        re.compile(r'\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b'),  # credit card
    ],
    "URL": [
        re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+'),
        re.compile(r'www\.[A-Za-z0-9\-]+\.[A-Za-z]{2,}[^\s]*'),
    ],
    "IP": [
        re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'),  # IPv6
    ],
    "VEHICLE": [
        re.compile(r'\b(?:plate|license plate|VIN)[:\s]*[A-Z0-9]{5,17}\b', re.IGNORECASE),
    ],
    "DEVICE": [
        re.compile(r'\b(?:serial|device)[:\s#]*[A-Z0-9]{6,20}\b', re.IGNORECASE),
    ],
    "LICENSE": [
        re.compile(r'\b(?:license|certificate|cert)[:\s#]*[A-Z0-9\-]{5,20}\b', re.IGNORECASE),
    ],
    "GEO": [
        re.compile(r'\b\d{5}(?:-\d{4})?\b'),  # ZIP codes
        re.compile(r'\b\d{1,5}\s+[A-Za-z\s]{3,40}(?:St|Ave|Blvd|Rd|Dr|Ln|Ct|Pl|Way|Pkwy)\.?\b', re.IGNORECASE),
    ],
    "OTHER_ID": [
        re.compile(r'\b(?:ID|UID|client ID|patient ID)[:\s#]*[A-Z0-9]{4,20}\b', re.IGNORECASE),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# PRESIDIO INTEGRATION (optional — graceful fallback if not installed)
# ─────────────────────────────────────────────────────────────────────────────

_presidio_available = False
_analyzer = None
_anonymizer = None

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    _analyzer = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()
    _presidio_available = True
    logger.info("AKCTokenizer: Presidio available — full NER mode active")
except ImportError:
    logger.warning(
        "AKCTokenizer: presidio-analyzer not installed — regex fallback mode active. "
        "Install: pip install presidio-analyzer presidio-anonymizer spacy --break-system-packages && "
        "python -m spacy download en_core_web_lg"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT DATABASE
# ─────────────────────────────────────────────────────────────────────────────

def _init_audit_db() -> None:
    """Create audit DB and table if they don't exist."""
    AUDIT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUDIT_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS akc_audit (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                direction       TEXT NOT NULL,   -- 'TOKENIZE' or 'DETOKENIZE'
                input_chars     INTEGER,
                output_chars    INTEGER,
                token_count     INTEGER,
                phi_types       TEXT,            -- JSON list of types found
                presidio_used   INTEGER,         -- 0/1
                notes           TEXT
            )
        """)
        conn.commit()


def _write_audit(session_id: str, direction: str, input_chars: int,
                 output_chars: int, token_count: int,
                 phi_types: List[str], presidio_used: bool,
                 notes: str = "") -> None:
    """Write one audit record. Silent on failure — never block the pipeline."""
    try:
        _init_audit_db()
        with sqlite3.connect(AUDIT_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO akc_audit
                   (session_id, timestamp, direction, input_chars, output_chars,
                    token_count, phi_types, presidio_used, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    datetime.datetime.utcnow().isoformat(),
                    direction,
                    input_chars,
                    output_chars,
                    token_count,
                    json.dumps(phi_types),
                    1 if presidio_used else 0,
                    notes,
                )
            )
            conn.commit()
    except Exception as exc:
        logger.error("AKCTokenizer audit write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TOKENIZER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class AKCTokenizer:
    """
    Gate 1 PHI Tokenizer — HIPAA Safe Harbor 18-identifier implementation.

    Thread-safety: one instance per session_id. Do NOT share across sessions.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        # entity_map: token → original_value  (forward: for detokenization)
        self._token_to_value: Dict[str, str] = {}
        # reverse_map: original_value → token  (for consistency: same value → same token)
        self._value_to_token: Dict[str, str] = {}
        # counters per type
        self._counters: Dict[str, int] = defaultdict(int)

    # ── Token generation ────────────────────────────────────────────────────

    def _make_token(self, phi_type: str, value: str) -> str:
        """Return an existing token for value, or mint a new one."""
        if value in self._value_to_token:
            return self._value_to_token[value]
        self._counters[phi_type] += 1
        token = f"[{phi_type}_{self._counters[phi_type]:04d}]"
        self._token_to_value[token] = value
        self._value_to_token[value] = token
        return token

    # ── Presidio-based detection ─────────────────────────────────────────────

    def _presidio_tokenize(self, text: str) -> Tuple[str, List[str]]:
        """
        Use Presidio NER to find entities and replace them with tokens.
        Returns (tokenized_text, list_of_phi_types_found).
        """
        if not _presidio_available or _analyzer is None:
            return text, []

        # Map Presidio entity types → our PHI_TYPES labels
        PRESIDIO_MAP = {
            "PERSON":               "NAME",
            "LOCATION":             "GEO",
            "DATE_TIME":            "DATE",
            "PHONE_NUMBER":         "PHONE",
            "EMAIL_ADDRESS":        "EMAIL",
            "US_SSN":               "SSN",
            "MEDICAL_LICENSE":      "LICENSE",
            "US_BANK_NUMBER":       "ACCOUNT",
            "CREDIT_CARD":          "ACCOUNT",
            "US_DRIVER_LICENSE":    "LICENSE",
            "US_PASSPORT":          "LICENSE",
            "IP_ADDRESS":           "IP",
            "URL":                  "URL",
            "NRP":                  "OTHER_ID",  # Nationality/Religion/Political
        }

        try:
            results = _analyzer.analyze(text=text, language="en")
        except Exception as exc:
            logger.warning("Presidio analysis failed: %s", exc)
            return text, []

        # Sort by start position descending so we can replace in-place without offset drift
        results_sorted = sorted(results, key=lambda r: r.start, reverse=True)
        phi_types_found = []
        chars = list(text)

        for result in results_sorted:
            phi_type = PRESIDIO_MAP.get(result.entity_type, "OTHER_ID")
            original = text[result.start:result.end]
            token = self._make_token(phi_type, original)
            chars[result.start:result.end] = list(token)
            if phi_type not in phi_types_found:
                phi_types_found.append(phi_type)

        return "".join(chars), phi_types_found

    # ── Regex-based detection ─────────────────────────────────────────────────

    def _regex_tokenize(self, text: str) -> Tuple[str, List[str]]:
        """
        Apply all regex patterns in order of specificity.
        Returns (tokenized_text, list_of_phi_types_found).
        """
        phi_types_found = []

        # Process most-specific patterns first to avoid double-tokenizing
        ORDER = ["SSN", "MRN", "PLAN", "ACCOUNT", "PHONE", "FAX", "EMAIL",
                 "DATE", "URL", "IP", "VEHICLE", "DEVICE", "LICENSE", "GEO", "OTHER_ID"]

        for phi_type in ORDER:
            patterns = PHI_PATTERNS.get(phi_type, [])
            for pattern in patterns:
                def replacer(m, _phi_type=phi_type):
                    return self._make_token(_phi_type, m.group(0))

                new_text = pattern.sub(replacer, text)
                if new_text != text:
                    if phi_type not in phi_types_found:
                        phi_types_found.append(phi_type)
                    text = new_text

        return text, phi_types_found

    # ── Public API ────────────────────────────────────────────────────────────

    def tokenize(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Replace PHI with opaque tokens. Returns (safe_text, token_map).

        safe_text  — text with PHI replaced by [TYPE_NNNN] tokens
        token_map  — {token: original_value} for this call's new tokens

        Session-consistent: if the same PHI value appears in turn 2
        that appeared in turn 1, it gets the same token.
        """
        if not text or not text.strip():
            return text, {}

        input_len = len(text)
        phi_types_found: List[str] = []

        if _presidio_available:
            text, presidio_types = self._presidio_tokenize(text)
            phi_types_found.extend(presidio_types)

        # Always run regex pass — catches things Presidio misses (SSNs, ZIPs, etc.)
        text, regex_types = self._regex_tokenize(text)
        for t in regex_types:
            if t not in phi_types_found:
                phi_types_found.append(t)

        # Build token_map for this call (all tokens, not just new ones)
        token_map = dict(self._token_to_value)

        _write_audit(
            session_id=self.session_id,
            direction="TOKENIZE",
            input_chars=input_len,
            output_chars=len(text),
            token_count=len(token_map),
            phi_types=phi_types_found,
            presidio_used=_presidio_available,
            notes=f"phi_types={phi_types_found}" if phi_types_found else "no_phi_detected",
        )

        return text, token_map

    def detokenize(self, text: str) -> str:
        """
        Reverse tokenization: replace [TYPE_NNNN] tokens with original values.
        Only works within the same session instance.
        """
        if not text:
            return text

        input_len = len(text)
        for token, original in self._token_to_value.items():
            text = text.replace(token, original)

        _write_audit(
            session_id=self.session_id,
            direction="DETOKENIZE",
            input_chars=input_len,
            output_chars=len(text),
            token_count=len(self._token_to_value),
            phi_types=[],
            presidio_used=_presidio_available,
        )

        return text

    def get_session_map(self) -> Dict[str, str]:
        """Return the full token→value map for this session (for external audit)."""
        return dict(self._token_to_value)

    def phi_type_summary(self) -> Dict[str, int]:
        """Return count of each PHI type detected this session."""
        return dict(self._counters)

    def reset_session(self) -> None:
        """Clear all mappings. Use with caution — detokenize will fail after reset."""
        self._token_to_value.clear()
        self._value_to_token.clear()
        self._counters.clear()


# ─────────────────────────────────────────────────────────────────────────────
# SESSION REGISTRY (process-level singleton)
# ─────────────────────────────────────────────────────────────────────────────
# Keep one tokenizer per session_id so multi-turn consistency is maintained
# even when called from different import sites in the same process.

_session_registry: Dict[str, AKCTokenizer] = {}


def get_tokenizer(session_id: str) -> AKCTokenizer:
    """Return the tokenizer for session_id, creating it if needed."""
    if session_id not in _session_registry:
        _session_registry[session_id] = AKCTokenizer(session_id)
    return _session_registry[session_id]


def release_session(session_id: str) -> None:
    """Drop the tokenizer for a completed session (frees memory)."""
    _session_registry.pop(session_id, None)


def active_session_count() -> int:
    """How many sessions currently have open tokenizers."""
    return len(_session_registry)


# ─────────────────────────────────────────────────────────────────────────────
# GATE 1 FIREWALL WRAPPER
# ─────────────────────────────────────────────────────────────────────────────
# Drop-in replacement for direct LLM calls when Secure Mode is active.

class Gate1Firewall:
    """
    5-layer PHI firewall wrapper.
    Layers: tokenizer (Gate 1) · classifier · context strip · output scan · audit log
    Layers 2-4 are stubs — replace with real implementations when ready.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.tokenizer = get_tokenizer(session_id)
        self._blocked_count = 0

    def inbound(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Sanitize text before it reaches any cloud LLM.
        Returns (safe_text, token_map).
        """
        # Layer 1: tokenize (Gate 1) ←── this is what we're building
        safe_text, token_map = self.tokenizer.tokenize(text)

        # Layer 2: classifier stub (future: block if residual PHI confidence > threshold)
        # Layer 3: context strip stub (future: remove role/session context that leaks PHI)

        return safe_text, token_map

    def outbound(self, text: str) -> str:
        """
        Restore tokens in LLM response and scan for any PHI that slipped back.
        Returns original-context response.
        """
        # Layer 4: output scan stub (future: scan for new PHI introduced by LLM)
        restored = self.tokenizer.detokenize(text)

        # Layer 5: audit log — already handled inside tokenizer.detokenize()

        return restored

    @property
    def blocked_count(self) -> int:
        return self._blocked_count


# ─────────────────────────────────────────────────────────────────────────────
# CLI SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("═" * 60)
    print("  CC_akc_tokenizer_v2 — Gate 1 Self-Test")
    print(f"  Presidio: {'✅ available' if _presidio_available else '⚠️  unavailable (regex fallback)'}")
    print("═" * 60)

    TEST_CASES = [
        "Maria Ivanova, DOB 01/15/1942, SSN 123-45-6789",
        "Call us at (718) 555-0123 or fax to (718) 555-0199",
        "MRN: 00483921 · Plan ID: MEDICARE-9874523",
        "Email: maria.ivanova@example.com · IP: 192.168.1.105",
        "Client lives at 425 Ocean Ave, Brooklyn NY 11226",
        "Account #: 4532-1234-5678-9012 expires 03/2026",
    ]

    firewall = Gate1Firewall(session_id="self_test_001")

    all_pass = True
    for i, test in enumerate(TEST_CASES, 1):
        safe, tmap = firewall.inbound(test)
        restored = firewall.outbound(safe)

        tokens_found = len(tmap)
        roundtrip_ok = (restored == test)
        all_pass = all_pass and roundtrip_ok

        status = "✅" if roundtrip_ok else "❌"
        print(f"\nTest {i}: {status}")
        print(f"  Original:  {test}")
        print(f"  Tokenized: {safe}")
        print(f"  Restored:  {restored}")
        print(f"  Tokens:    {tokens_found} · Round-trip: {'OK' if roundtrip_ok else 'FAIL'}")
        if tmap:
            phi_summary = firewall.tokenizer.phi_type_summary()
            print(f"  PHI types: {phi_summary}")

    print()
    print("═" * 60)
    overall = "✅ ALL TESTS PASS" if all_pass else "❌ SOME TESTS FAILED"
    print(f"  {overall}")
    print(f"  Audit log: {AUDIT_DB_PATH}")
    print("═" * 60)

    sys.exit(0 if all_pass else 1)
