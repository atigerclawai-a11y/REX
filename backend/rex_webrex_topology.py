"""
backend/rex_webrex_topology.py
================================
Phase 17 — WebRex Topology Manager
Gold Health Systems · Packet B

PURPOSE:
    Manages the GHS infrastructure topology map.
    Reads/writes state/webrex_topology.json.
    Provides live health checks for topology nodes.
    Serves data to the dashboard View A (SVG topology/lineage map).

ACTIVATION STATUS: READY — pending import in backend/main.py
    from backend.rex_webrex_topology import WebrexTopology
    topology = WebrexTopology()

    @app.get("/api/webrex/topology")
    async def get_topology():
        return topology.get_live_topology()

Gold Health Systems · Phase 17 · June 4, 2026
"""

import json
import asyncio
import aiohttp
import logging
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TOPOLOGY_STATE = Path.home() / "Desktop" / "REX" / "state" / "webrex_topology.json"

# Service endpoints to health-check
HEALTH_ENDPOINTS = {
    "hermes_gateway":  "http://localhost:3002/health",
    "rex_api":         "http://localhost:8000/api/health",
    "goj_dashboard":   "http://localhost:8080/health",
    "tigerclaw_api":   "http://localhost:27226/health",
    "ollama":          "http://localhost:11434/api/tags",
    "hermes_local":    "http://localhost:65001/v1/models",
}

EXTERNAL_ENDPOINTS = {
    "hermestigerclaw": "https://rex.hermestigerclaw.com/api/health",
    "goldhealthsys":   "https://goldhealthsys.com",
}


class WebrexTopology:
    """GHS infrastructure topology manager."""

    def __init__(self):
        self._topology: dict = {}
        self._last_health_check: Optional[str] = None
        self._health_cache: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if TOPOLOGY_STATE.exists():
            with open(TOPOLOGY_STATE) as f:
                self._topology = json.load(f)
        else:
            logger.warning("WebrexTopology: state file not found at %s", TOPOLOGY_STATE)
            self._topology = {}

    def _save(self) -> None:
        self._topology["_updated"] = datetime.datetime.utcnow().isoformat()
        with open(TOPOLOGY_STATE, "w") as f:
            json.dump(self._topology, f, indent=2)

    # ── Health checks ────────────────────────────────────────────────────────

    async def _check_endpoint(self, name: str, url: str, timeout: float = 3.0) -> dict:
        """Check a single endpoint. Returns {name, status, latency_ms, error}."""
        start = datetime.datetime.utcnow()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    latency_ms = int((datetime.datetime.utcnow() - start).total_seconds() * 1000)
                    return {
                        "name": name,
                        "url": url,
                        "status": "UP" if resp.status < 500 else "DEGRADED",
                        "http_code": resp.status,
                        "latency_ms": latency_ms,
                        "checked_at": datetime.datetime.utcnow().isoformat(),
                    }
        except asyncio.TimeoutError:
            return {"name": name, "url": url, "status": "TIMEOUT", "latency_ms": None,
                    "checked_at": datetime.datetime.utcnow().isoformat()}
        except Exception as exc:
            return {"name": name, "url": url, "status": "DOWN", "error": str(exc),
                    "latency_ms": None, "checked_at": datetime.datetime.utcnow().isoformat()}

    async def run_health_checks(self) -> Dict[str, dict]:
        """Run all endpoint health checks concurrently."""
        all_endpoints = {**HEALTH_ENDPOINTS, **EXTERNAL_ENDPOINTS}
        tasks = [self._check_endpoint(name, url) for name, url in all_endpoints.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self._health_cache = {}
        for r in results:
            if isinstance(r, dict):
                self._health_cache[r["name"]] = r
        self._last_health_check = datetime.datetime.utcnow().isoformat()
        return self._health_cache

    def get_cached_health(self) -> dict:
        return {
            "last_checked": self._last_health_check,
            "services": self._health_cache,
        }

    # ── Topology data ────────────────────────────────────────────────────────

    def get_live_topology(self) -> dict:
        """Return topology with merged health status for dashboard."""
        topology = dict(self._topology)

        # Merge cached health into nodes
        nodes = topology.get("nodes", [])
        for node in nodes:
            node_services = node.get("services", [])
            node_health = []
            for svc_str in node_services:
                svc_name = svc_str.split(":")[0] if ":" in svc_str else svc_str
                if svc_name in self._health_cache:
                    node_health.append(self._health_cache[svc_name])
            if node_health:
                up_count = sum(1 for h in node_health if h.get("status") == "UP")
                node["live_health"] = "UP" if up_count == len(node_health) else (
                    "PARTIAL" if up_count > 0 else "DOWN"
                )

        topology["health_summary"] = self.get_cached_health()
        topology["generated_at"] = datetime.datetime.utcnow().isoformat()
        return topology

    def get_nodes(self) -> List[dict]:
        return self._topology.get("nodes", [])

    def get_clusters(self) -> List[dict]:
        return self._topology.get("clusters", [])

    def get_authority_chains(self) -> List[dict]:
        return self._topology.get("authority_chains", [])

    def update_node_status(self, node_id: str, status: str, note: str = "") -> None:
        """Update a node's status in the topology (from health check or manual)."""
        for node in self._topology.get("nodes", []):
            if node["id"] == node_id:
                node["status"] = status
                if note:
                    node["status_note"] = note
                node["last_updated"] = datetime.datetime.utcnow().isoformat()
                self._save()
                return
        logger.warning("WebrexTopology: node not found: %s", node_id)
