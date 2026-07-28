"""
REX — Encrypted Transcript Store
==================================
Saves every session transcript to disk using triple-layer encryption,
matching Rexxie's vault-level security standard.

Encryption stack (same as Rexxie personal memories):
  Layer 1 — AES-256-GCM    (authenticated encryption)
  Layer 2 — ChaCha20-Poly1305  (different cipher family, independent nonce)
  Layer 3 — AES-256-GCM    (outer seal)

Each layer uses a distinct HKDF-derived sub-key so compromising one layer
does not expose the others.

Storage:
  Transcripts are saved to ~/Desktop/REX/transcripts/
  Each file is named:  <ISO timestamp>_<session_id>.rext
  They can only be read by rex_encrypted_transcript.py using the REX master key.

Usage from main.py:
  from .rex_encrypted_transcript import TranscriptStore
  transcript_store = TranscriptStore(master_key=storage._key)
  transcript_store.save(session_id, messages, rexxie_active=rexxie.active)

Command-line viewer (run from ~/Desktop/REX):
  python backend/rex_encrypted_transcript.py --list
  python backend/rex_encrypted_transcript.py --read <filename>
  python backend/rex_encrypted_transcript.py --export <filename>   (exports plain text)
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

TRANSCRIPT_DIR = Path.home() / "Desktop" / "REX" / "transcripts"


# ── Crypto primitives (identical stack to Rexxie triple-encrypt) ──────────────

def _derive(master: bytes, label: str) -> bytes:
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    return HKDF(SHA256(), 32, None, label.encode(), default_backend()).derive(master)


def _aes_gcm_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, None)


def _aes_gcm_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(data[:12], data[12:], None)


def _chacha_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = os.urandom(12)
    return nonce + ChaCha20Poly1305(key).encrypt(nonce, data, None)


def _chacha_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    return ChaCha20Poly1305(key).decrypt(data[:12], data[12:], None)


def _triple_encrypt(data: bytes, master: bytes) -> bytes:
    """AES-256-GCM → ChaCha20-Poly1305 → AES-256-GCM with independent derived keys."""
    k1 = _derive(master, "transcript-layer1-aes")
    k2 = _derive(master, "transcript-layer2-cha")
    k3 = _derive(master, "transcript-layer3-aes")
    ct = _aes_gcm_encrypt(data, k1)
    ct = _chacha_encrypt(ct, k2)
    ct = _aes_gcm_encrypt(ct, k3)
    return ct


def _triple_decrypt(data: bytes, master: bytes) -> bytes:
    k1 = _derive(master, "transcript-layer1-aes")
    k2 = _derive(master, "transcript-layer2-cha")
    k3 = _derive(master, "transcript-layer3-aes")
    ct = _aes_gcm_decrypt(data, k3)
    ct = _chacha_decrypt(ct, k2)
    ct = _aes_gcm_decrypt(ct, k1)
    return ct


# ── Transcript Store ──────────────────────────────────────────────────────────

class TranscriptStore:
    """
    Saves and reads encrypted session transcripts.
    All files are triple-encrypted at rest — unreadable without the REX master key.
    """

    def __init__(self, master_key: Optional[bytes] = None):
        self._key = master_key or self._load_or_create_key()
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    def _load_or_create_key(self) -> bytes:
        """Fall back to keyring or file-based key if no master key passed in."""
        key_path = Path.home() / "Desktop" / "REX" / ".transcript_key"
        try:
            import keyring
            existing = keyring.get_password("rex-sovereign", "transcript-key")
            if existing:
                return bytes.fromhex(existing)
            key = os.urandom(32)
            keyring.set_password("rex-sovereign", "transcript-key", key.hex())
            return key
        except Exception:
            if key_path.exists():
                return bytes.fromhex(key_path.read_text().strip())
            key = os.urandom(32)
            key_path.write_text(key.hex())
            key_path.chmod(0o600)
            return key

    def save(
        self,
        session_id: str,
        messages: list,
        rexxie_active: bool = False,
        user_name: str = "Kato",
    ) -> Optional[Path]:
        """
        Save a session's messages as a triple-encrypted transcript file.
        System messages are excluded (they contain full sovereign prompt — not needed for review).
        Returns the saved file path, or None on failure.
        """
        try:
            # Strip system messages — we only need human/assistant exchanges
            visible = [m for m in messages if m.get("role") != "system"]
            if not visible:
                return None

            payload = {
                "session_id":    session_id,
                "saved_at":      datetime.utcnow().isoformat(),
                "user":          user_name,
                "mode":          "rexxie" if rexxie_active else "rex",
                "message_count": len(visible),
                "messages":      visible,
            }

            raw   = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ct    = _triple_encrypt(raw, self._key)

            ts    = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            fname = f"{ts}_{session_id[:8]}.rext"
            fpath = TRANSCRIPT_DIR / fname
            fpath.write_bytes(ct)
            fpath.chmod(0o600)
            logger.info(f"🔒 Transcript saved: {fname} ({len(ct)} bytes, triple-encrypted)")
            return fpath

        except Exception as e:
            logger.warning(f"Transcript save failed: {e}")
            return None

    def list_transcripts(self) -> List[dict]:
        """
        List all saved transcripts — metadata only (no decryption needed for listing
        since filename encodes timestamp and session ID).
        """
        files = sorted(TRANSCRIPT_DIR.glob("*.rext"), reverse=True)
        result = []
        for f in files:
            stat = f.stat()
            result.append({
                "filename":     f.name,
                "size_bytes":   stat.st_size,
                "modified":     datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "path":         str(f),
            })
        return result

    def read(self, filename: str) -> Optional[dict]:
        """Decrypt and return a transcript by filename."""
        fpath = TRANSCRIPT_DIR / filename
        if not fpath.exists():
            logger.error(f"Transcript not found: {filename}")
            return None
        try:
            ct      = fpath.read_bytes()
            raw     = _triple_decrypt(ct, self._key)
            payload = json.loads(raw.decode("utf-8"))
            return payload
        except Exception as e:
            logger.error(f"Transcript decrypt failed for {filename}: {e}")
            return None

    def format_for_display(self, transcript: dict) -> str:
        """Format a decrypted transcript as readable plain text."""
        lines = [
            f"═══════════════════════════════════════",
            f"  REX Session Transcript",
            f"  Date:    {transcript.get('saved_at', 'unknown')[:16].replace('T', ' ')} UTC",
            f"  Mode:    {'🌸 Rexxie' if transcript.get('mode') == 'rexxie' else '🦖 REX'}",
            f"  Session: {transcript.get('session_id', 'unknown')}",
            f"  Messages:{transcript.get('message_count', 0)}",
            f"═══════════════════════════════════════",
            "",
        ]
        for msg in transcript.get("messages", []):
            role    = msg.get("role", "unknown")
            content = msg.get("content", "")
            speaker = "Kato" if role == "user" else ("Rexxie" if transcript.get("mode") == "rexxie" else "REX")
            lines.append(f"[{speaker}]")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)


# ── Also fix the session cache: encrypt it at rest ────────────────────────────

class EncryptedSessionCache:
    """
    Drop-in replacement for the plaintext .rex_session_cache.json.
    Encrypts the session cache with AES-256-GCM so it's not readable as plaintext.
    Backwards-compatible: reads old plaintext cache files on first load, then re-saves encrypted.
    """
    CACHE_PATH    = Path.home() / "Desktop" / "REX" / ".rex_session_cache.enc"
    LEGACY_PATH   = Path.home() / "Desktop" / "REX" / ".rex_session_cache.json"
    RESUME_WINDOW = 30 * 60  # 30 minutes

    def __init__(self, master_key: Optional[bytes] = None):
        self._key = master_key

    def _get_key(self) -> bytes:
        if self._key:
            return _derive(self._key, "session-cache-aes")
        raise RuntimeError("No master key available for session cache encryption")

    def save(self, messages: list, rexxie_active: bool) -> None:
        """Save session cache, encrypted."""
        try:
            if not self._key:
                return  # Can't encrypt without key — skip silently
            user_msgs = [m for m in messages if m.get("role") != "system"]
            if not user_msgs:
                return
            payload = {
                "saved_at":      datetime.utcnow().isoformat(),
                "rexxie_active": rexxie_active,
                "messages":      user_msgs[-40:],  # Keep last 40 messages
            }
            raw = json.dumps(payload).encode("utf-8")
            ct  = _aes_gcm_encrypt(raw, self._get_key())
            self.CACHE_PATH.write_bytes(ct)
            self.CACHE_PATH.chmod(0o600)
            # Remove old plaintext file if it still exists
            if self.LEGACY_PATH.exists():
                self.LEGACY_PATH.unlink()
        except Exception as e:
            logger.warning(f"Encrypted session cache save failed: {e}")

    def load(self) -> Tuple[Optional[list], bool]:
        """Load session cache. Handles both encrypted and legacy plaintext formats."""
        # Try encrypted cache first
        if self.CACHE_PATH.exists() and self._key:
            try:
                ct      = self.CACHE_PATH.read_bytes()
                raw     = _aes_gcm_decrypt(ct, self._get_key())
                payload = json.loads(raw.decode("utf-8"))
                saved   = datetime.fromisoformat(payload["saved_at"])
                age     = (datetime.utcnow() - saved).total_seconds()
                if age <= self.RESUME_WINDOW:
                    return payload.get("messages", []), payload.get("rexxie_active", False)
                self.CACHE_PATH.unlink()
                return None, False
            except Exception as e:
                logger.warning(f"Encrypted cache load failed: {e}")

        # Fall back to legacy plaintext (migrates it automatically)
        if self.LEGACY_PATH.exists():
            try:
                payload = json.loads(self.LEGACY_PATH.read_text())
                saved   = datetime.fromisoformat(payload["saved_at"])
                age     = (datetime.utcnow() - saved).total_seconds()
                if age <= self.RESUME_WINDOW:
                    msgs    = payload.get("messages", [])
                    active  = payload.get("rexxie_active", False)
                    # Immediately re-save as encrypted, delete plaintext
                    self.save(msgs, active)
                    return msgs, active
                self.LEGACY_PATH.unlink()
            except Exception:
                pass

        return None, False

    def clear(self) -> None:
        """Delete both cache files."""
        for p in (self.CACHE_PATH, self.LEGACY_PATH):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


# ── CLI viewer ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="REX Encrypted Transcript Viewer")
    parser.add_argument("--list",   action="store_true", help="List all saved transcripts")
    parser.add_argument("--read",   metavar="FILENAME",  help="Decrypt and display a transcript")
    parser.add_argument("--export", metavar="FILENAME",  help="Export transcript as plain text file")
    args = parser.parse_args()

    # Load key from keyring or prompt
    master_key = None
    try:
        import keyring
        hex_key = keyring.get_password("rex-sovereign", "rex-master-key") or \
                  keyring.get_password("rex-sovereign", "transcript-key")
        if hex_key:
            master_key = bytes.fromhex(hex_key)
    except Exception:
        pass

    if not master_key:
        key_path = Path.home() / "Desktop" / "REX" / ".rex_key"
        if key_path.exists():
            master_key = bytes.fromhex(key_path.read_text().strip())
        else:
            print("❌ Cannot find REX master key. Run from within REX's Python environment.")
            sys.exit(1)

    store = TranscriptStore(master_key=master_key)

    if args.list:
        transcripts = store.list_transcripts()
        if not transcripts:
            print("No transcripts saved yet.")
        else:
            print(f"\n{'File':<40} {'Size':>10}  {'Saved'}")
            print("─" * 65)
            for t in transcripts:
                print(f"{t['filename']:<40} {t['size_bytes']:>8}B  {t['modified']}")
            print(f"\n{len(transcripts)} transcript(s) — all triple-encrypted at rest.\n")

    elif args.read:
        transcript = store.read(args.read)
        if not transcript:
            print(f"Could not read '{args.read}'. Wrong key or file corrupted.")
            sys.exit(1)
        print(store.format_for_display(transcript))

    elif args.export:
        transcript = store.read(args.export)
        if not transcript:
            print(f"Could not read '{args.export}'.")
            sys.exit(1)
        out_name = args.export.replace(".rext", "_plaintext.txt")
        out_path = TRANSCRIPT_DIR / out_name
        out_path.write_text(store.format_for_display(transcript), encoding="utf-8")
        out_path.chmod(0o600)
        print(f"✅ Exported to: {out_path}")
        print("⚠️  This file is plain text — delete it after review.")

    else:
        parser.print_help()
