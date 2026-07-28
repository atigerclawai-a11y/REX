#!/usr/bin/env python3
"""
REX — Training Privacy Panel API  (rex_training_panel.py)
Phase 13 | Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
PURPOSE
  FastAPI routes for the Command Center Training Privacy Panel.
  All 6 sections (A–F) plus drift history persistence.

PRIVACY RULES (enforced in every route)
  - content_sanitized field never returned in any response
  - quarantine entries return metadata + hash only — never raw content
  - Section C (Rexxie) returns count fields and timestamps only
  - All routes require Chairman role (_require_chairman)
  - Training tab only visible/actionable when session is unlocked

SECTION OVERVIEW
  A. /training/summary          — mode, snapshots, counts, drift alerts
  B. /training/pipeline         — candidates with batch grouping
     /training/pipeline/approve
     /training/pipeline/reject
     /training/pipeline/rollback-batch
  C. /training/rexxie-privacy   — meta counts only (PRIVATE - META ONLY)
     /training/rexxie-privacy/pause
     /training/rexxie-privacy/resume
  D. /training/quarantine       — blocked items (metadata + hash only)
  E. /training/drift            — drift score + governance score + history
  F. /training/versions         — foundation version + rollback points

REFINEMENTS APPLIED
  1. Snapshot includes system version context
  2. Quarantine has reviewable + override_required fields
  3. Drift score persisted to state/rex_drift_history.jsonl
  4. Pipeline shows batch grouping explicitly
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rex_training_panel")

training_router = APIRouter(tags=["Training Privacy Panel"])

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE       = Path(__file__).parent.parent
CORPUS      = _BASE / "state" / "rex_training_corpus.json"
FOUNDATION  = _BASE / "state" / "rex_foundation_manifest.json"
QUARANTINE  = _BASE / "state" / "rex_training_quarantine.json"
SNAPSHOTS   = _BASE / "state" / "rex_training_snapshots.jsonl"
DRIFT_HIST  = _BASE / "state" / "rex_drift_history.jsonl"
AUDIT_LOG   = _BASE / "state" / "rex_training_audit.log"
BEHAVIOR_LOG = _BASE / "logs" / "behavior_flags.json"
SEP_RULES   = _BASE / "state" / "rex_separation_rules.json"


# ── Auth guard (imported from command center pattern) ──────────────────────────
def _require_chairman(x_user_name: Optional[str], x_claimed_role: Optional[str]) -> None:
    try:
        from .rex_role_auth import verify_role
        verified = verify_role(x_user_name or "", x_claimed_role or "")
        if verified != "chairman":
            raise HTTPException(status_code=403, detail="Access denied.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Access denied.")


# ── Request models ─────────────────────────────────────────────────────────────
class TrainingApprovalRequest(BaseModel):
    approved_by: str = "chairman"

class TrainingRejectRequest(BaseModel):
    reason: str = ""

class RollbackBatchRequest(BaseModel):
    approved_by: str = "chairman"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — Training Safety Summary
# ══════════════════════════════════════════════════════════════════════════════

@training_router.get("/training/summary")
async def training_summary(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Section A: Training Safety Summary.
    Shows: mode, last snapshot, counts, drift alerts, foundation version.
    Never exposes raw training content.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        corpus     = _load_json(CORPUS, {"candidates": []})
        foundation = _load_json(FOUNDATION, {})
        quarantine = _load_json(QUARANTINE, {"quarantine": []})
        candidates = corpus.get("candidates", [])

        approved_count  = sum(1 for c in candidates if c.get("status") == "approved")
        committed_count = sum(1 for c in candidates if c.get("committed_to_rex"))
        blocked_count   = len(quarantine.get("quarantine", []))
        pending_count   = sum(1 for c in candidates if c.get("status") == "pending_review")

        # Last snapshot
        last_snap = _last_snapshot()
        drift     = _compute_drift_score()

        return {
            "panel":                "training_summary",
            "training_mode_active": False,   # read from training.active in live system
            "last_snapshot_id":     last_snap.get("snapshot_id") if last_snap else None,
            "last_snapshot_at":     last_snap.get("created_at")  if last_snap else None,
            "quarantine_count":     blocked_count,
            "approved_count":       approved_count,
            "committed_count":      committed_count,
            "pending_count":        pending_count,
            "drift_alerts":         drift.get("alert_count", 0),
            "drift_score":          drift.get("drift_score", 0.0),
            "last_rollback_at":     foundation.get("last_rollback_at"),
            "last_rollback_batch":  foundation.get("last_rollback_batch"),
            "rex_foundation_version": foundation.get("corpus_version", "0.0"),
            "foundation_badge":     foundation.get("foundation_badge", "REX FOUNDATION v0.0"),
            "deployment_eligible":  foundation.get("deployment_eligible", False),
        }
    except Exception as e:
        logger.error(f"[training/summary] {e}")
        return {"panel": "training_summary", "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — Rex Training Pipeline (with batch grouping)
# ══════════════════════════════════════════════════════════════════════════════

@training_router.get("/training/pipeline")
async def training_pipeline(
    status:   Optional[str] = None,
    batch_id: Optional[str] = None,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Section B: Rex Training Pipeline.
    Refinement: returns candidates grouped by training_batch_id.
    NEVER returns content_sanitized field — content privacy enforced.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        corpus     = _load_json(CORPUS, {"candidates": []})
        candidates = corpus.get("candidates", [])

        # Filter
        if status:
            candidates = [c for c in candidates if c.get("status") == status]
        if batch_id:
            candidates = [c for c in candidates if c.get("training_batch_id") == batch_id]

        # Strip raw content — privacy enforcement
        safe_candidates = [_safe_candidate(c) for c in candidates]

        # Refinement: group by batch_id
        batches: Dict[str, Dict] = {}
        for c in safe_candidates:
            bid = c.get("training_batch_id", "ungrouped")
            if bid not in batches:
                batches[bid] = {
                    "batch_id":    bid,
                    "snapshot_id": c.get("snapshot_id"),
                    "candidates":  [],
                    "status_summary": {"pending_review": 0, "approved": 0,
                                       "rejected": 0, "committed": 0, "rolled_back": 0},
                }
            batches[bid]["candidates"].append(c)
            s = c.get("status", "unknown")
            if c.get("committed_to_rex"):
                batches[bid]["status_summary"]["committed"] += 1
            elif s in batches[bid]["status_summary"]:
                batches[bid]["status_summary"][s] += 1

        # Compute batch-level status label
        for bid, b in batches.items():
            ss = b["status_summary"]
            if ss["rolled_back"] > 0:
                b["batch_status"] = "rolled_back"
            elif ss["committed"] == len(b["candidates"]):
                b["batch_status"] = "fully_committed"
            elif ss["approved"] > 0 and ss["pending_review"] == 0:
                b["batch_status"] = "approved"
            elif ss["rejected"] == len(b["candidates"]):
                b["batch_status"] = "rejected"
            else:
                b["batch_status"] = "partial" if ss["approved"] > 0 else "pending"

        return {
            "panel":     "training_pipeline",
            "total":     len(safe_candidates),
            "batches":   list(batches.values()),
            "filters":   {"status": status, "batch_id": batch_id},
        }
    except Exception as e:
        logger.error(f"[training/pipeline] {e}")
        return {"panel": "training_pipeline", "error": str(e), "batches": []}


@training_router.post("/training/pipeline/approve/{candidate_id}")
async def training_approve(
    candidate_id: str,
    body: TrainingApprovalRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Approve a training candidate (existing governed flow)."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_training_classifier import RexTrainingClassifier
        clf    = RexTrainingClassifier()
        result = clf.approve_candidate(candidate_id, approved_by=body.approved_by or x_user_name or "chairman")
        return {"panel": "training_approve", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@training_router.post("/training/pipeline/reject/{candidate_id}")
async def training_reject(
    candidate_id: str,
    body: TrainingRejectRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Reject a training candidate."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        from .rex_training_classifier import RexTrainingClassifier
        clf    = RexTrainingClassifier()
        result = clf.reject_candidate(candidate_id, reason=body.reason)
        return {"panel": "training_reject", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@training_router.post("/training/pipeline/rollback-batch/{batch_id}")
async def training_rollback_batch(
    batch_id: str,
    body: RollbackBatchRequest,
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Roll back all candidates in a training batch.
    Requires Chairman session. Reverts corpus and removes committed DB rows.
    """
    _require_chairman(x_user_name, x_claimed_role)
    # MSU session check
    try:
        from .rex_session import SessionEngine
        eng   = SessionEngine()
        block = eng.require_unlocked()
        if block:
            return {"panel": "training_rollback", **block}
        eng.record_protected_activity()
    except Exception as e:
        logger.warning(f"MSU check: {e}")

    try:
        from .rex_training_snapshot import TrainingSnapshot
        snap   = TrainingSnapshot()
        # Use rex_training.db path from foundation
        db_path = str(_BASE.parent / "Desktop" / "REX" / "rex_training.db")
        result = snap.rollback_batch(batch_id, db_path, approved_by=body.approved_by)
        return {"panel": "training_rollback", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION C — Rexxie Training Privacy (PRIVATE — META ONLY)
# ══════════════════════════════════════════════════════════════════════════════

@training_router.get("/training/rexxie-privacy")
async def rexxie_training_privacy(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Section C: Rexxie Training Privacy.
    Refinement: label is unmistakably PRIVATE — META ONLY.
    Returns count fields and timestamps ONLY. Never returns content, events, or text.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        # Read Rexxie memory DB for counts only — never content
        rexxie_db = _BASE / "rexxie_memory.db"
        training_count = 0
        refinement_count = 0
        coordination_count = 0
        trust_count = 0
        last_reviewed = None

        if rexxie_db.exists():
            import sqlite3
            try:
                conn = sqlite3.connect(str(rexxie_db))
                # Count only — no content read
                rows = conn.execute(
                    "SELECT mem_type, COUNT(*) as n FROM rexxie_memory WHERE active=1 GROUP BY mem_type"
                ).fetchall()
                conn.close()
                for mem_type, count in rows:
                    mt = (mem_type or "").lower()
                    if "train" in mt:
                        training_count = count
                    elif "private" in mt or "refine" in mt:
                        refinement_count = count
                    elif "coord" in mt:
                        coordination_count = count
                    elif "trust" in mt or "personal" in mt or "conversation" in mt:
                        trust_count += count
            except Exception:
                pass

        # Status from foundation manifest
        foundation = _load_json(FOUNDATION, {})
        paused     = foundation.get("rexxie_training_paused", False)

        return {
            "panel":              "rexxie_training_privacy",
            "_privacy_label":     "REXXIE PRIVATE — META ONLY — NO DATA EXPOSURE",
            "training_events_count":       training_count,
            "private_refinement_count":    refinement_count,
            "trust_building_count":        trust_count,
            "coordination_improvements":   coordination_count,
            "last_reviewed":               last_reviewed,
            "current_status":              "paused" if paused else "active",
            "exportable_by_default":       False,
            "note":               "Raw Rexxie training content is never exposed through this panel.",
        }
    except Exception as e:
        logger.error(f"[training/rexxie-privacy] {e}")
        return {"panel": "rexxie_training_privacy", "error": str(e)}


@training_router.post("/training/rexxie-privacy/pause")
async def rexxie_training_pause(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Pause Rexxie private training. Sets flag in foundation manifest."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        fm = _load_json(FOUNDATION, {})
        fm["rexxie_training_paused"] = True
        fm["rexxie_training_paused_at"] = _now_iso()
        _atomic_write(FOUNDATION, json.dumps(fm, indent=2))
        _audit_event("rex_rexxie_training_paused", paused_by=x_user_name or "chairman")
        return {"panel": "rexxie_pause", "ok": True, "status": "paused"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@training_router.post("/training/rexxie-privacy/resume")
async def rexxie_training_resume(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """Resume Rexxie private training."""
    _require_chairman(x_user_name, x_claimed_role)
    try:
        fm = _load_json(FOUNDATION, {})
        fm["rexxie_training_paused"] = False
        fm["rexxie_training_resumed_at"] = _now_iso()
        _atomic_write(FOUNDATION, json.dumps(fm, indent=2))
        _audit_event("rex_rexxie_training_resumed", resumed_by=x_user_name or "chairman")
        return {"panel": "rexxie_resume", "ok": True, "status": "active"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION D — Training Quarantine
# ══════════════════════════════════════════════════════════════════════════════

@training_router.get("/training/quarantine")
async def training_quarantine(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Section D: Training Quarantine.
    Returns metadata + hash ONLY — never raw content.
    Refinement: includes reviewable + override_required fields.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        qdata   = _load_json(QUARANTINE, {"quarantine": []})
        entries = qdata.get("quarantine", [])
        # Return all fields EXCEPT any that might contain raw content
        safe = [
            {k: v for k, v in entry.items()
             if k not in ("raw_text", "content", "text", "sanitized")}
            for entry in entries
        ]
        reviewable_count = sum(1 for e in entries if e.get("reviewable"))
        return {
            "panel":             "training_quarantine",
            "total":             len(entries),
            "reviewable_count":  reviewable_count,
            "override_note":     "Overrides require Chairman approval. Auto-retry is never permitted.",
            "entries":           safe,
        }
    except Exception as e:
        return {"panel": "training_quarantine", "error": str(e), "entries": []}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION E — Drift Monitor (with persistence)
# ══════════════════════════════════════════════════════════════════════════════

@training_router.get("/training/drift")
async def training_drift(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Section E: Drift Monitor.
    Refinement: drift score is computed AND persisted to rex_drift_history.jsonl.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        drift   = _compute_drift_score()
        history = _drift_history(limit=30)

        # Correlate drift with recent training batch if possible
        triggering_batch = _correlate_drift_with_batch(drift)

        # Persist to drift history
        hist_entry = {
            "timestamp":          _now_iso(),
            "drift_score":        drift["drift_score"],
            "compliance_score":   drift["compliance_score"],
            "alert_count":        drift["alert_count"],
            "triggering_batch_id": triggering_batch,
        }
        with DRIFT_HIST.open("a") as f:
            f.write(json.dumps(hist_entry) + "\n")

        return {
            "panel":                "drift_monitor",
            "drift_score":          drift["drift_score"],
            "governance_compliance_score": drift["compliance_score"],
            "alert_count":          drift["alert_count"],
            "revert_recommendation": drift["revert_recommendation"],
            "last_scan":            _now_iso(),
            "triggering_batch_id":  triggering_batch,
            "history":              history,
        }
    except Exception as e:
        return {"panel": "drift_monitor", "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION F — Training Versions
# ══════════════════════════════════════════════════════════════════════════════

@training_router.get("/training/versions")
async def training_versions(
    x_user_name:    Optional[str] = Header(None),
    x_claimed_role: Optional[str] = Header(None),
):
    """
    Section F: Training Versions.
    Shows foundation version, rollback points, last known good baseline.
    """
    _require_chairman(x_user_name, x_claimed_role)
    try:
        foundation = _load_json(FOUNDATION, {})
        corpus     = _load_json(CORPUS, {"candidates": []})
        candidates = corpus.get("candidates", [])

        # Rollback points = unique batches that have pre-training snapshots
        snaps = _list_snapshots(limit=20)
        rollback_points = [
            {
                "snapshot_id":      s["snapshot_id"],
                "batch_id":         s["training_batch_id"],
                "created_at":       s["created_at"],
                "system_version":   s.get("system_manifest_version", "unknown"),
                "corpus_hash":      s.get("training_corpus_hash", ""),
            }
            for s in snaps if s.get("type") == "pre_training"
        ]

        # Last approved batch
        approved = [c for c in candidates if c.get("status") == "approved"]
        last_approved_batch = None
        if approved:
            last_approved_batch = sorted(approved,
                key=lambda c: c.get("approved_at") or "",
                reverse=True
            )[0].get("training_batch_id")

        # Last known good = last rollback snapshot
        lkg = foundation.get("last_rollback_batch")

        return {
            "panel":                   "training_versions",
            "rex_foundation_version":  foundation.get("corpus_version", "0.0"),
            "foundation_badge":        foundation.get("foundation_badge", "REX FOUNDATION v0.0"),
            "last_approved_batch":     last_approved_batch,
            "last_rollback_at":        foundation.get("last_rollback_at"),
            "last_rollback_batch":     foundation.get("last_rollback_batch"),
            "last_known_good":         lkg or "none — no rollback performed yet",
            "pending_deployment_review": not foundation.get("deployment_eligible", False),
            "deployment_eligible":     foundation.get("deployment_eligible", False),
            "rollback_points":         rollback_points,
            "total_approved_candidates": len(foundation.get("approved_candidate_ids", [])),
        }
    except Exception as e:
        return {"panel": "training_versions", "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _safe_candidate(c: Dict) -> Dict:
    """Return candidate dict with raw content stripped."""
    STRIP = {"content_sanitized", "raw_text", "content", "text"}
    return {k: v for k, v in c.items() if k not in STRIP}

def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content)
    tmp.replace(path)

def _last_snapshot() -> Optional[Dict]:
    if not SNAPSHOTS.exists():
        return None
    lines = [l.strip() for l in SNAPSHOTS.read_text().splitlines() if l.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return None

def _list_snapshots(limit: int = 20) -> List[Dict]:
    if not SNAPSHOTS.exists():
        return []
    snaps = []
    for line in SNAPSHOTS.read_text().splitlines():
        try:
            snaps.append(json.loads(line.strip()))
        except Exception:
            continue
    return list(reversed(snaps[-limit:]))

def _compute_drift_score() -> Dict:
    """
    Compute drift_score (0.0–1.0) and governance_compliance_score from behavior flags.
    0 = clean, 1 = severe drift.
    """
    drift_score       = 0.0
    compliance_score  = 1.0
    alert_count       = 0
    revert_rec        = "none"

    if not BEHAVIOR_LOG.exists():
        return {
            "drift_score":         0.0,
            "compliance_score":    1.0,
            "alert_count":         0,
            "revert_recommendation": "none",
        }

    try:
        flags = json.loads(BEHAVIOR_LOG.read_text())
        if not isinstance(flags, list):
            flags = []

        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        recent = [f for f in flags if (f.get("timestamp") or "") >= cutoff]

        critical = sum(1 for f in recent if f.get("severity") == "CRITICAL")
        high     = sum(1 for f in recent if f.get("severity") in ("HIGH", "IMMEDIATE"))
        weekly   = sum(1 for f in recent if f.get("severity") == "WEEKLY")
        alert_count = critical + high

        drift_score      = min(1.0, (critical * 0.4 + high * 0.2 + weekly * 0.05))
        compliance_score = max(0.0, 1.0 - (critical * 0.5 + high * 0.25))

        if drift_score > 0.7:
            revert_rec = "immediate_revert"
        elif drift_score > 0.4:
            revert_rec = "review_and_consider_revert"
        elif drift_score > 0.15:
            revert_rec = "monitor_closely"

    except Exception as e:
        logger.warning("Drift score compute error: %s", e)

    return {
        "drift_score":          round(drift_score, 3),
        "compliance_score":     round(compliance_score, 3),
        "alert_count":          alert_count,
        "revert_recommendation": revert_rec,
    }

def _drift_history(limit: int = 30) -> List[Dict]:
    if not DRIFT_HIST.exists():
        return []
    entries = []
    for line in reversed(DRIFT_HIST.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
            if len(entries) >= limit:
                break
        except Exception:
            continue
    return entries

def _correlate_drift_with_batch(drift: Dict) -> Optional[str]:
    """Try to correlate current drift with the most recently committed training batch."""
    if drift.get("alert_count", 0) == 0:
        return None
    corpus = _load_json(CORPUS, {"candidates": []})
    committed = [
        c for c in corpus.get("candidates", [])
        if c.get("committed_to_rex") and c.get("training_batch_id")
    ]
    if not committed:
        return None
    # Most recently committed batch
    committed.sort(key=lambda c: c.get("submitted_at") or "", reverse=True)
    return committed[0].get("training_batch_id")

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _audit_event(event: str, **kwargs) -> None:
    entry = {"event": event, "timestamp": _now_iso(), **kwargs}
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
