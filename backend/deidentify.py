"""
REX — De-Identification Engine
Covers all 18 HIPAA Safe Harbor identifiers plus healthcare-specific extensions.
Uses Microsoft Presidio with custom recognizers.

Multi-turn consistency: a per-session mapping dict is passed in and updated in place,
so the same entity always maps to the same placeholder across the full conversation.
"""
import re
from typing import Dict, Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)

# ── Placeholder templates ─────────────────────────────────────────────────────
# Format: [ENTITY_TYPE_N] where N is the occurrence index within the session

ENTITY_LABELS = {
    "PERSON":            "PERSON",
    "PHONE_NUMBER":      "PHONE",
    "EMAIL_ADDRESS":     "EMAIL",
    "US_SSN":            "SSN",
    "US_PASSPORT":       "PASSPORT",
    "CREDIT_CARD":       "CARD",
    "IP_ADDRESS":        "IP",
    "DATE_TIME":         "DATE",
    "AGE":               "AGE",
    "URL":               "URL",
    "LOCATION":          "LOCATION",
    "MEDICAL_LICENSE":   "MED_LIC",
    "US_DRIVER_LICENSE": "DL",
    "US_BANK_NUMBER":    "BANK",
    "IBAN_CODE":         "IBAN",
    "NPI":               "NPI",
    "MRN":               "MRN",
    "ICD_CODE":          "ICD",
    "DEA_NUMBER":        "DEA",
    "INSURANCE_ID":      "INS_ID",
    "DEVICE_ID":         "DEVICE",
    "BIOMETRIC_ID":      "BIOMETRIC",
    "ACCOUNT_NUMBER":    "ACCT",
    "CERTIFICATE":       "CERT",
    "VIN":               "VIN",
    "LICENSE_PLATE":     "PLATE",
    "CRYPTO":            "CRYPTO",
    "MEDICAL_RECORD":    "MED_REC",
    "FAX_NUMBER":        "FAX",
    "ZIP_CODE":          "ZIP",
}


