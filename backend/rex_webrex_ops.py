"""
backend/rex_webrex_ops.py
============================
Phase 17 — WebRex Web Operations Pipeline
Gold Health Systems · Packet B

PURPOSE:
    Manages the 6-stage web operations pipeline:
    MONITOR → AUDIT → DRAFT → STAGE → APPROVE → PUBLISH

    HARD RULE: Nothing publishes without Chairman MSU approval.
    WebRex suggests and stages only — never auto-publishes.

ACTIVATION STATUS: READY — pending import in backend/main.py

Gold Health Systems · Phase 17 · June 4, 2026
"""

import json
import logging
import datetime
import sqlite3
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

OPS_STATE   = Path.home() / "Desktop" / "REX" / "state" / "webrex_operations.json"
OPS_AUDIT   = Path.home() / "Desktop" / "REX" / "data" / "webrex_ops_audit.db"

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE STAGES
# ─────────────────────────────────────────────────────────────────────────────

class PipelineStage(str, Enum):
    MONITOR = "MONITOR"
    AUDIT   = "AUDIT"
    DRAFT   = "DRAFT"
    STAGE   = "STAGE"
    APPROVE = "APPROVE"   # Requires Chairman MSU
    PUBLISH = "PUBLISH"   # Requires Chairman MSU + explicit confirmation


MSU_REQUIRED_STAGES = {PipelineStage.APPROVE, PipelineStage.PUBLISH}


class WebOpAuthError(PermissionError):
    """MSU or Chairman authorization required."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT
# ─────────────────────────────────────────────────────────────────────────────

def _init_ops_audit() -> None:
    OPS_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(OPS_AUDIT) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS web_ops_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                operation_id    TEXT,
                site_id         TEXT,
                stage           TEXT NOT NULL,
                action          TEXT NOT NULL,
                authorized_by   TEXT,
                session_id      TEXT,
                result          TEXT NOT NULL,
                notes           TEXT
            )
        """)
        conn.commit()


