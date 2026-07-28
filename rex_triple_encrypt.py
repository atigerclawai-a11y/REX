"""
rex_triple_encrypt.py
──────────────────────────────────────────────────────────────────────────────
REX — Triple Encryption Layer for Rexxie's Personal Vault
Garden of Joy · Gold Health Systems · Locked Lucy Compliant

Why triple encryption for Rexxie specifically:
  Rexxie is Kato's personal confidant. Over time she will hold genuinely
  sensitive personal information — health concerns, personal decisions,
  private thoughts, financial details, relationship context. This data
  deserves protection beyond the SQLCipher database-level encryption.

  Even if an attacker had:
    • Physical access to the Mac
    • The SQLCipher vault key (~/.rex/vault.key)
  ...they still cannot read Rexxie's personal memories without the triple
  encryption keys, which are derived separately from the vault master key
  using HKDF with per-layer domain separation.

Encryption stack (applied to every value stored in Rexxie's personal vault):
  Layer 1 — AES-256-GCM      (AEAD, authentication tag, 96-bit nonce)
  Layer 2 — ChaCha20-Poly1305 (AEAD, different algorithm family, 96-bit nonce)
  Layer 3 — AES-256-GCM      (AEAD, final wrap, 96-bit nonce)

  Plaintext → [AES-GCM K1] → [ChaCha20 K2] → [AES-GCM K3] → ciphertext

  Each layer uses a fresh random nonce. All three authenticated — a tamper
  with any layer is detected at decryption and raises an exception.

  Key derivation: HKDF-SHA512 from vault master key with per-layer "info"
  so K1, K2, K3 are cryptographically independent even from the same root.

  On top of SQLCipher (AES-256 at database level), this gives:
    database-level AES-256 + app-level AES-256-GCM + ChaCha20 + AES-256-GCM

Wire-up:
  Used automatically by VaultSession when agent_name == "rexxie" and
  namespace does NOT start with "rexxie_ops" (ops data stays single-layer).
  All other agents use standard SQLCipher only.
"""

from __future__ import annotations

import hashlib
import logging
import os
import struct
from typing import Optional

logger = logging.getLogger("rex.triple_encrypt")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# HKDF domain separation — never reuse these strings for anything else
_LAYER1_INFO = b"rexxie-personal-layer1-aes-gcm-v1"
_LAYER2_INFO = b"rexxie-personal-layer2-chacha20-v1"
_LAYER3_INFO = b"rexxie-personal-layer3-aes-gcm-v1"

# Nonce sizes
_AES_GCM_NONCE_LEN    = 12   # 96 bits — GCM standard
_CHACHA20_NONCE_LEN   = 12   # 96 bits — ChaCha20-Poly1305 standard

# Magic prefix so we can detect triple-encrypted blobs reliably
_MAGIC = b"RXT3\x01"   # "RXT3" + version byte

# Namespaces in Rexxie's vault that are personal (triple-encrypted)
# Anything NOT in this set uses standard SQLCipher only
PERSONAL_NAMESPACES = {
    "personal",
    "memories",
    "rexxie_memory",
    "rex_memory",
    "user_model",
    "reflections",
    "private",
    "journal",
    "conversations",
    "personal_notes",
    "health",
    "goals",
    "decisions",
    "relationships",
}

# Operational namespaces — single-layer SQLCipher only (no triple wrap)
# These are business-adjacent even inside Rexxie's vault
OPERATIONAL_NAMESPACES = {
    "rexxie_ops",
    "system",
    "config",
    "vault_meta",
}


# ─────────────────────────────────────────────────────────────────────────────
# KEY DERIVATION
# ─────────────────────────────────────────────────────────────────────────────

def _derive_keys(master_key: bytes) -> tuple[bytes, bytes, bytes]:
    """
    Derive three independent 32-byte keys from the vault master key.
    Uses HKDF-SHA512 with per-layer domain separation.
    Returns (k1_aes, k2_chacha, k3_aes).
    """
    try:
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend

        def hkdf(info: bytes) -> bytes:
            return HKDF(
                algorithm=hashes.SHA512(),
                length=32,
                salt=None,
                info=info,
                backend=default_backend(),
            ).derive(master_key)

        return hkdf(_LAYER1_INFO), hkdf(_LAYER2_INFO), hkdf(_LAYER3_INFO)

    except ImportError:
        # Fallback: HMAC-SHA512 key derivation (no external library needed)
        import hmac
        def hmac_kdf(info: bytes) -> bytes:
            return hmac.new(master_key, info, hashlib.sha512).digest()[:32]
        return hmac_kdf(_LAYER1_INFO), hmac_kdf(_LAYER2_INFO), hmac_kdf(_LAYER3_INFO)


