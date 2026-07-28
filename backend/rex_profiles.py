"""
backend/rex_profiles.py
========================
Phase 14 — Business Profile Engine
Gold Health Systems · Packet B

PURPOSE:
    Manages the four GHS business profiles: GOJ, Sports Bar, Web Design, Social Media.
    Each profile has its own: system prompt context, agent assignments, data scope,
    memory partition, and allowed operations.

ACTIVATION STATUS: READY — pending import in backend/main.py
    Add to main.py startup:
        from backend.rex_profiles import ProfileEngine
        profile_engine = ProfileEngine()

Gold Health Systems · Phase 14 · June 4, 2026
"""

import json
import logging
import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from core.business_isolation import get_isolation_enforcer, CrossContextViolation

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

STATE_DIR = Path.home() / "Desktop" / "REX" / "state"
BUSINESS_REGISTRY = STATE_DIR / "business_registry.json"
VENTURE_REGISTRY  = STATE_DIR / "venture_registry.json"
PROFILES_FILE     = STATE_DIR / "profiles.json"


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ProfileEngine:
    """
    Manages GHS business profiles.
    Reads from state/ JSON files. Applies isolation rules on access.
    """

    def __init__(self):
        self._enforcer = get_isolation_enforcer()
        self._profiles: Dict[str, Any] = {}
        self._business_registry: Dict[str, Any] = {}
        self._active_profile: Optional[str] = None
        self._load_all()

    def _load_all(self) -> None:
        """Load all profile and registry files from state/."""
        for path, attr in [
            (PROFILES_FILE, "_profiles"),
            (BUSINESS_REGISTRY, "_business_registry"),
        ]:
            if path.exists():
                with open(path) as f:
                    setattr(self, attr, json.load(f))
                logger.info("ProfileEngine: loaded %s", path.name)
            else:
                logger.warning("ProfileEngine: %s not found — using empty dict", path.name)

    def reload(self) -> None:
        """Reload all profile data from disk (call after manual edits)."""
        self._load_all()

    # ── Profile lookup ───────────────────────────────────────────────────────

    def get_profile(self, context_code: str) -> Optional[Dict[str, Any]]:
        """Return the full profile dict for a context, or None."""
        self._enforcer.validate_context(context_code)
        return self._profiles.get(context_code)

    def get_active_profile(self) -> Optional[Dict[str, Any]]:
        if self._active_profile:
            return self.get_profile(self._active_profile)
        return None

    def set_active_context(self, context_code: str, session_id: Optional[str] = None) -> None:
        """
        Switch the active profile. Triggers isolation check if crossing contexts.
        """
        if self._active_profile and self._active_profile != context_code:
            self._enforcer.assert_access(
                requesting_context=self._active_profile,
                target_context=context_code,
                session_id=session_id,
                reason="profile_switch",
            )
        self._active_profile = context_code
        logger.info("ProfileEngine: active context → %s", context_code)

    # ── System prompt injection ──────────────────────────────────────────────

    def get_system_prompt_injection(self, context_code: str) -> str:
        """
        Return a system-prompt snippet for the given business context.
        Injected by sovereign.py / build_system_prompt().
        """
        snippets = {
            "goj": (
                "ACTIVE CONTEXT: Garden of Joy Adult Day Care (GOJ), Brooklyn NY. "
                "~425 HIPAA-covered clients. Primary focus: scheduling, authorization, menus, "
                "attendance, driver routes. GOJ data is PHI — apply Gate 1 tokenization before "
                "any cloud routing. Russian-speaking client population."
            ),
            "sports_bar": (
                "ACTIVE CONTEXT: Boardwalk Beer Garden & Restaurant (BBG). "
                "Focus: inventory, events, Masha voice agent, POS integration (Clover). "
                "Not HIPAA. Standard business confidentiality."
            ),
            "web_design": (
                "ACTIVE CONTEXT: Gold Health Systems Web Design Business. "
                "Focus: goldhealthsys.com (Railway, 34 modules), hermestigerclaw.com (Cloudflare). "
                "WebRex manages staging and publish pipeline."
            ),
            "social_media": (
                "ACTIVE CONTEXT: GHS Social Media Agency. "
                "Focus: content scheduling, client social accounts, CC_social_media_router.py. "
                "Public-facing content — standard brand safety rules apply."
            ),
        }
        self._enforcer.validate_context(context_code)
        return snippets.get(context_code, "")

    # ── Business registry ────────────────────────────────────────────────────

    def list_businesses(self) -> list:
        """Return list of all registered businesses."""
        return list(self._business_registry.get("businesses", []))

    def get_business(self, context_code: str) -> Optional[Dict[str, Any]]:
        """Return business metadata for a context code."""
        for biz in self.list_businesses():
            if biz.get("code") == context_code:
                return biz
        return None

    # ── Status ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "active_context": self._active_profile,
            "profiles_loaded": list(self._profiles.keys()),
            "businesses_registered": len(self.list_businesses()),
            "isolation_report": self._enforcer.isolation_report(),
        }
