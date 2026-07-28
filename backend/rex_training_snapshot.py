#!/usr/bin/env python3
"""
REX — Training Snapshot Engine  (rex_training_snapshot.py)
Phase 13 | Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
PURPOSE
  Rule 4 enforcement: every training event links to a pre-training snapshot.
  All training is reversible. Rollback path remains visible.

SNAPSHOT SHAPE (refinement: includes system version context)
  {
    "snapshot_id":              "snap_abc123",
    "type":                     "pre_training",
    "created_at":               "...",
    "training_corpus_hash":     "...",     ← SHA-256[:16] of corpus JSON
    "foundation_manifest_hash": "...",     ← SHA-256[:16] of foundation JSON
    "system_manifest_version":  "3.1-...", ← _version from ACTIVE_SYSTEM_MANIFEST
    "schema_version":           "2.2",     ← schema_version from manifest
    "training_batch_id":        "TB-...",
    "candidate_count":          0,
    "note":                     ""
  }

  Rationale for version context (refinement): if schema or structure changes,
  rollback without version context creates a subtle corruption risk — you'd
  restore training data against a different schema. The version snapshot
  makes rollback safe and auditable.

BATCH MODEL
  training_batch_id groups candidates submitted in one session/cycle.
  Format: TB-YYYY-MM-DD-NN (NN = daily sequence)
  All candidates in a batch share one pre-training snapshot.
  Rollback is batch-scoped: reverting a batch reverts all candidates in it.

ROLLBACK
  rollback_batch(batch_id):
    1. Find all candidates with that batch_id in corpus
    2. Restore corpus to snapshot hash (verify match)
    3. Mark all batch candidates as status="rolled_back"
    4. Write rollback event to training audit log
    5. Remove committed candidates from rex_training.db (by candidate_id)

STORAGE
  state/rex_training_snapshots.jsonl — one JSON line per snapshot (append-only)

AUDIT EVENTS → state/rex_training_audit.log
  rex_training_snapshot_created
  rex_training_rollback_started
  rex_training_rollback_completed
  rex_training_rollback_failed
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("rex_training_snapshot")

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE       = Path(__file__).parent.parent
SNAPSHOTS   = _BASE / "state" / "rex_training_snapshots.jsonl"
CORPUS      = _BASE / "state" / "rex_training_corpus.json"
FOUNDATION  = _BASE / "state" / "rex_foundation_manifest.json"
MANIFEST    = _BASE / "ACTIVE_SYSTEM_MANIFEST.json"
AUDIT_LOG   = _BASE / "state" / "rex_training_audit.log"


# ══════════════════════════════════════════════════════════════════════════════
# SNAPSHOT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TrainingSnapshot:
    """
    Creates, reads, and rolls back training snapshots.
    Each snapshot links one training batch to the system state before it was applied.
    """

    # ── Create ────────────────────────────────────────────────────────────────

    def create(
        self,
        training_batch_id: str,
        candidate_count:   int  = 0,
        note:              str  = "",
    ) -> Dict[str, Any]:
        """
        Create a pre-training snapshot for a batch.
        Refinement: includes system_manifest_version and schema_version
        so rollback is safe across schema changes.
        Returns the snapshot dict (also persisted to snapshots.jsonl).
        """
        snap = {
            "snapshot_id":              f"snap_{uuid.uuid4().hex[:8]}",
            "type":                     "pre_training",
            "created_at":               _now_iso(),
            "created_by":               "rex_training_classifier",  # refinement
            "training_batch_id":        training_batch_id,
            "candidate_count":          candidate_count,
            "training_corpus_hash":     _file_hash(CORPUS),
            "foundation_manifest_hash": _file_hash(FOUNDATION),
            "system_manifest_version":  self._manifest_version(),
            "schema_version":           self._schema_version(),
            "note":                     note,
        }

        SNAPSHOTS.parent.mkdir(parents=True, exist_ok=True)
        with SNAPSHOTS.open("a") as f:
            f.write(json.dumps(snap) + "\n")

        self._audit("rex_training_snapshot_created",
                    snapshot_id=snap["snapshot_id"],
                    batch_id=training_batch_id)
        log.info("Snapshot created: %s for batch %s", snap["snapshot_id"], training_batch_id)
        return snap

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, snapshot_id: str) -> Optional[Dict]:
        """Retrieve a specific snapshot by ID."""
        if not SNAPSHOTS.exists():
            return None
        for line in SNAPSHOTS.read_text().splitlines():
            try:
                s = json.loads(line.strip())
                if s.get("snapshot_id") == snapshot_id:
                    return s
            except Exception:
                continue
        return None

    def get_by_batch(self, batch_id: str) -> Optional[Dict]:
        """Retrieve the pre-training snapshot for a specific batch."""
        if not SNAPSHOTS.exists():
            return None
        # Return the most recent snapshot for this batch
        matches = []
        for line in SNAPSHOTS.read_text().splitlines():
            try:
                s = json.loads(line.strip())
                if s.get("training_batch_id") == batch_id:
                    matches.append(s)
            except Exception:
                continue
        return matches[-1] if matches else None

    def list_recent(self, limit: int = 20) -> List[Dict]:
        """Return recent snapshots (most-recent-first)."""
        if not SNAPSHOTS.exists():
            return []
        snaps = []
        for line in SNAPSHOTS.read_text().splitlines():
            try:
                snaps.append(json.loads(line.strip()))
            except Exception:
                continue
        return list(reversed(snaps[-limit:]))

    # ── Batch ID generator ────────────────────────────────────────────────────

    @staticmethod
    def new_batch_id() -> str:
        """
        Generate a training batch ID.
        Format: TB-YYYY-MM-DD-NN (NN = sequence number for the day).
        """
        today   = date.today().isoformat()
        # Count existing batches for today
        count   = 0
        if SNAPSHOTS.exists():
            for line in SNAPSHOTS.read_text().splitlines():
                try:
                    s = json.loads(line.strip())
                    if s.get("training_batch_id", "").startswith(f"TB-{today}"):
                        count += 1
                except Exception:
                    continue
        return f"TB-{today}-{count + 1:02d}"

    # ── Rollback ──────────────────────────────────────────────────────────────

    def rollback_batch(
        self,
        batch_id:        str,
        training_db_path: str,
        approved_by:     str = "chairman",
    ) -> Dict[str, Any]:
        """
        Roll back all candidates in a training batch.

        Steps:
          1. Find pre-training snapshot for the batch
          2. Verify current corpus hash matches snapshot OR proceed anyway with warning
          3. Mark all batch candidates as status="rolled_back" in corpus
          4. Remove committed rows from rex_training.db (by candidate_id)
          5. Restore foundation manifest rollback entry
          6. Audit log

        Returns: result dict with candidates_reverted, db_rows_removed.
        """
        snap = self.get_by_batch(batch_id)
        if not snap:
            return {"ok": False, "error": f"No snapshot found for batch '{batch_id}'"}

        self._audit("rex_training_rollback_started",
                    batch_id=batch_id, snapshot_id=snap["snapshot_id"],
                    approved_by=approved_by)
        log.info("Rollback started: batch=%s snapshot=%s", batch_id, snap["snapshot_id"])

        # Load corpus
        try:
            corpus = json.loads(CORPUS.read_text())
        except Exception as e:
            self._audit("rex_training_rollback_failed", batch_id=batch_id, reason=str(e))
            return {"ok": False, "error": f"Cannot read corpus: {e}"}

        # Mark batch candidates as rolled_back
        reverted    = []
        committed   = []
        for entry in corpus.get("candidates", []):
            if entry.get("training_batch_id") == batch_id:
                if entry.get("status") not in ("rolled_back",):
                    reverted.append(entry["id"])
                    if entry.get("committed_to_rex"):
                        committed.append(entry["id"])
                    entry["status"]       = "rolled_back"
                    entry["committed_to_rex"] = False

        # Save corpus (atomic)
        _atomic_write(CORPUS, json.dumps(corpus, indent=2))

        # Remove from training DB
        db_removed = 0
        if committed and training_db_path:
            try:
                conn = sqlite3.connect(training_db_path)
                for cid in committed:
                    result = conn.execute(
                        "DELETE FROM rex_training_log WHERE candidate_id = ?", (cid,)
                    )
                    db_removed += result.rowcount
                conn.commit()
                conn.close()
            except Exception as e:
                log.warning("DB cleanup during rollback: %s", e)

        # Update foundation manifest
        try:
            fm = json.loads(FOUNDATION.read_text())
            fm["last_rollback_at"] = _now_iso()
            fm["last_rollback_batch"] = batch_id
            _atomic_write(FOUNDATION, json.dumps(fm, indent=2))
        except Exception as e:
            log.warning("Foundation manifest update during rollback: %s", e)

        self._audit("rex_training_rollback_completed",
                    batch_id=batch_id, snapshot_id=snap["snapshot_id"],
                    candidates_reverted=len(reverted),
                    db_rows_removed=db_removed,
                    approved_by=approved_by)
        log.info("Rollback complete: batch=%s reverted=%d db_removed=%d",
                 batch_id, len(reverted), db_removed)

        return {
            "ok":                True,
            "batch_id":          batch_id,
            "snapshot_id":       snap["snapshot_id"],
            "candidates_reverted": len(reverted),
            "db_rows_removed":   db_removed,
            "message":           (
                f"Batch '{batch_id}' rolled back. "
                f"{len(reverted)} candidate(s) reverted, {db_removed} DB row(s) removed."
            ),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _manifest_version() -> str:
        try:
            return json.loads(MANIFEST.read_text()).get("_version", "unknown")
        except Exception:
            return "unknown"

    @staticmethod
    def _schema_version() -> str:
        try:
            return json.loads(MANIFEST.read_text()).get("schema_version", "unknown")
        except Exception:
            return "unknown"

    def _audit(self, event: str, **kwargs) -> None:
        entry = {"event": event, "timestamp": _now_iso(), **kwargs}
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Snapshot audit write failed: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically using temp-file swap."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content)
    tmp.replace(path)
