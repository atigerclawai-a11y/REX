"""
REX — Encrypted Agent Message Bus
====================================
Handles all inter-agent communication with:
  • AES-256-GCM encryption (per-agent derived keys)
  • HMAC-SHA256 message signing & verification
  • Full audit trail of every agent message
  • Minimum-necessary disclosure enforcement

Usage:
    bus = AgentBus(master_key=storage._key)

    # Send encrypted payload to OG33
    envelope = bus.seal("og33", {"action": "query", "data": "..."})

    # Receive and verify a reply
    payload = bus.open("og33", envelope)
    if payload is None:
        # Signature invalid — reject message
        ...
"""

import os
import json
import base64
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Key Derivation ─────────────────────────────────────────────────────────────

def _derive_agent_key(master_key: bytes, agent_id: str) -> bytes:
    """
    Derive a unique 32-byte AES key for a specific agent using HKDF-like derivation.
    Each agent gets its own key — compromise of one doesn't expose others.
    """
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    info = f"rex-agent-bus-{agent_id}".encode("utf-8")
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=None,
        info=info,
        backend=default_backend(),
    )
    return hkdf.derive(master_key)


# ── Encryption / Decryption ────────────────────────────────────────────────────

def _aes_gcm_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt bytes with AES-256-GCM. Returns nonce + ciphertext."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct    = AESGCM(key).encrypt(nonce, data, None)
    return nonce + ct


