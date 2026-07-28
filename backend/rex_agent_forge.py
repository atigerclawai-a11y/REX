"""
backend/rex_agent_forge.py
============================
Phase 15 — Agent Forge Engine
Gold Health Systems · Packet B

PURPOSE:
    Create, clone, retarget, assign permissions, pause, archive, and terminate
    agents in the GHS multi-agent system. All operations are MSU-gated per
    Phase 15 spec. Every operation is logged and reported to Chairman.

ACTIVATION STATUS: READY — pending import in backend/main.py
    Add to main.py:
        from backend.rex_agent_forge import AgentForge
        agent_forge = AgentForge()

    Add REST endpoint:
        @app.post("/api/forge/{operation}")  (MSU-gated)

HARD LIMITS (from CLAUDE.md / Phase 15 spec):
    - TERMINATE is IRREVERSIBLE — data is sealed after execution
    - No agent can grant itself permissions
    - No agent can bypass MSU
    - Luna is LAST to activate — only when all others are stable

Gold Health Systems · Phase 15 · June 4, 2026
"""

import json
import sqlite3
import logging
import datetime
import shutil
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

FORGE_REGISTRY = Path.home() / "Desktop" / "REX" / "state" / "agent_forge_registry.json"
AGENT_REGISTRY = Path.home() / "Desktop" / "REX" / "agent_registry.json"
FORGE_AUDIT_DB = Path.home() / "Desktop" / "REX" / "data" / "forge_audit.db"

# ─────────────────────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────

class ForgeAuthError(PermissionError):
    """Operation requires MSU authorization."""
    pass

class ForgeAgentNotFound(KeyError):
    """Agent ID not found in forge registry."""
    pass

class ForgeTerminateError(RuntimeError):
    """Raised on terminate if pre-conditions not met."""
    pass

# ─────────────────────────────────────────────────────────────────────────────
# AUDIT DB
# ─────────────────────────────────────────────────────────────────────────────

def _init_forge_audit() -> None:
    FORGE_AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(FORGE_AUDIT_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forge_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                operation       TEXT NOT NULL,
                agent_id        TEXT NOT NULL,
                authorized_by   TEXT,
                session_id      TEXT,
                payload         TEXT,
                result          TEXT NOT NULL,   -- SUCCESS / BLOCKED / ERROR
                notes           TEXT
            )
        """)
        conn.commit()

def _log_forge(operation: str, agent_id: str, result: str,
                authorized_by: Optional[str] = None,
                session_id: Optional[str] = None,
                payload: Optional[dict] = None,
                notes: str = "") -> None:
    try:
        _init_forge_audit()
        with sqlite3.connect(FORGE_AUDIT_DB) as conn:
            conn.execute(
                """INSERT INTO forge_events
                   (timestamp, operation, agent_id, authorized_by, session_id, payload, result, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (datetime.datetime.utcnow().isoformat(), operation, agent_id,
                 authorized_by, session_id, json.dumps(payload or {}), result, notes)
            )
            conn.commit()
    except Exception as exc:
        logger.error("Forge audit write failed: %s", exc)

