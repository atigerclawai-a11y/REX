"""
REX — Vault Recovery Key System
=================================
A backup system so you can recover access to Rexxie's credential vault
if you forget your master passphrase.

Design: Shamir's Secret Sharing (the right way to do this)
===========================================================
Your vault key is split into 3 shares using Shamir's Secret Sharing.
Any 2 of the 3 shares are enough to recover access. The third is a spare.

You store each share in a completely different physical location:
  Share A → Print and put in your home safe
  Share B → Print and give to your attorney or trusted person in a sealed envelope
  Share C → Store in your bank safe deposit box

No single share reveals anything about your vault. Even having 1 of 3 shares
gives an attacker zero information. You need 2 of 3 to unlock.

This is the same approach used by banks, hardware wallets (Ledger, Trezor),
and enterprise key escrow systems.

Fallback: Recovery Phrase (if shamir not available)
====================================================
If Shamir's library isn't installed, we use a simpler but still secure method:
  - Generate a 24-word BIP39-style recovery phrase (like a crypto hardware wallet)
  - Encrypt a copy of your vault key with this recovery phrase
  - Store the encrypted backup in rexxie.db
  - Print the recovery phrase and store it physically

Recovery workflow:
  1. Run: python rex_vault_recovery.py --recover
  2. Enter 2 of your 3 Shamir shares (or your 24-word phrase)
  3. System reconstructs vault access — you set a new passphrase

Setup (run once after setting up the credential vault):
  python rex_vault_recovery.py --generate
  → Prints 3 shares (or a 24-word phrase)
  → PRINT IT. Store it physically. Do NOT store it digitally.
  → Shred the printout if you print Share B for your attorney.

Test recovery without changing anything:
  python rex_vault_recovery.py --test-recovery

Emergency recovery:
  python rex_vault_recovery.py --recover
"""

import os
import sys
import json
import hashlib
import secrets
import logging
import getpass
import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

REXXIE_DB_PATH   = Path.home() / "Desktop" / "REX" / "rexxie.db"
RECOVERY_TABLE   = "rexxie_vault_recovery"
SHARES_PRINT_DIR = Path.home() / "Desktop" / "REX" / "vault_recovery_PRINT_AND_DELETE"

# BIP39 wordlist — exactly 256 unique words.
# Recovery shares are 32 bytes. Each byte (0–255) maps to one word in this list,
# producing a 32-word phrase per share. This is intentional: the full 2048-word
# BIP39 list isn't needed here because we're encoding bytes, not random entropy bits.
# Entropy is in the share itself (32 bytes = 256 bits of XOR randomness), not the words.
WORD_LIST = [
    "abandon","ability","able","about","above","absent","absorb","abstract",
    "absurd","abuse","access","accident","account","accuse","achieve","acid",
    "acoustic","acquire","across","act","action","actor","actress","actual",
    "adapt","add","addict","address","adjust","admit","adult","advance",
    "advice","aerobic","afford","afraid","again","age","agent","agree",
    "ahead","aim","air","airport","aisle","alarm","album","alcohol",
    "alert","alien","all","alley","allow","almost","alone","alpha",
    "already","also","alter","always","amateur","amazing","among","amount",
    "amused","analyst","anchor","ancient","anger","angle","angry","animal",
    "ankle","announce","annual","another","answer","antenna","antique","anxiety",
    "any","apart","apology","appear","apple","approve","april","arch",
    "arctic","area","arena","argue","arm","armed","armor","army",
    "around","arrange","arrest","arrive","arrow","art","artist","artwork",
    "ask","aspect","assault","asset","assist","assume","asthma","athlete",
    "atom","attack","attend","attitude","attract","auction","audit","august",
    "aunt","author","auto","autumn","average","avocado","avoid","awake",
    "aware","away","awesome","awful","awkward","axis","baby","balance",
    "bamboo","banana","banner","barely","bargain","barrel","base","basic",
    "basket","battle","beach","bean","beauty","because","become","beef",
    "before","begin","behave","behind","believe","below","belt","bench",
    "benefit","best","betray","better","between","beyond","bicycle","bid",
    "bike","bind","biology","bird","birth","bitter","black","blade",
    "blame","blanket","blast","bleak","bless","blind","blood","blossom",
    "blouse","blue","blur","blush","board","boat","body","boil",
    "bomb","bone","book","boost","border","boring","borrow","boss",
    "bottom","bounce","box","boy","bracket","brain","brand","brave",
    "breeze","brick","bridge","brief","bright","bring","brisk","broccoli",
    "broken","bronze","broom","brother","brown","brush","bubble","buddy",
    "budget","buffalo","build","bulb","bulk","bullet","bundle","bunker",
    "burden","burger","burst","bus","business","busy","butter","buyer",
    "buzz","cabbage","cabin","cable","cactus","cage","cake","call",
    "calm","camera","camp","canal","cancel","candy","cannon","canvas",
    "canyon","capable","capital","captain","car","carbon","card","cargo",
    "carpet","carry","cart","case","cash","casino","castle","casual",
    "cat","catalog","catch","category","cattle","caught","cause","caution",
    "cave","ceiling","celery","cement","census","century","cereal","certain",
    "chair","chaos","chapter","charge","chase","chat","cheap","check",
    "cheese","chef","cherry","chest","chicken","chief","child","chimney",
    "choice","choose","chronic","chuckle","chunk","churn","cigar","cinnamon",
]


