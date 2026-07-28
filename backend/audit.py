"""
REX — HIPAA-Grade Audit Logger
Logs all events required by the HIPAA Security Rule §164.312(b):
  - Who accessed what and when
  - Secure Mode toggles
  - Messages sent / received
  - PHI detection events
  - Decryption events (journey viewed)
  - API key changes
  - App start / stop
"""
import uuid
import logging
from typing import Dict, Any, Optional
from .storage import EncryptedStorage

logger = logging.getLogger(__name__)


# HIPAA-required audit event types
class AuditEventType:
    APP_START           = "APP_START"
    APP_STOP            = "APP_STOP"
    SECURE_MODE_ON      = "SECURE_MODE_ON"
    SECURE_MODE_OFF     = "SECURE_MODE_OFF"
    MESSAGE_SENT        = "MESSAGE_SENT"
    RESPONSE_RECEIVED   = "RESPONSE_RECEIVED"
    PHI_DETECTED        = "PHI_DETECTED"
    PHI_REDACTED        = "PHI_REDACTED"
    RESPONSE_SCAN_PASS  = "RESPONSE_SCAN_PASS"
    RESPONSE_SCAN_FAIL  = "RESPONSE_SCAN_FAIL"  # PHI slippage detected in response
    JOURNEY_CREATED     = "JOURNEY_CREATED"
    JOURNEY_VIEWED      = "JOURNEY_VIEWED"       # Decryption event
    JOURNEY_EXPORTED    = "JOURNEY_EXPORTED"
    API_KEY_SET         = "API_KEY_SET"
    API_KEY_REMOVED     = "API_KEY_REMOVED"
    STORAGE_RELOCATED   = "STORAGE_RELOCATED"
    ENCRYPTION_KEY_INIT = "ENCRYPTION_KEY_INIT"
    MODEL_CHANGED       = "MODEL_CHANGED"
    OLLAMA_REROUTE      = "OLLAMA_REROUTE"       # Auto-routed to local model due to PHI


class AuditLogger:
    """
    Thread-safe audit logger that writes encrypted events to the audit_log table.
    Every event includes: id, timestamp, event_type, details dict.
    """

    def __init__(self, storage: EncryptedStorage):
        self._storage = storage

    def log(self, event_type: str, details: Optional[Dict[str, Any]] = None):
        """
        Log an audit event. Safe to call from anywhere — never raises.
        PHI content must NEVER be included in audit details. Only metadata.
        """
        if details is None:
            details = {}

        # Scrub any accidental PHI from details
        safe_details = self._scrub_phi_from_details(details)

        try:
            event_id = str(uuid.uuid4())
            self._storage.log_audit(event_id, event_type, safe_details)
            logger.debug(f"[AUDIT] {event_type}: {safe_details}")
        except Exception as e:
            # Audit failures should never crash the app
            logger.error(f"Audit log write failed: {e}")

    def _scrub_phi_from_details(self, details: Dict) -> Dict:
        """
        Remove any keys that might contain PHI content.
        Audit logs record WHAT happened, not the content.
        """
        safe = {}
        FORBIDDEN_KEYS = {"content", "text", "message", "original", "phi_value", "response"}
        for k, v in details.items():
            if k.lower() in FORBIDDEN_KEYS:
                safe[k] = "[redacted]"
            elif isinstance(v, str) and len(v) > 200:
                safe[k] = v[:200] + "...[truncated]"
            else:
                safe[k] = v
        return safe

    # ── Convenience methods ───────────────────────────────────────────────────

    def app_start(self, version: str = "1.0.0"):
        self.log(AuditEventType.APP_START, {"version": version})

    def app_stop(self):
        self.log(AuditEventType.APP_STOP)

    def secure_mode_toggle(self, enabled: bool):
        event = AuditEventType.SECURE_MODE_ON if enabled else AuditEventType.SECURE_MODE_OFF
        self.log(event, {"enabled": enabled})

    def message_sent(self, journey_id: str, model: str, secure: bool, char_count: int):
        self.log(AuditEventType.MESSAGE_SENT, {
            "journey_id": journey_id,
            "model": model,
            "secure_mode": secure,
            "char_count": char_count,
        })

    def response_received(self, journey_id: str, model: str, secure: bool, char_count: int):
        self.log(AuditEventType.RESPONSE_RECEIVED, {
            "journey_id": journey_id,
            "model": model,
            "secure_mode": secure,
            "char_count": char_count,
        })

    def phi_detected(self, journey_id: str, entity_types: list, count: int):
        self.log(AuditEventType.PHI_DETECTED, {
            "journey_id": journey_id,
            "entity_types": entity_types,
            "phi_count": count,
        })

    def phi_redacted(self, journey_id: str, count: int):
        self.log(AuditEventType.PHI_REDACTED, {
            "journey_id": journey_id,
            "redacted_count": count,
        })

    def response_scan(self, journey_id: str, phi_found: bool):
        event = AuditEventType.RESPONSE_SCAN_FAIL if phi_found else AuditEventType.RESPONSE_SCAN_PASS
        self.log(event, {"journey_id": journey_id, "phi_in_response": phi_found})

    def journey_viewed(self, journey_id: str):
        self.log(AuditEventType.JOURNEY_VIEWED, {"journey_id": journey_id})

    def journey_exported(self, journey_id: str, format: str = "json"):
        self.log(AuditEventType.JOURNEY_EXPORTED, {
            "journey_id": journey_id,
            "format": format,
        })

    def api_key_set(self, provider: str):
        self.log(AuditEventType.API_KEY_SET, {"provider": provider})

    def ollama_reroute(self, journey_id: str, original_model: str, ollama_model: str, reason: str):
        self.log(AuditEventType.OLLAMA_REROUTE, {
            "journey_id": journey_id,
            "original_model": original_model,
            "routed_to": ollama_model,
            "reason": reason,
        })

    def model_changed(self, old_model: str, new_model: str):
        self.log(AuditEventType.MODEL_CHANGED, {
            "from": old_model,
            "to": new_model,
        })

    def get_recent_events(self, limit: int = 100) -> list:
        return self._storage.get_audit_log(limit=limit)