# ─────────────────────────────────────────────────────────────────────────────
# FORGE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class AgentForge:
    """
    Phase 15 Agent Forge — create, manage, and govern GHS agents.
    All MSU-gated operations require a valid session_id that has been
    unlocked via the MSU flow (CHAIRMAN code in rex_security_audit.py).
    """

    # Operations that require MSU
    _MSU_REQUIRED = {"CREATE", "CLONE", "ASSIGN", "ARCHIVE", "TERMINATE"}

    def __init__(self):
        self._registry: dict = {}
        self._msu_sessions: set = set()
        self._load_registry()

    def _load_registry(self) -> None:
        if FORGE_REGISTRY.exists():
            with open(FORGE_REGISTRY) as f:
                self._registry = json.load(f)
        else:
            logger.warning("AgentForge: registry not found at %s", FORGE_REGISTRY)
            self._registry = {"agents": [], "forge_operations": {}}

    def _save_registry(self) -> None:
        self._registry["_updated"] = datetime.datetime.utcnow().isoformat()
        with open(FORGE_REGISTRY, "w") as f:
            json.dump(self._registry, f, indent=2)

    def _get_agent(self, agent_id: str) -> dict:
        for agent in self._registry.get("agents", []):
            if agent["id"] == agent_id:
                return agent
        raise ForgeAgentNotFound(f"Agent not found: {agent_id}")

    # ── MSU authorization ────────────────────────────────────────────────────

    def grant_msu(self, session_id: str) -> None:
        """Called by MSU unlock handler after CHAIRMAN code verified."""
        self._msu_sessions.add(session_id)
        logger.info("AgentForge: MSU granted for session %s", session_id)

    def revoke_msu(self, session_id: str) -> None:
        self._msu_sessions.discard(session_id)

    def _require_msu(self, operation: str, session_id: Optional[str]) -> None:
        if operation in self._MSU_REQUIRED:
            if not session_id or session_id not in self._msu_sessions:
                _log_forge(operation, "N/A", "BLOCKED", notes="MSU required")
                raise ForgeAuthError(
                    f"Operation '{operation}' requires Chairman MSU authorization. "
                    f"Unlock MSU with CHAIRMAN code first."
                )

    # ── LIST / STATUS ────────────────────────────────────────────────────────

    def list_agents(self, status_filter: Optional[str] = None) -> List[dict]:
        agents = self._registry.get("agents", [])
        if status_filter:
            agents = [a for a in agents if a.get("forge_status") == status_filter]
        return agents

    def get_agent_status(self, agent_id: str) -> dict:
        agent = self._get_agent(agent_id)
        return {
            "id": agent["id"],
            "name": agent["name"],
            "forge_status": agent.get("forge_status", "UNKNOWN"),
            "context": agent.get("context"),
            "health_status": agent.get("health_status"),
            "health_note": agent.get("health_note"),
        }

    # ── PAUSE (no MSU needed — Clause or Chairman) ───────────────────────────

    def pause(self, agent_id: str, reason: str = "", session_id: Optional[str] = None) -> dict:
        """
        PAUSE: Suspend agent. Reversible. Clause or Chairman can execute.
        """
        agent = self._get_agent(agent_id)
        prev_status = agent.get("forge_status")

        agent["forge_status"] = "PAUSED"
        agent["pause_reason"] = reason
        agent["paused_at"] = datetime.datetime.utcnow().isoformat()
        agent["paused_by"] = session_id or "system"

        self._save_registry()
        _log_forge("PAUSE", agent_id, "SUCCESS", session_id=session_id,
                    payload={"reason": reason, "prev_status": prev_status})

        logger.info("AgentForge PAUSE: %s (was %s) — %s", agent_id, prev_status, reason)
        return {"ok": True, "agent_id": agent_id, "status": "PAUSED"}

    def unpause(self, agent_id: str, session_id: Optional[str] = None) -> dict:
        """Resume a paused agent."""
        agent = self._get_agent(agent_id)
        agent["forge_status"] = "ACTIVE"
        agent.pop("pause_reason", None)
        agent.pop("paused_at", None)
        agent.pop("paused_by", None)
        self._save_registry()
        _log_forge("UNPAUSE", agent_id, "SUCCESS", session_id=session_id)
        return {"ok": True, "agent_id": agent_id, "status": "ACTIVE"}

    # ── RETARGET (no MSU — change model/endpoint) ────────────────────────────

    def retarget(self, agent_id: str, new_model: str,
                  session_id: Optional[str] = None) -> dict:
        """
        RETARGET: Change an agent's model or endpoint. No MSU required.
        """
        agent = self._get_agent(agent_id)
        old_model = agent.get("model", "unknown")
        agent["model"] = new_model
        agent["retargeted_at"] = datetime.datetime.utcnow().isoformat()
        self._save_registry()
        _log_forge("RETARGET", agent_id, "SUCCESS", session_id=session_id,
                    payload={"old_model": old_model, "new_model": new_model})
        logger.info("AgentForge RETARGET: %s → %s", agent_id, new_model)
        return {"ok": True, "agent_id": agent_id, "old_model": old_model, "new_model": new_model}

    # ── CREATE (MSU required) ────────────────────────────────────────────────

    def create(self, agent_def: dict, session_id: Optional[str] = None) -> dict:
        """
        CREATE: Spawn a new agent from a definition dict.
        Requires MSU. agent_def must have: id, name, category, context.
        """
        self._require_msu("CREATE", session_id)

        agent_id = agent_def.get("id")
        if not agent_id:
            raise ValueError("agent_def must include 'id'")

        # Check for duplicate
        try:
            self._get_agent(agent_id)
            raise ValueError(f"Agent {agent_id} already exists")
        except ForgeAgentNotFound:
            pass

        # Enforce hard limits — no agent gets these permissions at create time
        forbidden_perms = {"master_key_access", "msu_bypass", "self_permission_grant",
                           "training_commit_execute", "live_publish_unrestricted"}
        requested_perms = set(agent_def.get("permissions", []))
        if requested_perms & forbidden_perms:
            raise ForgeAuthError(
                f"Cannot create agent with forbidden permissions: "
                f"{requested_perms & forbidden_perms}"
            )

        agent_def["forge_status"] = "ACTIVE"
        agent_def["created"] = datetime.datetime.utcnow().isoformat()
        agent_def["created_by"] = session_id or "system"
        agent_def["lineage"] = "forged"

        self._registry["agents"].append(agent_def)
        self._registry["total_agents"] = len(self._registry["agents"])
        self._save_registry()

        _log_forge("CREATE", agent_id, "SUCCESS", session_id=session_id,
                    authorized_by="CHAIRMAN_MSU", payload=agent_def)
        logger.info("AgentForge CREATE: %s", agent_id)
        return {"ok": True, "agent_id": agent_id, "status": "ACTIVE"}

    # ── CLONE (MSU required) ─────────────────────────────────────────────────

    def clone(self, source_id: str, new_id: str, overrides: Optional[dict] = None,
               session_id: Optional[str] = None) -> dict:
        """
        CLONE: Fork an existing agent with optional overrides.
        """
        self._require_msu("CLONE", session_id)
        source = self._get_agent(source_id)
        import copy
        new_agent = copy.deepcopy(source)
        new_agent["id"] = new_id
        new_agent["lineage"] = f"clone:{source_id}"
        new_agent["forge_status"] = "ACTIVE"
        new_agent["created"] = datetime.datetime.utcnow().isoformat()
        if overrides:
            new_agent.update(overrides)

        self._registry["agents"].append(new_agent)
        self._save_registry()
        _log_forge("CLONE", new_id, "SUCCESS", session_id=session_id,
                    authorized_by="CHAIRMAN_MSU",
                    payload={"source": source_id, "overrides": overrides})
        return {"ok": True, "source_id": source_id, "new_id": new_id}

    # ── ASSIGN permissions (MSU required) ────────────────────────────────────

    def assign_permissions(self, agent_id: str, add_permissions: List[str],
                             session_id: Optional[str] = None) -> dict:
        """Add permissions to an agent. MSU required."""
        self._require_msu("ASSIGN", session_id)

        forbidden_perms = {"master_key_access", "msu_bypass", "self_permission_grant"}
        if set(add_permissions) & forbidden_perms:
            raise ForgeAuthError(f"Cannot assign forbidden permissions: {set(add_permissions) & forbidden_perms}")

        agent = self._get_agent(agent_id)
        existing = set(agent.get("permissions", []))
        existing.update(add_permissions)
        agent["permissions"] = sorted(existing)
        self._save_registry()

        _log_forge("ASSIGN", agent_id, "SUCCESS", session_id=session_id,
                    authorized_by="CHAIRMAN_MSU",
                    payload={"added": add_permissions})
        return {"ok": True, "agent_id": agent_id, "permissions": agent["permissions"]}

    # ── ARCHIVE (MSU required, reversible) ───────────────────────────────────

    def archive(self, agent_id: str, reason: str = "",
                 session_id: Optional[str] = None) -> dict:
        """
        ARCHIVE: Seal and archive an agent. MSU required. Reversible (unlike TERMINATE).
        """
        self._require_msu("ARCHIVE", session_id)
        agent = self._get_agent(agent_id)
        agent["forge_status"] = "ARCHIVED"
        agent["archived_at"] = datetime.datetime.utcnow().isoformat()
        agent["archive_reason"] = reason
        self._save_registry()
        _log_forge("ARCHIVE", agent_id, "SUCCESS", session_id=session_id,
                    authorized_by="CHAIRMAN_MSU", payload={"reason": reason})
        return {"ok": True, "agent_id": agent_id, "status": "ARCHIVED"}

    # ── TERMINATE (MSU required, IRREVERSIBLE) ───────────────────────────────

    def terminate(self, agent_id: str, confirm_irreversible: bool = False,
                   reason: str = "", session_id: Optional[str] = None) -> dict:
        """
        TERMINATE: Permanent. Data is sealed. CANNOT be undone.
        Requires MSU + explicit confirm_irreversible=True.
        """
        self._require_msu("TERMINATE", session_id)

        if not confirm_irreversible:
            raise ForgeTerminateError(
                "TERMINATE is irreversible. Pass confirm_irreversible=True to proceed. "
                "This action permanently seals the agent and cannot be undone."
            )

        agent = self._get_agent(agent_id)

        # Write final audit record before any changes
        _log_forge("TERMINATE", agent_id, "SUCCESS", session_id=session_id,
                    authorized_by="CHAIRMAN_MSU",
                    payload={"reason": reason, "final_state": dict(agent)},
                    notes="PERMANENT — data sealed")

        agent["forge_status"] = "TERMINATED"
        agent["terminated_at"] = datetime.datetime.utcnow().isoformat()
        agent["terminate_reason"] = reason
        # Clear sensitive fields
        for field in ["venv", "env", "db", "log"]:
            agent.pop(field, None)

        self._save_registry()
        logger.warning("AgentForge TERMINATE (PERMANENT): %s — %s", agent_id, reason)
        return {"ok": True, "agent_id": agent_id, "status": "TERMINATED", "permanent": True}

    # ── Summary ──────────────────────────────────────────────────────────────

    def forge_summary(self) -> dict:
        agents = self._registry.get("agents", [])
        by_status: Dict[str, int] = {}
        for a in agents:
            s = a.get("forge_status", "UNKNOWN")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": len(agents),
            "by_status": by_status,
            "msu_sessions_active": len(self._msu_sessions),
        }