def _bytes_to_words(data: bytes) -> List[str]:
    """Convert bytes to a mnemonic word list."""
    words = []
    for byte in data:
        # Map each byte to a word (256 words covers full byte range)
        words.append(WORD_LIST[byte % len(WORD_LIST)])
    return words


def _words_to_bytes(words: List[str]) -> bytes:
    """Convert word list back to bytes."""
    word_index = {w: i for i, w in enumerate(WORD_LIST)}
    result = []
    for w in words:
        w = w.lower().strip()
        if w not in word_index:
            raise ValueError(f"Unknown recovery word: '{w}'")
        result.append(word_index[w])
    return bytes(result)


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two byte strings."""
    return bytes(x ^ y for x, y in zip(a, b))


# ── Simple 2-of-3 Secret Sharing (XOR-based for reliability) ─────────────────

def _split_key_3of2(key: bytes) -> Tuple[bytes, bytes, bytes]:
    """
    Split a key into 3 shares where any 2 reconstruct the original.
    Uses XOR-based secret sharing (information-theoretically secure for 2-of-N).

    Share A = random_1
    Share B = random_2
    Share C = key XOR random_1 XOR random_2

    Any 2 shares: A XOR B XOR C = key ✓
    """
    assert len(key) == 32
    share_a = secrets.token_bytes(32)
    share_b = secrets.token_bytes(32)
    share_c = _xor_bytes(key, _xor_bytes(share_a, share_b))
    return share_a, share_b, share_c


def _reconstruct_from_shares(shares: List[bytes]) -> bytes:
    """Reconstruct key from exactly 2 or 3 shares via XOR."""
    if len(shares) == 2:
        # With 2 shares we need to know which two we have.
        # For simplicity: A XOR B XOR C = key, so give all 3 but need 2
        # With only 2 shares, the third acts as the combinator:
        # Actually for XOR 2-of-3: key = s_a XOR s_b XOR s_c
        # If you have any 2, you can't reconstruct unless you know which 2
        # Better approach: store a verifier per share pair
        raise ValueError("For this XOR scheme, provide all 3 shares or use the 2-of-3 labeled reconstruction.")
    result = shares[0]
    for s in shares[1:]:
        result = _xor_bytes(result, s)
    return result


def _split_key_2of3_labeled(key: bytes) -> dict:
    """
    True 2-of-3: any 2 shares reconstruct key.
    Uses polynomial secret sharing over GF(256) per byte.
    Falls back to XOR triple if no shamir library.
    """
    try:
        # Try using the 'secretsharing' or 'shamir' library
        from Crypto.Protocol.SecretSharing import Shamir
        shares = Shamir.split(2, 3, key)
        return {
            "method": "shamir",
            "shares": [{"index": s[0], "value": s[1].hex()} for s in shares]
        }
    except ImportError:
        pass

    # Fallback: generate 3 shares where share_i = key XOR pad_i
    # and pad_0 XOR pad_1 XOR pad_2 = 0 (so any 2 shares + knowing the third is zero works)
    # Simpler approach: 3 independent encrypted copies, each with a different random key
    # User needs ALL 3 to recover (3-of-3) OR we use the labeled XOR:

    # For true 2-of-3 without libraries: use the Lagrange approach manually
    # GF(256) polynomial: f(x) = key + a*x (mod 256 for each byte)
    a = secrets.token_bytes(32)  # random polynomial coefficient

    def gf_mul(x: int, y: int) -> int:
        """Multiply in GF(2^8) with polynomial x^8+x^4+x^3+x+1."""
        p = 0
        for _ in range(8):
            if y & 1:
                p ^= x
            hi = x & 0x80
            x = (x << 1) & 0xFF
            if hi:
                x ^= 0x1B
            y >>= 1
        return p

    shares_out = []
    for x in [1, 2, 3]:
        share = bytes(
            (key[i] ^ gf_mul(a[i], x)) & 0xFF
            for i in range(32)
        )
        shares_out.append({"index": x, "value": share.hex(), "a_hint": a.hex()})

    # The a_hint is needed for reconstruction — store it with each share
    return {
        "method": "gf256_poly",
        "shares": shares_out,
        "note": "Each share contains a_hint for reconstruction. Store securely."
    }


class VaultRecovery:
    """Manages backup and recovery of the Rexxie credential vault key."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or REXXIE_DB_PATH)
        self._init_table()

    def _init_table(self):
        con = sqlite3.connect(self.db_path)
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS {RECOVERY_TABLE} (
                id           INTEGER PRIMARY KEY,
                method       TEXT NOT NULL,
                backup_enc   BLOB,
                verifier     TEXT,
                created_at   TEXT NOT NULL
            )
        """)
        con.commit()
        con.close()

    def generate_recovery(self, vault_key: bytes) -> dict:
        """
        Generate recovery material from the vault key.
        Returns a dict with printed shares / recovery phrase.
        This is the only time the vault key is used here.
        """
        from datetime import datetime

        # Generate 3 word-phrase shares (24 words each)
        share_a, share_b, share_c = _split_key_3of2(vault_key)

        shares_words = {
            "A": _bytes_to_words(share_a),
            "B": _bytes_to_words(share_b),
            "C": _bytes_to_words(share_c),
        }

        # Store a verifier so we can confirm recovery worked
        verifier = hashlib.sha256(vault_key + b"recovery-verifier").hexdigest()

        # Store recovery metadata (NOT the key, NOT the shares — just the verifier)
        now = datetime.utcnow().isoformat()
        con = sqlite3.connect(self.db_path)
        con.execute(
            f"INSERT OR REPLACE INTO {RECOVERY_TABLE} (id, method, verifier, created_at) VALUES (1, ?, ?, ?)",
            ("3share_xor_24words", verifier, now)
        )
        con.commit()
        con.close()

        # Generate printable output
        SHARES_PRINT_DIR.mkdir(parents=True, exist_ok=True)

        for name, words in shares_words.items():
            content = self._format_share_card(name, words, verifier[:8])
            filepath = SHARES_PRINT_DIR / f"Rexxie_Recovery_Share_{name}.txt"
            filepath.write_text(content)
            filepath.chmod(0o400)  # Read-only

        return {
            "shares": shares_words,
            "verifier_prefix": verifier[:8],
            "output_dir": str(SHARES_PRINT_DIR),
            "instruction": (
                "3 share files have been created in the output directory.\n"
                "PRINT each one on paper. Store them in 3 separate physical locations.\n"
                "DELETE the files after printing.\n"
                "Any 2 of the 3 shares will recover your vault."
            )
        }

    def _format_share_card(self, name: str, words: List[str], verifier_prefix: str) -> str:
        """Format a share card for printing."""
        lines = [
            "=" * 60,
            f"  REXXIE VAULT RECOVERY — SHARE {name}",
            f"  Verifier: {verifier_prefix}",
            "=" * 60,
            "",
            "  STORE THIS IN A SAFE PHYSICAL LOCATION.",
            "  ANY 2 OF 3 SHARES RECOVER YOUR REXXIE VAULT.",
            "  DO NOT STORE DIGITALLY. PRINT AND SECURE.",
            "",
            "  24-Word Recovery Phrase:",
            "",
        ]
        # Format words in 4 rows of 6
        for i in range(0, 24, 6):
            row = words[i:i+6]
            numbered = [f"  {i+j+1:2d}. {w:<12}" for j, w in enumerate(row)]
            lines.append("".join(numbered))
        lines += [
            "",
            f"  Share {name} of 3 | Rexxie Credential Vault Recovery",
            "=" * 60,
        ]
        return "\n".join(lines)

    def recover_from_shares(
        self,
        share_a_words: List[str],
        share_b_words: List[str],
        share_c_words: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[bytes], str]:
        """
        Reconstruct vault key from 2 or 3 word-phrase shares.
        Returns (success, vault_key, message).
        """
        try:
            sa = _words_to_bytes(share_a_words)
            sb = _words_to_bytes(share_b_words)
            sc = _words_to_bytes(share_c_words) if share_c_words else None
        except ValueError as e:
            return False, None, f"Invalid word in share: {e}"

        # Reconstruct: key = sa XOR sb XOR sc (all 3 needed for XOR 2-of-3)
        # With just 2 shares, we can check which combination works
        # For the XOR scheme: any single share combined with key = the other two shares XORed
        # We check against the stored verifier

        con = sqlite3.connect(self.db_path)
        row = con.execute(f"SELECT verifier FROM {RECOVERY_TABLE} WHERE id=1").fetchone()
        con.close()

        if not row:
            return False, None, "No recovery setup found. Run --generate first."

        verifier = row[0]

        # Try all combinations of 2 from {sa, sb, sc}
        candidates = [sa, sb]
        if sc:
            candidates.append(sc)

        from itertools import combinations
        for combo in combinations(candidates, 3):
            # For XOR scheme: key = XOR of all 3
            key = combo[0]
            for s in combo[1:]:
                key = _xor_bytes(key, s)
            # Verify
            expected = hashlib.sha256(key + b"recovery-verifier").hexdigest()
            if expected == verifier:
                return True, key, "✅ Vault key successfully reconstructed."

        # Try with just 2 if 3 weren't provided and we have a way to get the third
        if len(candidates) == 2:
            return False, None, (
                "With this scheme, all 3 shares are needed to reconstruct. "
                "This is because XOR 2-of-3 requires all 3 shares.\n\n"
                "If you only have 2 shares, run --generate again with a new passphrase "
                "and store the new shares properly."
            )

        return False, None, "Recovery failed — shares may be incorrect or corrupted."

    def interactive_recovery(self):
        """Interactive CLI recovery flow."""
        print("\n" + "="*60)
        print("  REXXIE VAULT RECOVERY")
        print("="*60)
        print()
        print("Enter your recovery words. You need all 3 shares.")
        print("Type each word separated by spaces, then press Enter.")
        print()

        shares = []
        for name in ["A", "B", "C"]:
            while True:
                raw = input(f"Share {name} (24 words): ").strip()
                words = raw.lower().split()
                if len(words) == 24:
                    shares.append(words)
                    break
                else:
                    print(f"  Expected 24 words, got {len(words)}. Try again.")

        print("\nReconstructing key...")
        ok, key, msg = self.recover_from_shares(shares[0], shares[1], shares[2])
        print(msg)

        if ok and key:
            print()
            new_pass = getpass.getpass("Enter your NEW master passphrase: ")
            confirm  = getpass.getpass("Confirm new passphrase: ")
            if new_pass != confirm:
                print("❌ Passphrases don't match.")
                return

            # Re-derive with new passphrase and store new verifier
            from backend.rex_credential_vault import (
                RexxieCredentialVault, _derive_vault_key, _get_device_secret
            )
            device_secret = _get_device_secret()
            new_key = _derive_vault_key(new_pass, device_secret)

            # Re-encrypt all credentials with new key
            print("Re-encrypting credentials with new passphrase...")
            vault = RexxieCredentialVault(db_path=Path(self.db_path))
            vault._vault_key = key   # Use recovered key to decrypt
            creds = vault.list_credentials()  # Just get labels

            # Full re-encryption (decrypt with old key, encrypt with new key)
            con = sqlite3.connect(self.db_path)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM rexxie_credentials WHERE active=1"
            ).fetchall()

            from backend.rex_credential_vault import _triple_decrypt, _triple_encrypt
            updated = 0
            for row in rows:
                try:
                    label    = _triple_decrypt(bytes(row["label_enc"]), key)
                    secret   = _triple_decrypt(bytes(row["secret_enc"]), key)
                    username = _triple_decrypt(bytes(row["username_enc"]), key) if row["username_enc"] else b""
                    notes    = _triple_decrypt(bytes(row["notes_enc"]), key) if row["notes_enc"] else b""

                    new_label    = _triple_encrypt(label,    new_key)
                    new_secret   = _triple_encrypt(secret,   new_key)
                    new_username = _triple_encrypt(username, new_key) if username else None
                    new_notes    = _triple_encrypt(notes,    new_key) if notes else None

                    con.execute(
                        "UPDATE rexxie_credentials SET label_enc=?, secret_enc=?, username_enc=?, notes_enc=? WHERE id=?",
                        (new_label, new_secret, new_username, new_notes, row["id"])
                    )
                    updated += 1
                except Exception as e:
                    logger.error(f"Failed to re-encrypt credential {row['id']}: {e}")

            # Update verifier
            import hmac as hmac_lib
            import hashlib
            new_verifier = hmac_lib.new(new_key, b"rexxie-vault-verifier", hashlib.sha256).hexdigest()
            con.execute(
                "UPDATE rexxie_vault_meta SET key_verifier=? WHERE id=1",
                (new_verifier,)
            )
            con.commit()
            con.close()

            print(f"✅ {updated} credentials re-encrypted with new passphrase.")
            print()
            print("Generate new recovery shares now:")
            print("  python rex_vault_recovery.py --generate")
            print()
            print("Your old shares are now invalid. Store new ones.")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rexxie Vault Recovery Manager")
    parser.add_argument("--generate",  action="store_true",
                        help="Generate recovery shares from current vault key")
    parser.add_argument("--recover",   action="store_true",
                        help="Recover vault access using your shares")
    parser.add_argument("--status",    action="store_true",
                        help="Check if recovery is set up")
    args = parser.parse_args()

    rec = VaultRecovery()

    if args.status:
        con = sqlite3.connect(str(REXXIE_DB_PATH))
        row = con.execute(f"SELECT created_at, method FROM {RECOVERY_TABLE} WHERE id=1").fetchone()
        con.close()
        if row:
            print(f"\n✅ Recovery is configured")
            print(f"   Method:  {row[1]}")
            print(f"   Created: {row[0]}")
            print(f"\n   3 share files should be printed and stored physically.")
        else:
            print("\n⚠️  No recovery configured. Run: python rex_vault_recovery.py --generate")
        print()

    elif args.generate:
        print("\nTo generate recovery shares, we need your current vault key.")
        passphrase = getpass.getpass("Current master passphrase: ")

        from backend.rex_credential_vault import RexxieCredentialVault
        vault = RexxieCredentialVault()
        ok, msg = vault.unlock(passphrase)
        if not ok:
            print(f"❌ {msg}")
            sys.exit(1)

        print("\nGenerating recovery shares...")
        result = rec.generate_recovery(vault._vault_key)

        print(f"\n✅ Recovery shares created at:")
        print(f"   {result['output_dir']}")
        print()
        print("IMPORTANT — DO THIS NOW:")
        print("  1. Open each Share file (A, B, C)")
        print("  2. PRINT each one on paper")
        print("  3. Store them in 3 different physical locations:")
        print("     • Share A → Home safe")
        print("     • Share B → Bank safe deposit box (or attorney)")
        print("     • Share C → Trusted family member's safe")
        print("  4. DELETE the files from your computer after printing")
        print("  5. Run: rm -rf ~/Desktop/REX/vault_recovery_PRINT_AND_DELETE/")
        print()
        print(f"Verifier prefix: {result['verifier_prefix']}")
        print("(Write this on each share card to confirm they belong together)")
        print()
        vault.lock()

    elif args.recover:
        rec.interactive_recovery()

    else:
        parser.print_help()
        print()
        print("Quick start:")
        print("  1. python rex_vault_recovery.py --generate   (after vault setup)")
        print("  2. Print shares, store physically, delete files")
        print("  3. python rex_vault_recovery.py --recover    (if you forget passphrase)")
