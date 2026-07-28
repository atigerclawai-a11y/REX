#!/usr/bin/env python3
"""
REX — Training Classifier  (rex_training_classifier.py)
Phase 12 | Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
PURPOSE
  The sole gateway between raw source material and Rex's training corpus.
  No content may enter Rex's training log without passing through here first.

DATA CLASSES (hardcoded — not config)
  public_operational    — GOJ workflows, compliance, task patterns.
                          Rex eligible after approval.
  internal_operational  — Business logic, approved procedures.
                          Rex eligible after approval.
  private_personal      — Preferences, routines, personal coordination.
                          BLOCKED from Rex. Rexxie domain only.
  restricted_sensitive  — Protected confidential, health, private strategy.
                          BLOCKED from Rex. Never enters training pipeline.

PIPELINE
  source_material
    → classify(text)       → data_class (or BLOCKED)
    → sanitize(text)       → cleaned operational text (or BLOCKED if uncertain)
    → submit_candidate()   → corpus entry with status: pending_review
    → Chairman approval    → approve/reject
    → commit_approved()    → writes to rex_training.db

REFINEMENT: SANITIZATION FAILS CLOSED
  If sanitization cannot CONFIDENTLY strip all private context from material,
  the candidate is BLOCKED — not downgraded. Optimism is not allowed here.
  The sanitizer uses a conservative signal list: if any signal remains after
  stripping, the result is treated as unclean and the candidate is blocked.

AUDIT LOG
  All events go to state/rex_training_audit.log — NOT prompt_audit.log.
  Prompt governance and Rex training are separate audit domains.

EVENTS
  rex_training_candidate_submitted
  rex_training_candidate_blocked
  rex_training_candidate_sanitized
  rex_training_candidate_approved
  rex_training_candidate_rejected
  rex_training_candidate_committed
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("rex_training_classifier")

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE           = Path(__file__).parent.parent
CORPUS_FILE     = _BASE / "state" / "rex_training_corpus.json"
QUARANTINE_FILE = _BASE / "state" / "rex_training_quarantine.json"   # Phase 13
AUDIT_LOG     = _BASE / "state" / "rex_training_audit.log"   # separate from prompt_audit.log
FOUNDATION    = _BASE / "state" / "rex_foundation_manifest.json"

# ── Data classes ───────────────────────────────────────────────────────────────
CLASS_PUBLIC_OP      = "public_operational"
CLASS_INTERNAL_OP    = "internal_operational"
CLASS_PRIVATE        = "private_personal"
CLASS_RESTRICTED     = "restricted_sensitive"

REX_ELIGIBLE_CLASSES = frozenset({CLASS_PUBLIC_OP, CLASS_INTERNAL_OP})
BLOCKED_CLASSES      = frozenset({CLASS_PRIVATE, CLASS_RESTRICTED})

# ── Classification signals ─────────────────────────────────────────────────────
# Private/restricted signals — conservative list.
# ANY match → candidate is classified as private or restricted.
_PRIVATE_SIGNALS = [
    # Emotional/personal language
    r'\b(feel|felt|feeling|emotion|anxious|stressed|worried|scared|afraid|frustrated|overwhelmed)\b',
    r'\b(therapist|therapy|counselor|counseling|mental health|depression|anxiety)\b',
    r'\b(personally|private|confidential|between us|don.t tell|secret)\b',
    r'\b(my (wife|husband|partner|family|kids|children|mother|father|brother|sister))\b',
    r'\b(health|medical|diagnosis|prescription|medication|doctor|hospital)\b',
    # Rexxie-specific markers
    r'\brexxie\b',
    r'\bprivate mode\b',
    r'\bconfidant\b',
    r'\bpersonal (?:brief|coordination|notes|planning)\b',
    # Chairman-private markers
    r'\bchairman only\b',
    r'\bkato (?:told me|said|mentioned|shared)\b',
    # Financial/legal personal
    r'\b(bank account|credit card|loan|mortgage|lawsuit|attorney|legal advice)\b',
]

_OPERATIONAL_SIGNALS = [
    r'\b(workflow|procedure|process|client|authorization|billing|attendance|route|schedule)\b',
    r'\b(GOJ|gold health|garden of joy|hipaa|compliance|medicaid)\b',
    r'\b(driver|staff|shift|menu|transport|authorization|eligibility)\b',
    r'\b(monday|tuesday|wednesday|thursday|friday)\b',
    r'\b(report|summary|checklist|template|handoff|intake)\b',
]

_COMPILED_PRIVATE = [re.compile(p, re.IGNORECASE) for p in _PRIVATE_SIGNALS]
_COMPILED_OP      = [re.compile(p, re.IGNORECASE) for p in _OPERATIONAL_SIGNALS]

# ── Sanitization: patterns to strip ────────────────────────────────────────────
# Strip these from text before classifying as operational.
_STRIP_PATTERNS = [
    # Personal names before operational nouns
    (re.compile(r'\bKato\b', re.IGNORECASE),               "[CHAIRMAN]"),
    (re.compile(r'\b(Vlad|Vladimir)\b', re.IGNORECASE),    "[STAFF]"),
    # Emotional adjectives
    (re.compile(r'\b(stressed|anxious|worried|frustrated)\b', re.IGNORECASE), "[REDACTED]"),
    # Personal relationship words
    (re.compile(r'\b(my wife|my husband|my partner|my family)\b', re.IGNORECASE), "[PERSONAL]"),
    # Rexxie references
    (re.compile(r'\brexxie\b', re.IGNORECASE),              "[PRIVATE_AI]"),
]


# ══════════════════════════════════════════════════════════════════════════════
# CLASSIFIER ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class RexTrainingClassifier:
    """
    Classification, sanitization, and gating for Rex training material.

    Refinement: sanitization FAILS CLOSED.
    If content cannot be confidently stripped to operational-only form,
    the candidate is BLOCKED — not downgraded or passed with a warning.
    """

    # ── Classification ─────────────────────────────────────────────────────────

    def classify(self, text: str) -> Tuple[str, str]:
        """
        Classify text into a data class.
        Returns (data_class, reason).

        Conservative: any private signal = private or restricted.
        Only text with zero private signals AND at least one operational signal
        may be classified as public_operational or internal_operational.
        """
        if not text or not text.strip():
            return CLASS_PRIVATE, "empty_or_whitespace"

        # Check for private/restricted signals first (conservative)
        for pattern in _COMPILED_PRIVATE:
            if pattern.search(text):
                signal = pattern.pattern[:40]
                return CLASS_PRIVATE, f"private_signal_matched: {signal}"

        # Count operational signals
        op_hits = sum(1 for p in _COMPILED_OP if p.search(text))

        if op_hits >= 2:
            return CLASS_PUBLIC_OP, f"operational_signals={op_hits}"
        elif op_hits == 1:
            return CLASS_INTERNAL_OP, f"one_operational_signal"
        else:
            # No clear signal either way — default conservative: private
            return CLASS_PRIVATE, "no_clear_operational_signal"

    # ── Sanitization ───────────────────────────────────────────────────────────

    def sanitize(self, text: str) -> Tuple[bool, str, str]:
        """
        Attempt to strip private identifiers from text.
        Returns (success, sanitized_text, reason).

        FAILS CLOSED: if any private signal remains after stripping,
        returns (False, original_text, reason). Never returns uncertain content.
        """
        if not text:
            return False, text, "empty_input"

        working = text

        # Apply strip patterns
        for pattern, replacement in _STRIP_PATTERNS:
            working = pattern.sub(replacement, working)

        # Verify: re-run private signal check on result
        for patt in _COMPILED_PRIVATE:
            if patt.search(working):
                signal = patt.pattern[:40]
                return False, text, f"private_signal_remains_after_sanitize: {signal}"

        # Verify: sanitized result must still have operational signals
        op_hits = sum(1 for p in _COMPILED_OP if p.search(working))
        if op_hits == 0:
            return False, text, "no_operational_content_remains_after_sanitize"

        return True, working.strip(), "sanitized_ok"

    # ── Submit candidate ───────────────────────────────────────────────────────

    def submit_candidate(
        self,
        text:              str,
        source:            str  = "unknown",
        trainer:           str  = "human",
        skill_cat:         str  = "general",
        force_class:       Optional[str] = None,
        training_batch_id: Optional[str] = None,   # Phase 13: batch linkage
    ) -> Dict[str, Any]:
        """
        Full pipeline: classify → sanitize → snapshot → submit to corpus.
        Phase 13 additions:
          - Creates a pre-training snapshot (Rule 4 enforcement)
          - Links snapshot_id and training_batch_id to every corpus entry
          - Blocked candidates are written to quarantine store (reviewable metadata only)
        """
        from .rex_training_snapshot import TrainingSnapshot
        snap_engine = TrainingSnapshot()

        # Auto-generate batch_id if not provided
        if not training_batch_id:
            training_batch_id = snap_engine.new_batch_id()

        # Step 1: Classify
        data_class, classify_reason = self.classify(text)
        if force_class and force_class in REX_ELIGIBLE_CLASSES:
            if data_class in REX_ELIGIBLE_CLASSES:
                data_class = force_class

        # Step 2: Block private/restricted → write to quarantine (with reviewable fields)
        if data_class in BLOCKED_CLASSES:
            self._audit("rex_training_candidate_blocked", source=source,
                        data_class=data_class, reason=classify_reason,
                        content_hash=_hash(text))
            # Refinement: quarantine with manual review override path
            self._write_quarantine(
                content_hash    = _hash(text),
                reason          = classify_reason,
                sensitivity     = data_class,
                source          = source,
                batch_id        = training_batch_id,
                retry_eligible  = False,
                reviewable      = (data_class == CLASS_PRIVATE),   # private may be salvageable; restricted never
                override_required = True,   # always — Chairman must approve any override
            )
            log.info("Classifier: BLOCKED+QUARANTINED (%s) source=%s", data_class, source)
            return {
                "ok":        False,
                "blocked":   True,
                "quarantined": True,
                "data_class": data_class,
                "reason":    classify_reason,
                "message":   f"Content classified as '{data_class}' — quarantined. Not eligible for Rex training.",
            }

        # Step 3: Sanitize (fails closed) → quarantine on failure
        ok, sanitized, san_reason = self.sanitize(text)
        if not ok:
            self._audit("rex_training_candidate_blocked", source=source,
                        data_class=data_class,
                        reason=f"sanitization_failed: {san_reason}",
                        content_hash=_hash(text))
            self._write_quarantine(
                content_hash    = _hash(text),
                reason          = f"sanitization_failed: {san_reason}",
                sensitivity     = data_class,
                source          = source,
                batch_id        = training_batch_id,
                retry_eligible  = False,
                reviewable      = True,     # sanitization failures can be manually rewritten
                override_required = True,
            )
            log.info("Classifier: BLOCKED+QUARANTINED (sanitization failed) source=%s", source)
            return {
                "ok":        False,
                "blocked":   True,
                "quarantined": True,
                "data_class": data_class,
                "reason":    f"sanitization_failed: {san_reason}",
                "message":   "Content could not be confidently sanitized. Blocked — not downgraded. Manual rewrite may be submitted.",
            }

        self._audit("rex_training_candidate_sanitized", source=source,
                    data_class=data_class, content_hash=_hash(sanitized))

        # Step 4: Create pre-training snapshot (Rule 4 — every training links to snapshot)
        snap = snap_engine.create(
            training_batch_id = training_batch_id,
            candidate_count   = 1,
        )
        snapshot_id = snap["snapshot_id"]

        # Step 5: Add to corpus as pending_review with snapshot + batch linkage
        candidate_id = f"rtc_{uuid.uuid4().hex[:8]}"
        entry = {
            "id":               candidate_id,
            "data_class":       data_class,
            "source":           source,
            "trainer":          trainer,
            "skill_cat":        skill_cat,
            "content_sanitized": sanitized,
            "content_hash":     _hash(sanitized),
            "classify_reason":  classify_reason,
            "snapshot_id":      snapshot_id,          # Phase 13: Rule 4
            "training_batch_id": training_batch_id,   # Phase 13: batch grouping
            "training_risk_level": self._compute_risk_level(data_class, source, sanitized),  # optional improvement
            "status":           "pending_review",
            "submitted_at":     _now_iso(),
            "approved_at":      None,
            "approved_by":      None,
            "rejected_at":      None,
            "rejected_reason":  None,
            "committed_to_rex": False,
        }
        self._append_to_corpus(entry)
        self._audit("rex_training_candidate_submitted", candidate_id=candidate_id,
                    source=source, data_class=data_class, skill_cat=skill_cat,
                    snapshot_id=snapshot_id, batch_id=training_batch_id,
                    content_hash=_hash(sanitized))
        log.info("Classifier: submitted candidate %s (%s) from %s",
                 candidate_id, data_class, source)

        return {
            "ok":               True,
            "candidate_id":     candidate_id,
            "data_class":       data_class,
            "snapshot_id":      snapshot_id,
            "training_batch_id": training_batch_id,
            "status":           "pending_review",
            "message":          (
                f"Candidate {candidate_id} submitted for Chairman review. "
                f"Class: {data_class}. Snapshot: {snapshot_id}. "
                f"Approve via: 'approve training {candidate_id}'"
            ),
        }

    # ── Approve / reject ───────────────────────────────────────────────────────

    def approve_candidate(self, candidate_id: str, approved_by: str = "chairman") -> Dict[str, Any]:
        """Mark a candidate approved. Does not commit to rex_training.db yet."""
        corpus = self._load_corpus()
        for entry in corpus["candidates"]:
            if entry["id"] == candidate_id:
                if entry["status"] != "pending_review":
                    return {"ok": False, "error": f"Status is '{entry['status']}' — cannot approve"}
                entry["status"]      = "approved"
                entry["approved_at"] = _now_iso()
                entry["approved_by"] = approved_by
                self._save_corpus(corpus)
                self._update_foundation(candidate_id)
                self._audit("rex_training_candidate_approved", candidate_id=candidate_id,
                            approved_by=approved_by, data_class=entry["data_class"])
                return {"ok": True, "candidate_id": candidate_id, "status": "approved"}
        return {"ok": False, "error": f"Candidate '{candidate_id}' not found"}

    def reject_candidate(self, candidate_id: str, reason: str = "") -> Dict[str, Any]:
        """Mark a candidate rejected. Never committed to Rex."""
        corpus = self._load_corpus()
        for entry in corpus["candidates"]:
            if entry["id"] == candidate_id:
                if entry["status"] != "pending_review":
                    return {"ok": False, "error": f"Status is '{entry['status']}' — cannot reject"}
                entry["status"]          = "rejected"
                entry["rejected_at"]     = _now_iso()
                entry["rejected_reason"] = reason
                self._save_corpus(corpus)
                self._audit("rex_training_candidate_rejected", candidate_id=candidate_id,
                            reason=reason)
                return {"ok": True, "candidate_id": candidate_id, "status": "rejected"}
        return {"ok": False, "error": f"Candidate '{candidate_id}' not found"}

    def commit_approved(self, candidate_id: str, training_db_path: str) -> Dict[str, Any]:
        """
        Commit an approved candidate to rex_training.db.
        Only approved candidates may be committed. Writes with data_class tag.
        """
        corpus = self._load_corpus()
        target = None
        for entry in corpus["candidates"]:
            if entry["id"] == candidate_id:
                target = entry
                break
        if not target:
            return {"ok": False, "error": f"Candidate '{candidate_id}' not found"}
        if target["status"] != "approved":
            return {"ok": False, "error": f"Candidate must be approved first (status={target['status']})"}
        if target["committed_to_rex"]:
            return {"ok": False, "error": f"Candidate '{candidate_id}' already committed"}

        # Phase 13 / Rule 4: snapshot_id must be present before commit (fail-closed)
        if not target.get("snapshot_id"):
            self._audit("rex_training_candidate_blocked",
                        candidate_id=candidate_id, reason="missing_snapshot_id")
            return {
                "ok":    False,
                "error": (
                    f"Candidate '{candidate_id}' has no snapshot_id — commit blocked. "
                    "Rule 4: every training event must link to a pre-training snapshot."
                ),
            }

        # Write to training DB with data_class tag
        import sqlite3
        con = sqlite3.connect(training_db_path)
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS rex_training_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT, trainer TEXT, authority TEXT,
                    skill_cat TEXT, lesson TEXT, detail TEXT,
                    data_class TEXT NOT NULL DEFAULT 'public_operational',
                    candidate_id TEXT,
                    created_at TEXT
                )
            """)
            # Add data_class column if missing (migration safety)
            try:
                con.execute("ALTER TABLE rex_training_log ADD COLUMN data_class TEXT NOT NULL DEFAULT 'public_operational'")
            except Exception:
                pass
            try:
                con.execute("ALTER TABLE rex_training_log ADD COLUMN candidate_id TEXT")
            except Exception:
                pass
            con.execute("""
                INSERT INTO rex_training_log
                    (session_id, trainer, authority, skill_cat, lesson, detail, data_class, candidate_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "corpus_commit",
                target.get("trainer", "human"),
                "CORPUS",
                target.get("skill_cat", "general"),
                target["content_sanitized"],
                f"corpus_candidate:{candidate_id}",
                target["data_class"],
                candidate_id,
                _now_iso(),
            ))
            con.commit()
        finally:
            con.close()

        # Mark committed
        target["committed_to_rex"] = True
        self._save_corpus(corpus)
        self._audit("rex_training_candidate_committed", candidate_id=candidate_id,
                    data_class=target["data_class"])
        log.info("Committed candidate %s (%s) to rex_training.db", candidate_id, target["data_class"])
        return {"ok": True, "candidate_id": candidate_id, "committed": True}

    def list_candidates(self, status: Optional[str] = None) -> List[Dict]:
        corpus = self._load_corpus()
        candidates = corpus.get("candidates", [])
        if status:
            candidates = [c for c in candidates if c["status"] == status]
        return candidates

    # ── Corpus I/O ─────────────────────────────────────────────────────────────

    def _write_quarantine(
        self,
        content_hash:     str,
        reason:           str,
        sensitivity:      str,
        source:           str,
        batch_id:         str,
        retry_eligible:   bool = False,
        reviewable:       bool = False,
        override_required: bool = True,
    ) -> None:
        """
        Phase 13 refinement: write blocked candidate to quarantine store.
        Stores metadata only — never raw content.
        Refinement: includes reviewable and override_required fields for manual review path.
        override_required is ALWAYS True — Chairman must approve any override.
        """
        entry = {
            "id":               f"qtc_{uuid.uuid4().hex[:8]}",
            "quarantined_at":   _now_iso(),
            "content_hash":     content_hash,     # hash only — never raw content
            "reason":           reason,
            "sensitivity_class": sensitivity,
            "source_type":      source,
            "training_batch_id": batch_id,
            "retry_eligible":   retry_eligible,
            "reviewable":       reviewable,        # can be manually rewritten + resubmitted
            "override_required": override_required, # always True — Chairman gate never bypassed
            "review_status":    "awaiting_review" if reviewable else "not_applicable",
            "status":           "quarantined",
            "reviewer_needed":  reviewable,
        }
        try:
            if QUARANTINE_FILE.exists():
                qdata = json.loads(QUARANTINE_FILE.read_text())
            else:
                qdata = {"schema_version":"1.0","quarantine":[]}
            qdata["quarantine"].append(entry)
            tmp = QUARANTINE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(qdata, indent=2))
            tmp.replace(QUARANTINE_FILE)
        except Exception as e:
            log.error("Quarantine write failed: %s", e)

    @staticmethod
    def _compute_risk_level(data_class: str, source: str, content: str) -> str:
        """
        Optional improvement: compute training risk level per candidate.
        Based on data_class, source, and content length/complexity.
        Returns: low | medium | high
        """
        if data_class == CLASS_PUBLIC_OP:
            base = "low"
        else:
            base = "medium"
        # Elevate if source is from training session (not queue)
        if "rex_training" in source:
            base = "medium" if base == "low" else "high"
        # Elevate for long content (more surface area)
        if len(content) > 500:
            base = "medium" if base == "low" else base
        return base

    def _load_corpus(self) -> Dict:
        if not CORPUS_FILE.exists():
            return self._initial_corpus()
        try:
            return json.loads(CORPUS_FILE.read_text())
        except Exception:
            return self._initial_corpus()

    def _save_corpus(self, corpus: Dict) -> None:
        corpus["_updated"] = _now_iso()
        tmp = CORPUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(corpus, indent=2))
        tmp.replace(CORPUS_FILE)

    def _append_to_corpus(self, entry: Dict) -> None:
        corpus = self._load_corpus()
        corpus["candidates"].append(entry)
        corpus["total_submitted"] = corpus.get("total_submitted", 0) + 1
        self._save_corpus(corpus)

    @staticmethod
    def _initial_corpus() -> Dict:
        return {
            "schema_version":  "1.0",
            "_created":        _now_iso(),
            "_updated":        _now_iso(),
            "_rule":           "Only Chairman-approved sanitized operational content may be committed to Rex.",
            "corpus_version":  "0.1",
            "total_submitted": 0,
            "total_approved":  0,
            "total_committed": 0,
            "candidates":      [],
        }

    # ── Foundation manifest update ─────────────────────────────────────────────

    def _update_foundation(self, candidate_id: str) -> None:
        """Update rex_foundation_manifest.json when a candidate is approved."""
        try:
            if FOUNDATION.exists():
                manifest = json.loads(FOUNDATION.read_text())
            else:
                manifest = _initial_foundation()

            approved_ids = manifest.get("approved_candidate_ids", [])
            if candidate_id not in approved_ids:
                approved_ids.append(candidate_id)
            manifest["approved_candidate_ids"] = approved_ids
            manifest["last_review_at"]         = _now_iso()
            manifest["corpus_version"]         = _corpus_version(manifest)
            tmp = FOUNDATION.with_suffix(".tmp")
            tmp.write_text(json.dumps(manifest, indent=2))
            tmp.replace(FOUNDATION)
        except Exception as e:
            log.error("Foundation manifest update failed: %s", e)

    # ── Audit ──────────────────────────────────────────────────────────────────

    def _audit(self, event: str, **kwargs) -> None:
        """Write to state/rex_training_audit.log — separate from prompt_audit.log."""
        entry = {"event": event, "timestamp": _now_iso(), **kwargs}
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Training audit write failed: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def _corpus_version(manifest: Dict) -> str:
    n = len(manifest.get("approved_candidate_ids", []))
    return f"0.{n}"

def _initial_foundation() -> Dict:
    return {
        "schema_version":           "1.0",
        "_created":                 _now_iso(),
        "_rule":                    "Rex foundation — approved operational training corpus only.",
        "corpus_version":           "0.0",
        "approved_candidate_ids":   [],
        "last_review_at":           None,
        "last_export_review_at":    None,
        "deployment_eligible":      False,
        "deployment_notes":         "Not yet reviewed for deployment eligibility.",
    }