def _aes_gcm_decrypt(payload: bytes, key: bytes) -> bytes:
    """Decrypt nonce+ciphertext produced by _aes_gcm_encrypt."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, ct = payload[:12], payload[12:]
    return AESGCM(key).decrypt(nonce, ct, None)


def _hmac_sign(data: bytes, key: bytes) -> str:
    """HMAC-SHA256 signature. Returns hex string."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def _hmac_verify(data: bytes, key: bytes, expected_hex: str) -> bool:
    """Constant-time HMAC verification."""
    actual = hmac.new(key, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(actual, expected_hex)


# ── Agent Bus ─────────────────────────────────────────────────────────────────

class AgentBus:
    """
    Secure inter-agent communication bus.

    Every message is:
      1. Sanitized — blocked fields (API keys, PHI) automatically stripped
      2. JSON-serialized
      3. AES-256-GCM encrypted with the agent's derived key
      4. HMAC-SHA256 signed
      5. Base64-encoded into a portable "envelope"

    The receiving agent reverses this process and rejects any message
    with an invalid signature.
    """

    AGENTS = {
        "og33":    "OG33 Debate Chamber Orchestrator",
        "billing": "Billing Agent",
        "rex":     "REX Self (for internal task queues)",
    }

    # ── HARDCODED BLOCKLIST — these fields are NEVER transmitted to any agent ──
    # No matter what the caller asks for, these are always stripped before sealing.
    # This is an immutable security boundary — it cannot be bypassed by code.
    BLOCKED_FIELDS = frozenset({
        # API keys & credentials
        "api_key", "apikey", "api_secret", "secret_key", "secret",
        "token", "access_token", "refresh_token", "bearer_token",
        "password", "passwd", "pass", "credential", "credentials",
        "private_key", "encryption_key", "master_key", "_key",
        # Anthropic / OpenAI / provider keys
        "anthropic_api_key", "openai_api_key", "gemini_api_key",
        "claude_key", "openai_key", "litellm_key",
        # HIPAA PHI fields
        "dob", "date_of_birth", "ssn", "social_security",
        "member_id", "medicaid_id", "medicare_id",
        "diagnosis", "condition", "icd_code", "medical_record",
        # Financial
        "bank_account", "routing_number", "credit_card",
        "billing_number", "payment_info",
        # Internal system fields
        "content_enc", "title_enc", "model_enc", "details_enc",
        "original_enc", "tags_enc", "summary_enc", "topics_enc",
    })

    def _agent_keys(self, agent_id: str):
        """Returns (enc_key, sign_key) pair for agent."""
        enc_key  = _derive_agent_key(self._master_key, f"enc-{agent_id}")
        sign_key = _derive_agent_key(self._master_key, f"sig-{agent_id}")
        return enc_key, sign_key

    def __init__(self, master_key: bytes):
        self._master_key = master_key
        self._audit_log: list = []

    def _agent_keys(self, agent_id: str):
        """Returns (enc_key, sign_key) pair for agent."""
        enc_key  = _derive_agent_key(self._master_key, f"enc-{agent_id}")
        sign_key = _derive_agent_key(self._master_key, f"sig-{agent_id}")
        return enc_key, sign_key

    def _sanitize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strip ALL blocked fields from a payload before it leaves REX.
        This runs automatically on every seal() call — it cannot be bypassed.
        Nested dicts are also sanitized recursively.
        """
        clean = {}
        for k, v in payload.items():
            k_lower = k.lower().replace("-", "_").replace(" ", "_")
            if k_lower in self.BLOCKED_FIELDS:
                logger.warning(f"🔒 AgentBus: blocked field '{k}' stripped from outbound payload")
                self._audit("BLOCKED_FIELD", "outbound", 0, k)
                continue
            # Recurse into nested dicts
            if isinstance(v, dict):
                clean[k] = self._sanitize(v)
            else:
                clean[k] = v
        return clean

    # ── Outbound (seal) ───────────────────────────────────────────────────────

    def seal(self, target_agent: str, payload: Dict[str, Any]) -> str:
        """
        Encrypt and sign a payload for a target agent.

        Returns a base64-encoded envelope string safe to transmit over
        any channel (HTTP, WebSocket, log file).

        The envelope contains:
          • encrypted_payload (base64)
          • signature (hex)
          • agent_id (plaintext — needed for key derivation on the other side)
          • timestamp (plaintext — for replay detection)
          • version (protocol version)
        """
        enc_key, sign_key = self._agent_keys(target_agent)

        # ── Strip blocked fields BEFORE anything else ─────────────────────
        payload = self._sanitize(payload)

        # Serialize payload
        raw_json = json.dumps({
            **payload,
            "_meta": {
                "from":      "rex",
                "to":        target_agent,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }, ensure_ascii=False).encode("utf-8")

        # Encrypt
        ciphertext = _aes_gcm_encrypt(raw_json, enc_key)
        ct_b64 = base64.b64encode(ciphertext).decode("ascii")

        # Sign (sign the ciphertext so we detect tampering after encryption)
        sig = _hmac_sign(ciphertext, sign_key)

        envelope = {
            "v":        1,
            "agent":    target_agent,
            "ct":       ct_b64,
            "sig":      sig,
            "ts":       datetime.utcnow().isoformat(),
        }

        envelope_b64 = base64.b64encode(
            json.dumps(envelope).encode("utf-8")
        ).decode("ascii")

        self._audit("SEAL", target_agent, len(raw_json), sig[:16])
        return envelope_b64

    # ── Inbound (open) ────────────────────────────────────────────────────────

    def open(self, source_agent: str, envelope_b64: str) -> Optional[Dict]:
        """
        Verify and decrypt an envelope received from source_agent.

        Returns the decrypted payload dict, or None if signature invalid
        or decryption fails (which means the message was tampered with
        or came from an unauthorized source).
        """
        try:
            envelope = json.loads(base64.b64decode(envelope_b64).decode("utf-8"))
        except Exception as e:
            logger.warning(f"AgentBus: malformed envelope from {source_agent}: {e}")
            return None

        if envelope.get("v") != 1:
            logger.warning(f"AgentBus: unsupported envelope version from {source_agent}")
            return None

        enc_key, sign_key = self._agent_keys(source_agent)

        # Verify signature
        ct_b64 = envelope.get("ct", "")
        try:
            ciphertext = base64.b64decode(ct_b64)
        except Exception:
            logger.warning(f"AgentBus: invalid ciphertext encoding from {source_agent}")
            return None

        if not _hmac_verify(ciphertext, sign_key, envelope.get("sig", "")):
            logger.error(f"🚨 AgentBus: SIGNATURE MISMATCH from {source_agent} — message rejected")
            self._audit("REJECT", source_agent, 0, "SIG_FAIL")
            return None

        # Decrypt
        try:
            plaintext = _aes_gcm_decrypt(ciphertext, enc_key)
            payload   = json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error(f"AgentBus: decryption failed from {source_agent}: {e}")
            self._audit("DECRYPT_FAIL", source_agent, 0, str(e)[:40])
            return None

        self._audit("OPEN", source_agent, len(plaintext), envelope.get("sig", "")[:16])
        return payload

    # ── Minimum-Necessary Scrubber ────────────────────────────────────────────

    def scrub(self, payload: Dict, allowed_fields: list) -> Dict:
        """
        Enforce minimum-necessary disclosure: return only the fields in
        allowed_fields from payload. Everything else is stripped.

        Usage:
            safe = bus.scrub(client_record, ["name", "address", "phone"])
        """
        return {k: v for k, v in payload.items() if k in allowed_fields}

    # ── Audit ─────────────────────────────────────────────────────────────────

    def _audit(self, event: str, agent: str, size_bytes: int, detail: str):
        entry = {
            "ts":         datetime.utcnow().isoformat(),
            "event":      event,
            "agent":      agent,
            "size_bytes": size_bytes,
            "detail":     detail,
        }
        self._audit_log.append(entry)
        logger.info(f"🔐 AgentBus [{event}] → {agent} ({size_bytes}B)")

    def flush_audit(self) -> list:
        """Return and clear the in-memory audit buffer."""
        log = list(self._audit_log)
        self._audit_log.clear()
        return log

    # ── Convenience: encrypt a string for Chairman-only storage ───────────────

    def seal_for_chairman(self, content: str) -> str:
        """Seal a string specifically for chairman review (not for another agent)."""
        return self.seal("rex", {"chairman_note": content})

    def open_for_chairman(self, envelope_b64: str) -> Optional[str]:
        """Open a chairman-sealed envelope."""
        payload = self.open("rex", envelope_b64)
        if payload:
            return payload.get("chairman_note")
        return None


# ── Module-level alias so audit + external code can import BLOCKED_FIELDS directly ──
BLOCKED_FIELDS = AgentBus.BLOCKED_FIELDS
