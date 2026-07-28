"""
REX — Chairman Vault: Triple-Encryption Toggle
================================================
When VAULT MODE is ON (Chairman only), every piece of data flowing
through REX gets three independent encryption passes:

  Layer 1: AES-256-GCM   (standard, fast, authenticated)
  Layer 2: ChaCha20-Poly1305  (stream cipher, different math family)
  Layer 3: AES-256-GCM   (second pass, fresh nonce + derived key)

This means even if one cipher is compromised (e.g., a zero-day in
AES's hardware acceleration), the data is still protected by the other.

REX recognizes VAULT MODE in every response and marks its handling
differently so you always know which protection level is active.

Toggle in chat:
  "vault mode on"   → enables triple encryption for this session
  "vault mode off"  → returns to standard AES-256-GCM
  "vault status"    → shows current encryption level

Or programmatically:
  vault = ChairmanVault(master_key=storage._key)
  vault.set_vault_mode(True)
  sealed = vault.seal_triple("my sensitive data")
  plain  = vault.open_triple(sealed)

Architecture note:
  The vault key schedule derives 3 independent subkeys via HKDF,
  each with a unique info label. Compromise of one subkey cannot
  be used to derive the others.
"""

import os
import json
import base64
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Vault mode storage key in memory system
VAULT_MODE_MEMORY_TAG = "__chairman_vault_mode__"


# ── Key Derivation for 3 independent layers ────────────────────────────────

def _derive_layer_key(master_key: bytes, layer: int, label: str) -> bytes:
    """Derive an independent 32-byte key for each encryption layer."""
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    info = f"rex-vault-layer{layer}-{label}".encode("utf-8")
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=None,
        info=info,
        backend=default_backend(),
    )
    return hkdf.derive(master_key)


# ── Layer 1: AES-256-GCM ──────────────────────────────────────────────────

def _aes_gcm_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, data, None)
    return nonce + ct