def _log_ops(site_id: str, stage: str, action: str, result: str,
              operation_id: Optional[str] = None, session_id: Optional[str] = None,
              authorized_by: Optional[str] = None, notes: str = "") -> None:
    try:
        _init_ops_audit()
        with sqlite3.connect(OPS_AUDIT) as conn:
            conn.execute(
                """INSERT INTO web_ops_events
                   (timestamp, operation_id, site_id, stage, action, authorized_by,
                    session_id, result, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (datetime.datetime.utcnow().isoformat(), operation_id, site_id,
                 stage, action, authorized_by, session_id, result, notes)
            )
            conn.commit()
    except Exception as exc:
        logger.error("WebOps audit write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# WEB OPERATIONS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class WebrexOps:
    """
    Phase 17 Web Operations Pipeline.
    Manages change proposals through 6 stages, with hard MSU gate at APPROVE/PUBLISH.
    """

    def __init__(self):
        self._state: dict = {}
        self._msu_sessions: set = set()
        self._load()

    def _load(self) -> None:
        if OPS_STATE.exists():
            with open(OPS_STATE) as f:
                self._state = json.load(f)
        else:
            self._state = {"sites": [], "pipeline_queue": [], "publish_lock": True}

    def _save(self) -> None:
        self._state["_updated"] = datetime.datetime.utcnow().isoformat()
        with open(OPS_STATE, "w") as f:
            json.dump(self._state, f, indent=2)

    def grant_msu(self, session_id: str) -> None:
        self._msu_sessions.add(session_id)

    def revoke_msu(self, session_id: str) -> None:
        self._msu_sessions.discard(session_id)

    def _require_msu(self, stage: PipelineStage, session_id: Optional[str]) -> None:
        if stage in MSU_REQUIRED_STAGES:
            if not session_id or session_id not in self._msu_sessions:
                raise WebOpAuthError(
                    f"Stage '{stage}' requires Chairman MSU authorization. "
                    "Unlock MSU with CHAIRMAN code first."
                )

    # ── Site status ──────────────────────────────────────────────────────────

    def get_site(self, site_id: str) -> Optional[dict]:
        for site in self._state.get("sites", []):
            if site["id"] == site_id:
                return site
        return None

    def list_sites(self) -> List[dict]:
        return self._state.get("sites", [])

    def update_site_status(self, site_id: str, status: str, note: str = "",
                             session_id: Optional[str] = None) -> dict:
        site = self.get_site(site_id)
        if not site:
            return {"ok": False, "error": f"Site not found: {site_id}"}
        site["status"] = status
        if note:
            site["status_note"] = note
        site["last_verified"] = datetime.datetime.utcnow().isoformat()
        self._save()
        _log_ops(site_id, "MONITOR", "UPDATE_STATUS", "SUCCESS",
                  session_id=session_id, notes=f"{status}: {note}")
        return {"ok": True, "site_id": site_id, "status": status}

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def propose_change(self, site_id: str, description: str, diff: str = "",
                        proposed_by: str = "webrex") -> dict:
        """
        DRAFT stage: WebRex proposes a change.
        Creates a change record and adds to pipeline queue.
        """
        import uuid
        op_id = f"webop_{datetime.date.today().isoformat()}_{uuid.uuid4().hex[:8]}"

        change = {
            "id": op_id,
            "site_id": site_id,
            "stage": PipelineStage.DRAFT.value,
            "description": description,
            "diff": diff,
            "proposed_by": proposed_by,
            "proposed_at": datetime.datetime.utcnow().isoformat(),
            "approved_by": None,
            "approved_at": None,
            "published_at": None,
            "history": [
                {"stage": "DRAFT", "at": datetime.datetime.utcnow().isoformat(),
                 "by": proposed_by}
            ]
        }

        queue = self._state.setdefault("pipeline_queue", [])
        queue.append(change)
        self._save()

        _log_ops(site_id, "DRAFT", "PROPOSE", "SUCCESS", operation_id=op_id,
                  notes=description)
        return {"ok": True, "operation_id": op_id, "stage": "DRAFT"}

    def advance_to_stage(self, operation_id: str, target_stage: PipelineStage,
                          session_id: Optional[str] = None) -> dict:
        """
        Advance a change through the pipeline.
        APPROVE and PUBLISH require Chairman MSU.
        """
        self._require_msu(target_stage, session_id)

        queue = self._state.get("pipeline_queue", [])
        change = next((c for c in queue if c["id"] == operation_id), None)
        if not change:
            return {"ok": False, "error": f"Operation not found: {operation_id}"}

        # Validate stage progression order
        stage_order = [s.value for s in PipelineStage]
        current_idx = stage_order.index(change["stage"])
        target_idx  = stage_order.index(target_stage.value)
        if target_idx != current_idx + 1:
            return {"ok": False, "error": f"Cannot skip stages: {change['stage']} → {target_stage}"}

        change["stage"] = target_stage.value
        history_entry = {
            "stage": target_stage.value,
            "at": datetime.datetime.utcnow().isoformat(),
            "by": session_id or "system",
        }
        change.setdefault("history", []).append(history_entry)

        if target_stage == PipelineStage.APPROVE:
            change["approved_by"] = session_id
            change["approved_at"] = datetime.datetime.utcnow().isoformat()

        if target_stage == PipelineStage.PUBLISH:
            change["published_at"] = datetime.datetime.utcnow().isoformat()
            logger.info("WebRex PUBLISH: %s on %s (authorized by %s)",
                        operation_id, change["site_id"], session_id)

        self._save()
        _log_ops(change["site_id"], target_stage.value, "ADVANCE", "SUCCESS",
                  operation_id=operation_id, session_id=session_id,
                  authorized_by="CHAIRMAN_MSU" if target_stage in MSU_REQUIRED_STAGES else None)

        return {"ok": True, "operation_id": operation_id, "stage": target_stage.value}

    def get_pipeline_queue(self, site_id: Optional[str] = None) -> List[dict]:
        queue = self._state.get("pipeline_queue", [])
        if site_id:
            queue = [c for c in queue if c.get("site_id") == site_id]
        return queue

    # ── Status summary ───────────────────────────────────────────────────────

    def ops_summary(self) -> dict:
        queue = self._state.get("pipeline_queue", [])
        by_stage: Dict[str, int] = {}
        for item in queue:
            s = item.get("stage", "UNKNOWN")
            by_stage[s] = by_stage.get(s, 0) + 1
        return {
            "sites": len(self.list_sites()),
            "pipeline_items": len(queue),
            "by_stage": by_stage,
            "publish_lock": self._state.get("publish_lock", True),
            "msu_sessions_active": len(self._msu_sessions),
        }