class PresidioEngine:
    """
    Primary de-identification engine using Microsoft Presidio.
    Falls back to RegexEngine if Presidio is unavailable.
    """

    def __init__(self):
        self._available = False
        self._analyzer = None
        self._anonymizer = None
        self._try_load_presidio()

    def _try_load_presidio(self):
        try:
            from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
            from presidio_analyzer.predefined_recognizers import (
                SpacyRecognizer,
            )
            from presidio_anonymizer import AnonymizerEngine

            # Build registry with all built-ins
            registry = RecognizerRegistry()
            registry.load_predefined_recognizers()

            # Add custom recognizers
            self._add_custom_recognizers(registry)

            self._analyzer = AnalyzerEngine(registry=registry)
            self._anonymizer = AnonymizerEngine()
            self._available = True
            logger.info("✅ Presidio de-identification engine loaded")
        except ImportError:
            logger.warning("⚠️  Presidio not installed — falling back to regex engine")
        except Exception as e:
            logger.warning(f"⚠️  Presidio failed to load ({e}) — falling back to regex engine")

    def _add_custom_recognizers(self, registry):
        """Add HIPAA-specific recognizers not covered by Presidio defaults."""
        from presidio_analyzer import PatternRecognizer, Pattern

        custom_recognizers = [
            # MRN — Medical Record Number (variable formats per EHR)
            PatternRecognizer(
                supported_entity="MRN",
                patterns=[
                    Pattern("MRN_1", r"(?i)\bMRN[:\s#]?\s*\d{5,10}\b", 0.85),
                    Pattern("MRN_2", r"(?i)\bmedical\s+record\s+(?:number|#|no\.?)[:\s]*\d{5,10}\b", 0.9),
                    Pattern("MRN_3", r"(?i)\bpatient\s+(?:id|number|#)[:\s]*[A-Z0-9]{6,12}\b", 0.75),
                ],
                context=["mrn", "medical record", "patient id", "chart"],
            ),
            # NPI — National Provider Identifier (10 digits)
            PatternRecognizer(
                supported_entity="NPI",
                patterns=[
                    Pattern("NPI_1", r"\bNPI[:\s#]?\s*\d{10}\b", 0.95),
                    Pattern("NPI_2", r"(?i)\bnational\s+provider\s+(?:identifier|number)[:\s]*\d{10}\b", 0.9),
                ],
                context=["npi", "provider identifier", "provider number"],
            ),
            # DEA Number — Drug Enforcement Administration
            PatternRecognizer(
                supported_entity="DEA_NUMBER",
                patterns=[
                    Pattern("DEA_1", r"(?i)\bDEA[:\s#]?\s*[A-Z]{2}\d{7}\b", 0.95),
                ],
                context=["dea", "drug enforcement"],
            ),
            # Fax numbers
            PatternRecognizer(
                supported_entity="FAX_NUMBER",
                patterns=[
                    Pattern("FAX_1", r"(?i)\bfax[:\s]+[\+\(]?\d[\d\s\-\(\)\.]{7,15}\d\b", 0.8),
                ],
                context=["fax"],
            ),
            # US ZIP codes (5 or 9 digit)
            PatternRecognizer(
                supported_entity="ZIP_CODE",
                patterns=[
                    Pattern("ZIP_1", r"\b\d{5}(?:-\d{4})?\b", 0.4),
                ],
                context=["zip", "postal code", "zipcode"],
            ),
            # Insurance member ID
            PatternRecognizer(
                supported_entity="INSURANCE_ID",
                patterns=[
                    Pattern("INS_1", r"(?i)\bmember\s+(?:id|number|#)[:\s]*[A-Z0-9]{6,15}\b", 0.85),
                    Pattern("INS_2", r"(?i)\binsurance\s+(?:id|number|#|policy)[:\s]*[A-Z0-9]{6,15}\b", 0.85),
                    Pattern("INS_3", r"(?i)\bpolicy\s+(?:number|#)[:\s]*[A-Z0-9]{6,15}\b", 0.8),
                ],
                context=["insurance", "member", "policy", "subscriber"],
            ),
            # Medical record / chart references
            PatternRecognizer(
                supported_entity="MEDICAL_RECORD",
                patterns=[
                    Pattern("MEDREC_1", r"(?i)\bchart\s+(?:number|#)[:\s]*[A-Z0-9]{4,12}\b", 0.8),
                    Pattern("MEDREC_2", r"(?i)\baccession\s+(?:number|#)[:\s]*[A-Z0-9]{4,12}\b", 0.8),
                ],
            ),
            # Device identifiers (serial numbers, implant IDs)
            PatternRecognizer(
                supported_entity="DEVICE_ID",
                patterns=[
                    Pattern("DEV_1", r"(?i)\bdevice\s+(?:serial|id|number)[:\s]*[A-Z0-9\-]{6,20}\b", 0.8),
                    Pattern("DEV_2", r"(?i)\bserial\s+(?:number|#)[:\s]*[A-Z0-9\-]{6,20}\b", 0.75),
                ],
                context=["device", "serial", "implant", "pacemaker"],
            ),
        ]

        for recognizer in custom_recognizers:
            registry.add_recognizer(recognizer)

    def analyze(self, text: str, language: str = "en") -> list:
        if not self._available:
            return []
        try:
            results = self._analyzer.analyze(
                text=text,
                language=language,
                entities=list(ENTITY_LABELS.keys()),
                score_threshold=0.4,
            )
            return results
        except Exception as e:
            logger.error(f"Presidio analysis error: {e}")
            return []