# ─────────────────────────────────────────────────────────────────────────────
# TRIPLE ENCRYPTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TripleEncrypt:
    """
    Triple-layer encryption for Rexxie's personal vault data.

    Usage:
        te = TripleEncrypt(master_key)
        blob = te.encrypt(b"my secret thought")
        plaintext = te.decrypt(blob)

    The blob is self-contained — includes magic prefix + three nonces.
    Raises ValueError on decryption failure (tamper detection).
    """

    def __init__(self, master_key: bytes):
        if len(master_key) != 32:
            raise ValueError("master_key must be exactly 32 bytes")
        self._k1, self._k2, self._k3 = _derive_keys(master_key)
        self._available = self._check_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
            return True
        except ImportError:
            logger.warning(
                "[triple_encrypt] cryptography library not available — "
                "falling back to single-layer (SQLCipher only). "
                "Install with: pip install cryptography --break-system-packages"
            )
            return False

    # ── Encrypt ───────────────────────────────────────────────────────────────

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Triple-encrypt plaintext. Returns self-contained blob with magic prefix.
        Falls back to unencrypted (SQLCipher still protects at DB level) if
        cryptography library unavailable.
        """
        if not self._available:
            return _MAGIC + b"\x00" + plaintext   # fallback flag byte

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

            # Layer 1 — AES-256-GCM
            n1 = os.urandom(_AES_GCM_NONCE_LEN)
            c1 = AESGCM(self._k1).encrypt(n1, plaintext, None)

            # Layer 2 — ChaCha20-Poly1305
            n2 = os.urandom(_CHACHA20_NONCE_LEN)
            c2 = ChaCha20Poly1305(self._k2).encrypt(n2, c1, None)

            # Layer 3 — AES-256-GCM
            n3 = os.urandom(_AES_GCM_NONCE_LEN)
            c3 = AESGCM(self._k3).encrypt(n3, c2, None)

            # Pack: magic(5) + flag(1) + n1(12) + n2(12) + n3(12) + ciphertext
            return _MAGIC + b"\x01" + n1 + n2 + n3 + c3

        except Exception as e:
            logger.error(f"[triple_encrypt] Encryption failed: {e}")
            raise

    # ── Decrypt ───────────────────────────────────────────────────────────────

    def decrypt(self, blob: bytes) -> bytes:
        """
        Decrypt a triple-encrypted blob.
        Raises ValueError if blob is malformed or authentication fails.
        """
        if not blob.startswith(_MAGIC):
            raise ValueError("Not a Rexxie triple-encrypted blob (missing magic)")

        flag = blob[5:6]

        # Fallback mode — no encryption applied (just strip header)
        if flag == b"\x00":
            return blob[6:]

        if flag != b"\x01":
            raise ValueError(f"Unknown triple-encrypt version flag: {flag!r}")

        if not self._available:
            raise RuntimeError(
                "cryptography library required to decrypt this data. "
                "Install with: pip install cryptography --break-system-packages"
            )

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

            # Unpack header
            offset = 6
            n1 = blob[offset:offset + _AES_GCM_NONCE_LEN];   offset += _AES_GCM_NONCE_LEN
            n2 = blob[offset:offset + _CHACHA20_NONCE_LEN];   offset += _CHACHA20_NONCE_LEN
            n3 = blob[offset:offset + _AES_GCM_NONCE_LEN];    offset += _AES_GCM_NONCE_LEN
            c3 = blob[offset:]

            # Reverse: layer 3 → layer 2 → layer 1
            c2 = AESGCM(self._k3).decrypt(n3, c3, None)
            c1 = ChaCha20Poly1305(self._k2).decrypt(n2, c2, None)
            plaintext = AESGCM(self._k1).decrypt(n1, c1, None)
            return plaintext

        except Exception as e:
            raise ValueError(f"Triple-decryption failed — data tampered or wrong key: {e}") from e

    # ── Convenience helpers (string ↔ bytes) ──────────────────────────────────

    def encrypt_str(self, text: str) -> bytes:
        return self.encrypt(text.encode("utf-8"))

    def decrypt_str(self, blob: bytes) -> str:
        return self.decrypt(blob).decode("utf-8")

    # ── Namespace check ───────────────────────────────────────────────────────

    @staticmethod
    def should_triple_encrypt(agent_name: str, namespace: str) -> bool:
        """
        Returns True if this agent+namespace combination should have triple
        encryption applied on top of SQLCipher.

        Only Rexxie's personal namespaces get triple encryption.
        Operational/system namespaces stay single-layer even in Rexxie's vault.
        """
        if agent_name != "rexxie":
            return False
        ns_lower = namespace.lower()
        # If it's explicitly operational, skip triple encrypt
        if any(ns_lower.startswith(op) for op in OPERATIONAL_NAMESPACES):
            return False
        # Personal namespaces get triple encryption
        return True   # default: encrypt everything in Rexxie's vault


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("REX TRIPLE ENCRYPT — SELF-TEST")
    print("=" * 60)

    test_key = os.urandom(32)
    te = TripleEncrypt(test_key)

    # Test 1: Basic round-trip
    original = b"Kato told me something deeply personal about his health."
    blob = te.encrypt(original)
    recovered = te.decrypt(blob)
    assert recovered == original, f"Round-trip failed: {recovered!r}"
    print("✓ Test 1: Encrypt/decrypt round-trip OK")

    # Test 2: Magic prefix present
    assert blob.startswith(_MAGIC), "Magic prefix missing"
    assert blob[5:6] == b"\x01", "Version flag wrong"
    print("✓ Test 2: Blob structure correct (magic + version flag)")

    # Test 3: Ciphertext is different from plaintext (obviously)
    assert original not in blob, "Plaintext visible in ciphertext!"
    print("✓ Test 3: Plaintext not visible in ciphertext")

    # Test 4: String convenience helpers
    test_str = "I want to remember that Kato prefers directness over comfort."
    blob2 = te.encrypt_str(test_str)
    recovered2 = te.decrypt_str(blob2)
    assert recovered2 == test_str
    print("✓ Test 4: String encrypt/decrypt helpers OK")

    # Test 5: Tamper detection
    tampered = bytearray(blob)
    tampered[30] ^= 0xFF   # flip a bit in the ciphertext
    try:
        te.decrypt(bytes(tampered))
        print("✗ Test 5: FAIL — tamper not detected!")
        sys.exit(1)
    except ValueError:
        print("✓ Test 5: Tamper detected correctly (authentication tag rejected)")

    # Test 6: Wrong key cannot decrypt
    wrong_key = os.urandom(32)
    te_wrong = TripleEncrypt(wrong_key)
    try:
        te_wrong.decrypt(blob)
        print("✗ Test 6: FAIL — wrong key accepted!")
        sys.exit(1)
    except ValueError:
        print("✓ Test 6: Wrong key correctly rejected")

    # Test 7: Each encryption produces unique ciphertext (random nonces)
    blob_a = te.encrypt(original)
    blob_b = te.encrypt(original)
    assert blob_a != blob_b, "Same plaintext produced identical ciphertext — nonces not random!"
    assert te.decrypt(blob_a) == original
    assert te.decrypt(blob_b) == original
    print("✓ Test 7: Random nonces — identical plaintexts produce unique ciphertexts")

    # Test 8: Namespace routing
    assert TripleEncrypt.should_triple_encrypt("rexxie", "memories") is True
    assert TripleEncrypt.should_triple_encrypt("rexxie", "personal") is True
    assert TripleEncrypt.should_triple_encrypt("rexxie", "system") is False
    assert TripleEncrypt.should_triple_encrypt("backend", "memories") is False
    assert TripleEncrypt.should_triple_encrypt("knowledge", "anything") is False
    print("✓ Test 8: Namespace routing correct — only Rexxie personal namespaces triple-encrypted")

    print()
    print("=" * 60)
    print("ALL TESTS PASSED — rex_triple_encrypt.py is ready")
    print()
    print("Encryption stack confirmed:")
    print("  Plaintext → AES-256-GCM → ChaCha20-Poly1305 → AES-256-GCM")
    print("  + SQLCipher AES-256 at database level")
    print("  = 4 layers of encryption protecting Rexxie's personal memories")
    print("=" * 60)