def _aes_gcm_decrypt(payload: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, ct = payload[:12], payload[12:]
    return AESGCM(key).decrypt(nonce, ct, None)


# ── Layer 2: ChaCha20-Poly1305 ────────────────────────────────────────────

def _chacha_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = os.urandom(12)
    ct = ChaCha20Poly1305(key).encrypt(nonce, data, None)
    return nonce + ct


def _chacha_decrypt(payload: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce, ct = payload[:12], payload[12:]
    return ChaCha20Poly1305(key).decrypt(nonce, ct, None)


# ── Envelope format ───────────────────────────────────────────────────────

def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode(s: str) -> bytes:
    return base64.b64decode(s)


# ── Chairman Vault ─────────────────────────────────────────────────────────

class ChairmanVault:
    """
    Triple-encryption vault for the Chairman's most sensitive data.

    Each seal_triple() call applies 3 independent cipher passes:
      1. AES-256-GCM  (key derived with 'aes1' label)
      2. ChaCha20-Poly1305  (key derived with 'cha2' label)
      3. AES-256-GCM  (key derived with 'aes3' label — different from layer 1)

    open_triple() reverses in exact order. Each layer authenticates the
    data independently — any tampering at any layer is detected.

    The vault knows what mode REX is in:
      - standard: single AES-256-GCM (always active)
      - vault:    triple-layer (Chairman toggle)
    """

    VAULT_HEADER = b"REX-VAULT-v1:"
    STD_HEADER   = b"REX-STD-v1:"

    def __init__(self, master_key: bytes):
        self._master = master_key
        self._vault_mode: bool = False
        # Derive 3 independent subkeys
        self._k1 = _derive_layer_key(master_key, 1, "aes1")   # Layer 1: AES-GCM
        self._k2 = _derive_layer_key(master_key, 2, "cha2")   # Layer 2: ChaCha20
        self._k3 = _derive_layer_key(master_key, 3, "aes3")   # Layer 3: AES-GCM

    # ── Mode management ───────────────────────────────────────────────────

    @property
    def vault_mode(self) -> bool:
        return self._vault_mode

    def set_vault_mode(self, enabled: bool):
        self._vault_mode = enabled
        level = "TRIPLE-LAYER VAULT" if enabled else "STANDARD"
        logger.info(f"🔐 REX Vault: mode → {level}")

    def mode_label(self) -> str:
        if self._vault_mode:
            return "🔒🔒🔒 VAULT MODE (Triple-Encrypted)"
        return "🔒 Standard (AES-256-GCM)"

    def mode_description(self) -> str:
        if self._vault_mode:
            return (
                "**Triple-encryption active**\n"
                "Layer 1: AES-256-GCM\n"
                "Layer 2: ChaCha20-Poly1305\n"
                "Layer 3: AES-256-GCM (independent key)\n\n"
                "All data at rest and in motion passes through all three ciphers.\n"
                "Even a complete break of one cipher leaves your data protected."
            )
        return (
            "**Standard encryption active**\n"
            "AES-256-GCM — military-grade, HIPAA-compliant.\n"
            "Vault mode available for maximum protection."
        )

    # ── Triple-layer seal ─────────────────────────────────────────────────

    def seal(self, plaintext: str) -> str:
        """
        Encrypt a string. Uses triple-layer if vault mode is ON,
        single-layer otherwise. Always returns a base64 string with
        a header so REX can identify which mode produced it.
        """
        data = plaintext.encode("utf-8")
        if self._vault_mode:
            return self._seal_triple(data)
        return self._seal_standard(data)

    def open(self, sealed: str) -> Optional[str]:
        """
        Decrypt a sealed string. Auto-detects vault vs standard
        from the header so REX can decrypt regardless of current mode.
        """
        try:
            raw = _decode(sealed)
        except Exception:
            return None

        if raw.startswith(self.VAULT_HEADER):
            result = self._open_triple(raw[len(self.VAULT_HEADER):])
        elif raw.startswith(self.STD_HEADER):
            result = self._open_standard(raw[len(self.STD_HEADER):])
        else:
            # Fallback: try standard
            result = self._open_standard(raw)

        if result is None:
            return None
        try:
            return result.decode("utf-8")
        except Exception:
            return None

    def _seal_standard(self, data: bytes) -> str:
        ct = _aes_gcm_encrypt(data, self._k1)
        return _encode(self.STD_HEADER + ct)

    def _open_standard(self, data: bytes) -> Optional[bytes]:
        try:
            return _aes_gcm_decrypt(data, self._k1)
        except Exception:
            return None

    def _seal_triple(self, data: bytes) -> str:
        # Pass 1: AES-GCM
        ct1 = _aes_gcm_encrypt(data, self._k1)
        # Pass 2: ChaCha20-Poly1305
        ct2 = _chacha_encrypt(ct1, self._k2)
        # Pass 3: AES-GCM (independent key)
        ct3 = _aes_gcm_encrypt(ct2, self._k3)
        return _encode(self.VAULT_HEADER + ct3)

    def _open_triple(self, data: bytes) -> Optional[bytes]:
        try:
            # Reverse order: Layer 3 → 2 → 1
            ct2 = _aes_gcm_decrypt(data, self._k3)
            ct1 = _chacha_decrypt(ct2, self._k2)
            plain = _aes_gcm_decrypt(ct1, self._k1)
            return plain
        except Exception as e:
            logger.error(f"REX Vault: triple-decrypt failed: {e}")
            return None

    # ── Command detector for REX chat ─────────────────────────────────────

    CMD_VAULT_ON  = ("vault mode on", "enable vault", "vault on", "triple encrypt on")
    CMD_VAULT_OFF = ("vault mode off", "disable vault", "vault off", "triple encrypt off")
    CMD_VAULT_STATUS = ("vault status", "encryption status", "vault mode status")

    def detect_vault_command(self, user_text: str, user_role: str) -> Optional[str]:
        """
        Detect and handle vault mode commands from chat.
        Returns a reply string if command was found, None otherwise.
        Only the Chairman can toggle vault mode.
        """
        lower = user_text.strip().lower()

        for cmd in self.CMD_VAULT_STATUS:
            if cmd in lower:
                return (
                    f"**REX Encryption Status**\n\n"
                    f"Current mode: {self.mode_label()}\n\n"
                    f"{self.mode_description()}"
                )

        for cmd in self.CMD_VAULT_ON:
            if cmd in lower:
                if user_role != "chairman":
                    return "🔒 Only the Chairman can toggle Vault Mode."
                self.set_vault_mode(True)
                return (
                    "🔒🔒🔒 **VAULT MODE ACTIVATED**\n\n"
                    "REX is now applying **triple encryption** to all data:\n\n"
                    "• **Layer 1:** AES-256-GCM\n"
                    "• **Layer 2:** ChaCha20-Poly1305 _(different cipher family)_\n"
                    "• **Layer 3:** AES-256-GCM _(independent key)_\n\n"
                    "Even if one cipher is ever broken, two more protect your data.\n\n"
                    "REX will mark all vault-encrypted responses with 🔒🔒🔒\n"
                    "Type `vault mode off` to return to standard encryption."
                )

        for cmd in self.CMD_VAULT_OFF:
            if cmd in lower:
                if user_role != "chairman":
                    return "🔒 Only the Chairman can toggle Vault Mode."
                self.set_vault_mode(False)
                return (
                    "🔒 **Vault Mode deactivated.**\n\n"
                    "REX has returned to standard AES-256-GCM encryption.\n"
                    "Your data remains protected — this is still HIPAA-grade security.\n\n"
                    "Type `vault mode on` to re-enable triple encryption."
                )

        return None