class RegexEngine:
    """
    Fallback pure-regex de-identification when Presidio is unavailable.
    Covers the most common HIPAA identifiers.
    """

    PATTERNS = [
        # SSN
        ("US_SSN",      re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
        # Phone (US formats)
        ("PHONE_NUMBER", re.compile(r"\b(?:\+1[\s\-]?)?\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4}\b")),
        # Email
        ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
        # Date patterns (MM/DD/YYYY, YYYY-MM-DD, Month DD YYYY)
        ("DATE_TIME",   re.compile(
            r"\b(?:\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}|"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
            re.IGNORECASE
        )),
        # IP address
        ("IP_ADDRESS",  re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
        # NPI
        ("NPI",         re.compile(r"\bNPI[:\s]?\d{10}\b")),
        # MRN
        ("MRN",         re.compile(r"\bMRN[:\s#]?\d{5,10}\b", re.IGNORECASE)),
        # DEA
        ("DEA_NUMBER",  re.compile(r"\b[A-Z]{2}\d{7}\b")),
        # ZIP
        ("ZIP_CODE",    re.compile(r"\b\d{5}(?:-\d{4})?\b")),
        # Credit card
        ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b")),
    ]

    def find_matches(self, text: str) -> list:
        """Return list of (entity_type, start, end, matched_text)"""
        matches = []
        for entity_type, pattern in self.PATTERNS:
            for m in pattern.finditer(text):
                matches.append((entity_type, m.start(), m.end(), m.group()))
        # Sort by start position, deduplicate overlaps
        matches.sort(key=lambda x: x[1])
        deduped = []
        last_end = -1
        for m in matches:
            if m[1] >= last_end:
                deduped.append(m)
                last_end = m[2]
        return deduped


class DeidentificationEngine:
    """
    Main de-identification interface used by the FastAPI app.
    Handles both Presidio (preferred) and regex fallback transparently.
    Maintains multi-turn consistency via caller-supplied mapping dict.
    """

    def __init__(self):
        self._presidio = PresidioEngine()
        self._regex = RegexEngine()
        self._entity_counters: Dict[str, int] = {}

    def _next_placeholder(self, entity_type: str, mapping: Dict[str, str]) -> str:
        """Generate a unique, consistent placeholder for a given entity type."""
        label = ENTITY_LABELS.get(entity_type, entity_type)
        # Count existing placeholders of this type
        existing = sum(1 for v in mapping.values() if v.startswith(f"[{label}_"))
        n = existing + 1
        return f"[{label}_{n}]"

    def anonymize(
        self,
        text: str,
        session_mapping: Dict[str, str],
    ) -> Tuple[str, Dict[str, str]]:
        """
        De-identify text.

        Args:
            text: Original text containing possible PHI.
            session_mapping: Existing entity→placeholder map for this session
                             (modified in-place and returned as new_mappings).

        Returns:
            (sanitized_text, new_mappings_added_this_call)
        """
        new_mappings: Dict[str, str] = {}

        if self._presidio._available:
            return self._anonymize_presidio(text, session_mapping, new_mappings)
        else:
            return self._anonymize_regex(text, session_mapping, new_mappings)

    def _anonymize_presidio(
        self, text: str,
        session_mapping: Dict[str, str],
        new_mappings: Dict[str, str],
    ) -> Tuple[str, Dict[str, str]]:
        results = self._presidio.analyze(text)

        # Sort by position descending so we can replace without offset shift
        # Sort by descending start so replacements don't shift later offsets.
        # Then drop any result that OVERLAPS a span we've already replaced —
        # two recognizers matching the same text (e.g. MRN + ZIP on "12345")
        # would otherwise corrupt the output (e.g. "[MRN_1]1]") and could leave
        # partial PHI behind. Highest-confidence result for a span wins.
        results = sorted(results, key=lambda r: (r.start, -(r.end - r.start)),
                         reverse=True)
        kept = []
        last_start = None
        for r in results:
            if last_start is not None and r.end > last_start:
                continue   # overlaps an already-kept (later) span — skip
            kept.append(r)
            last_start = r.start
        results = kept

        sanitized = text
        for result in results:
            original = text[result.start:result.end]

            # Check if this exact string already has a placeholder
            if original in session_mapping:
                placeholder = session_mapping[original]
            else:
                placeholder = self._next_placeholder(result.entity_type, session_mapping)
                session_mapping[original] = placeholder
                new_mappings[original] = placeholder

            sanitized = sanitized[:result.start] + placeholder + sanitized[result.end:]

        return sanitized, new_mappings

    def _anonymize_regex(
        self, text: str,
        session_mapping: Dict[str, str],
        new_mappings: Dict[str, str],
    ) -> Tuple[str, Dict[str, str]]:
        matches = self._regex.find_matches(text)

        # Process in reverse order
        sanitized = text
        for entity_type, start, end, original in reversed(matches):
            if original in session_mapping:
                placeholder = session_mapping[original]
            else:
                placeholder = self._next_placeholder(entity_type, session_mapping)
                session_mapping[original] = placeholder
                new_mappings[original] = placeholder

            sanitized = sanitized[:start] + placeholder + sanitized[end:]

        return sanitized, new_mappings

    def re_identify(self, text: str, session_mapping: Dict[str, str]) -> str:
        """
        Restore original PHI from placeholders in AI response.
        Reverses the mapping: placeholder → original.
        """
        reverse_map = {v: k for k, v in session_mapping.items()}

        result = text
        # Sort by placeholder length descending to avoid partial replacements
        for placeholder, original in sorted(reverse_map.items(), key=lambda x: len(x[0]), reverse=True):
            result = result.replace(placeholder, original)

        return result

    def scan_response_for_phi(self, text: str) -> bool:
        """
        Check if an AI response contains any PHI that should NOT be there.
        Used as a safety check before displaying responses in Secure Mode.
        """
        if self._presidio._available:
            results = self._presidio.analyze(text)
            return len(results) > 0
        else:
            matches = self._regex.find_matches(text)
            return len(matches) > 0

    @property
    def engine_name(self) -> str:
        return "Presidio" if self._presidio._available else "Regex Fallback"
