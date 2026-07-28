#!/usr/bin/env python3
"""
REX — Schema Validator  (rex_schema_check.py)
Phase 10 | Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
PURPOSE
  At startup (and on demand), validate that all important state/config files
  carry the expected schema_version and minimum required structure.
  Surface any mismatch in the Command Center with a visible SCHEMA_WARNING
  state — distinct from HALTED, not as severe, but clearly visible.

REFINEMENT (Phase 10 approval)
  Schema mismatches are surfaced in the Command Center UI with:
    - affected file list
    - mismatch detail (found vs expected)
    - visible WARNING state (not HALTED, but distinct — yellow vs red)
  The Command Center GET /schema-status always returns current check results.

FAIL MODES
  "degrade":  log warning + continue (default)
  "strict":   refuse to proceed on any mismatch

KNOWN SCHEMAS (hardcoded — not config — so the validator cannot be confused
by a corrupted config file)

AUDIT EVENTS → state/prompt_audit.log
  schema_check_started, schema_check_passed, schema_check_failed (per file)
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("rex_schema_check")

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE      = Path(__file__).parent.parent
AUDIT_LOG  = _BASE / "state" / "prompt_audit.log"
CONFIG_FILE = _BASE / "config" / "session.yaml"

# ── Known schema registry ─────────────────────────────────────────────────────
# Hardcoded. A corrupted config cannot change what we consider valid.
# "version" is the expected schema_version string.
# "required_key" is a top-level key that must exist.
# "alt_version_key" allows checking _version as a fallback identifier.

KNOWN_SCHEMAS: Dict[str, Dict] = {
    "state/prompt_registry.json": {
        "required_key":    "prompts",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "Prompt Registry index",
    },
    "state/session_state.json": {
        "required_key":    "state",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "MSU session state",
    },
    "state/restore_drill_status.json": {
        "required_key":    "result",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "Restore drill status",
    },
    "ACTIVE_SYSTEM_MANIFEST.json": {
        "required_key":    "active_processes",
        "version":         "3.",
        "version_key":     "_version",
        "description":     "Active system manifest",
        "version_prefix":  True,  # _version may start with "3.x-..." — prefix match
    },
    "state/cls_aging_report.json": {
        "required_key":    "state_counts",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "CLS aging report (written on each run_aging() cycle)",
    },
    "state/rex_separation_rules.json": {
        "required_key":    "rules",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "Rex/Rexxie domain separation governance rules",
    },
    "state/rex_training_corpus.json": {
        "required_key":    "candidates",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "Rex approved training candidates corpus",
    },
    "state/rex_foundation_manifest.json": {
        "required_key":    "approved_candidate_ids",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "Rex foundation training manifest and deployment readiness",
    },
    "state/rex_training_quarantine.json": {
        "required_key":    "quarantine",
        "version":         "1.0",
        "version_key":     "schema_version",
        "description":     "Training quarantine store (metadata + hash only, no raw content)",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# RESULT TYPES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FileCheckResult:
    file:        str
    description: str
    exists:      bool
    version_ok:  bool
    key_ok:      bool
    found_version: Optional[str]
    expected_version: str
    detail:      str = ""

    @property
    def passed(self) -> bool:
        return self.exists and self.version_ok and self.key_ok

    def to_dict(self) -> Dict:
        return {**asdict(self), "passed": self.passed}


@dataclass
class SchemaCheckReport:
    schema_version: str  = "1.0"
    checked_at:     str  = ""
    fail_mode:      str  = "degrade"
    total:          int  = 0
    passed:         int  = 0
    failed:         int  = 0
    results:        List[Dict] = field(default_factory=list)
    status:         str  = "unknown"  # ok | schema_warning | schema_error

    def to_dict(self) -> Dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA CHECK ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class SchemaChecker:
    """
    Validates known state files against their expected schema_version.

    Refinement: schema mismatches are structured and surfaced in the
    Command Center as a SCHEMA_WARNING — visible, named, non-halting.
    """

    def __init__(self):
        self._fail_mode = self._load_fail_mode()

    def _load_fail_mode(self) -> str:
        if not CONFIG_FILE.exists():
            return "degrade"
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            return data.get("schema", {}).get("fail_mode", "degrade")
        except Exception:
            return "degrade"

    def run(self) -> SchemaCheckReport:
        """
        Check all known state files. Returns a structured report.
        Emits audit events. Never raises — always returns a report.
        """
        self._audit("schema_check_started")
        report = SchemaCheckReport(
            checked_at = _now_iso(),
            fail_mode  = self._fail_mode,
        )

        for rel_path, spec in KNOWN_SCHEMAS.items():
            result = self._check_file(rel_path, spec)
            report.results.append(result.to_dict())
            report.total += 1

            if result.passed:
                report.passed += 1
            else:
                report.failed += 1
                self._audit(
                    "schema_check_failed",
                    file        = rel_path,
                    description = spec["description"],
                    found       = result.found_version,
                    expected    = result.expected_version,
                    detail      = result.detail,
                )
                log.warning(
                    "Schema mismatch: %s | found=%s expected=%s | %s",
                    rel_path, result.found_version, result.expected_version, result.detail
                )

        # Determine status
        if report.failed == 0:
            report.status = "ok"
            self._audit("schema_check_passed", total=report.total)
        elif report.failed <= 2:
            report.status = "schema_warning"   # distinct from HALTED — yellow
        else:
            report.status = "schema_error"     # more severe — orange/amber

        if self._fail_mode == "strict" and report.failed > 0:
            log.error(
                "Schema check STRICT mode: %d failure(s) — system should degrade",
                report.failed
            )
            # Signal to caller that strict mode triggered
            report.status = "schema_error"

        return report

    def _check_file(self, rel_path: str, spec: Dict) -> FileCheckResult:
        full_path = _BASE / rel_path
        desc      = spec["description"]
        ver_key   = spec.get("version_key", "schema_version")
        expected  = spec["version"]
        req_key   = spec["required_key"]
        prefix    = spec.get("version_prefix", False)

        # Existence
        if not full_path.exists():
            return FileCheckResult(
                file=rel_path, description=desc,
                exists=False, version_ok=False, key_ok=False,
                found_version=None, expected_version=expected,
                detail="File does not exist",
            )

        # Parse
        try:
            data = json.loads(full_path.read_text())
        except json.JSONDecodeError as e:
            return FileCheckResult(
                file=rel_path, description=desc,
                exists=True, version_ok=False, key_ok=False,
                found_version=None, expected_version=expected,
                detail=f"JSON parse error: {e}",
            )

        # Required key
        key_ok = req_key in data

        # Version
        found_ver = str(data.get(ver_key, "MISSING"))
        if prefix:
            # e.g. expected "2.2", found "2.2-prompt-registry" → passes
            version_ok = found_ver.startswith(expected)
        else:
            version_ok = found_ver == expected

        detail = ""
        if not key_ok:
            detail = f"Required key '{req_key}' missing"
        elif not version_ok:
            detail = f"schema_version: found '{found_ver}', expected '{expected}'"

        return FileCheckResult(
            file=rel_path, description=desc,
            exists=True,
            version_ok=version_ok,
            key_ok=key_ok,
            found_version=found_ver,
            expected_version=expected,
            detail=detail,
        )

    def _audit(self, event: str, **kwargs) -> None:
        entry = {"event": event, "timestamp": _now_iso(), **kwargs}
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Schema audit write failed: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
