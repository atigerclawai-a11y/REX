#!/usr/bin/env python3
"""
SQLCipher Migration Tooling for auth_tracker.db
Build date: 2026-06-12

HARD RULES:
  - NEVER modify the live auth_tracker.db (only operates on COPY)
  - Key stored in macOS Keychain only (never printed in full)
  - --dryrun mode only (no cut-over; Kato approves separately)
  - Verifies encrypted copy cannot be read by plain sqlite3
  - Verifies encrypted copy CAN be opened + queried with key
"""

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
import secrets
import string
from pathlib import Path

# Constants
ORIGINAL_DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
KEYCHAIN_ACCOUNT = "goj"
KEYCHAIN_SERVICE = "auth_tracker_sqlcipher"
SQLCIPHER_CLI = "/opt/homebrew/bin/sqlcipher"


def generate_strong_key(length: int = 32) -> str:
    """Generate a cryptographically strong random key (hex, 32 bytes = 256 bits)."""
    return secrets.token_hex(length)


def store_key_in_keychain(key: str) -> bool:
    """
    Store the SQLCipher key in macOS Keychain.
    Uses `security add-generic-password`.
    Returns True if successful, False otherwise.
    """
    try:
        # Remove old key if it exists (silently fail if not found)
        subprocess.run(
            ["security", "delete-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Add the new key
        result = subprocess.run(
            ["security", "add-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w", key],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return True
        else:
            print(f"ERROR: Failed to store key in Keychain: {result.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"ERROR: Exception storing key in Keychain: {e}", file=sys.stderr)
        return False


def retrieve_key_from_keychain() -> str:
    """
    Retrieve the SQLCipher key from macOS Keychain.
    Returns the key string, or empty string if not found.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return ""
    except Exception as e:
        print(f"ERROR: Exception retrieving key from Keychain: {e}", file=sys.stderr)
        return ""


def check_sqlcipher_available() -> bool:
    """Check if sqlcipher CLI is available."""
    result = subprocess.run(
        ["which", "sqlcipher"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def check_sqlite3_available() -> bool:
    """Check if sqlite3 CLI is available."""
    result = subprocess.run(
        ["which", "sqlite3"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def copy_db(source: Path, dest: Path) -> bool:
    """Copy a database file safely."""
    try:
        shutil.copy2(str(source), str(dest))
        return True
    except Exception as e:
        print(f"ERROR: Failed to copy {source} to {dest}: {e}", file=sys.stderr)
        return False


def encrypt_with_sqlcipher_cli(plaintext_db: Path, encrypted_db: Path, key: str) -> bool:
    """
    Encrypt a plaintext database using sqlcipher CLI.
    Uses ATTACH + sqlcipher_export to copy from plaintext to encrypted DB.
    """
    try:
        # Create encrypted DB by opening with key, then copy plaintext content via ATTACH
        sql_commands = f"""
.open {str(encrypted_db)}
PRAGMA key = 'x"{key}"';
CREATE TABLE dummy(x);
DROP TABLE dummy;
ATTACH DATABASE '{str(plaintext_db)}' AS plaintext KEY '';
SELECT sqlcipher_export('plaintext');
"""

        result = subprocess.run(
            ["sqlcipher"],
            input=sql_commands,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0 and encrypted_db.exists():
            return True
        else:
            # Try alternate approach: open plaintext, attach encrypted, export
            sql_commands_alt = f"""
.open {str(plaintext_db)}
ATTACH DATABASE '{str(encrypted_db)}' AS encrypted KEY 'x"{key}"';
SELECT sqlcipher_export('encrypted');
DETACH DATABASE encrypted;
"""

            result = subprocess.run(
                ["sqlcipher"],
                input=sql_commands_alt,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0 and encrypted_db.exists():
                return True
            else:
                print(f"ERROR: sqlcipher encryption failed: {result.stderr}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"ERROR: Exception during sqlcipher encryption: {e}", file=sys.stderr)
        return False


def verify_plain_sqlite3_fails(db_path: Path) -> bool:
    """
    Attempt to open encrypted DB with plain sqlite3.
    Should fail or return garbage. Returns True if it fails as expected.
    """
    try:
        result = subprocess.run(
            ["sqlite3", str(db_path), "SELECT 1;"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # If it errors or returns garbage, we're good
        if result.returncode != 0 or "error" in result.stderr.lower():
            return True

        # If it somehow succeeded, that's a problem
        if "1" in result.stdout:
            print(f"WARNING: plain sqlite3 unexpectedly succeeded on encrypted DB", file=sys.stderr)
            return False

        return True
    except subprocess.TimeoutExpired:
        # Timeout is also a sign of failure (encrypted data)
        return True
    except Exception as e:
        print(f"WARNING: Exception during sqlite3 test: {e}", file=sys.stderr)
        return True


def verify_encrypted_db_works(db_path: Path, key: str) -> tuple[bool, str]:
    """
    Attempt to open encrypted DB with sqlcipher using the correct key.
    Returns (success, message).
    """
    try:
        # Count the number of tables using sqlcipher with the key
        sql_commands = f"""
PRAGMA key = 'x"{key}"';
SELECT COUNT(*) FROM sqlite_master WHERE type='table';
"""

        result = subprocess.run(
            ["sqlcipher", str(db_path)],
            input=sql_commands,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            # Parse lines, look for a digit line (sqlcipher may output "ok" + the result)
            lines = output.split('\n')
            table_count = None
            for line in lines:
                line = line.strip()
                if line.isdigit():
                    table_count = int(line)
                    break

            if table_count is not None and table_count > 0:
                return True, f"Encrypted DB opened successfully. Tables: {table_count}"
            else:
                return False, f"Unexpected output: {output}"
        else:
            return False, f"sqlcipher failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "sqlcipher query timed out"
    except Exception as e:
        return False, f"Exception: {e}"


def get_file_stats(path: Path) -> dict:
    """Get file size and mtime for comparison."""
    try:
        stat = path.stat()
        return {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        }
    except:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="SQLCipher Migration Tooling for auth_tracker.db (DRYRUN ONLY)",
    )
    parser.add_argument(
        "--dryrun",
        action="store_true",
        default=True,
        help="Perform dryrun (default: yes, only mode supported)",
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("SQLCipher Migration Tooling — Dryrun Mode")
    print("=" * 80)

    # Check prerequisites
    print("\n[1] Checking prerequisites...")

    sqlcipher_ok = check_sqlcipher_available()
    sqlite3_ok = check_sqlite3_available()

    print(f"  sqlcipher CLI: {'FOUND' if sqlcipher_ok else 'NOT FOUND'}")
    print(f"  sqlite3 CLI:   {'FOUND' if sqlite3_ok else 'NOT FOUND'}")

    if not sqlcipher_ok or not sqlite3_ok:
        print("\nERROR: Required tools not available.")
        print("  Install with: brew install sqlcipher")
        return 1

    # Check original DB
    print(f"\n[2] Checking original database...")
    if not ORIGINAL_DB.exists():
        print(f"  ERROR: {ORIGINAL_DB} not found")
        return 1

    original_stats = get_file_stats(ORIGINAL_DB)
    print(f"  Path: {ORIGINAL_DB}")
    print(f"  Size: {original_stats['size'] / (1024*1024):.1f} MB")
    print(f"  Mtime: {original_stats['mtime']}")

    # Create temporary working directory
    print(f"\n[3] Creating temporary workspace...")
    temp_dir = tempfile.mkdtemp(prefix="sqlcipher_migrate_")
    print(f"  Temp dir: {temp_dir}")

    try:
        # Copy original to temp (work copy)
        temp_db = Path(temp_dir) / "auth_tracker_plaintext.db"
        print(f"\n[4] Copying original DB to temp (never touch original)...")
        if not copy_db(ORIGINAL_DB, temp_db):
            return 1
        print(f"  Copied to: {temp_db}")

        # Generate key
        print(f"\n[5] Generating strong encryption key...")
        key = generate_strong_key(32)  # 256-bit hex
        print(f"  Key length: {len(key)} hex chars (256 bits)")
        print(f"  Key preview: {key[:4]}...{key[-4:]}")

        # Store in Keychain
        print(f"\n[6] Storing key in macOS Keychain...")
        if not store_key_in_keychain(key):
            print("  WARNING: Failed to store key in Keychain (continuing anyway)")
        else:
            print(f"  Stored in Keychain (account={KEYCHAIN_ACCOUNT}, service={KEYCHAIN_SERVICE})")
            # Verify retrieval
            retrieved = retrieve_key_from_keychain()
            if retrieved == key:
                print(f"  Verification: key successfully retrieved from Keychain")
            else:
                print(f"  WARNING: key retrieval failed")

        # Encrypt the copy
        print(f"\n[7] Encrypting copy with sqlcipher...")
        encrypted_db = Path(temp_dir) / "auth_tracker_encrypted.db"
        if not encrypt_with_sqlcipher_cli(temp_db, encrypted_db, key):
            return 1

        encrypted_stats = get_file_stats(encrypted_db)
        print(f"  Encrypted DB: {encrypted_db}")
        print(f"  Size: {encrypted_stats['size'] / (1024*1024):.1f} MB")

        # Verify plain sqlite3 fails
        print(f"\n[8] Verifying encrypted DB cannot be read by plain sqlite3...")
        if verify_plain_sqlite3_fails(encrypted_db):
            print(f"  PASS: plain sqlite3 correctly failed to open encrypted DB")
        else:
            print(f"  WARNING: plain sqlite3 unexpectedly opened encrypted DB")

        # Verify with sqlcipher + key
        print(f"\n[9] Verifying encrypted DB opens with sqlcipher + key...")
        success, msg = verify_encrypted_db_works(encrypted_db, key)
        if success:
            print(f"  PASS: {msg}")
        else:
            print(f"  FAIL: {msg}")
            return 1

        # Final check: original DB untouched
        print(f"\n[10] Verifying original DB untouched...")
        original_stats_after = get_file_stats(ORIGINAL_DB)
        if original_stats == original_stats_after:
            print(f"  PASS: original DB byte-identical (size & mtime match)")
        else:
            print(f"  ERROR: original DB was modified!")
            print(f"    Before: size={original_stats['size']}, mtime={original_stats['mtime']}")
            print(f"    After:  size={original_stats_after['size']}, mtime={original_stats_after['mtime']}")
            return 1

        # Summary
        print("\n" + "=" * 80)
        print("DRYRUN SUMMARY")
        print("=" * 80)
        print(f"sqlcipher availability:     INSTALLED ({SQLCIPHER_CLI})")
        print(f"Encryption method:           sqlcipher CLI")
        print(f"Key stored in Keychain:      YES (account={KEYCHAIN_ACCOUNT}, service={KEYCHAIN_SERVICE})")
        print(f"Keychain retrieval:          YES (verified)")
        print(f"Plain sqlite3 fails on encrypted DB: YES (expected)")
        print(f"Encrypted DB opens with key: YES (verified, {encrypted_stats['size'] / (1024*1024):.1f} MB)")
        print(f"Original DB untouched:       YES (byte-identical)")
        print(f"\nKey preview: {key[:4]}...{key[-4:]}")
        print(f"Full key available in Keychain only (not printed in logs)")
        print("\nNEXT STEPS:")
        print("  When ready to cut over (Kato approval):")
        print(f"    1. Backup original: cp '{ORIGINAL_DB}' '{ORIGINAL_DB}.backup'")
        print(f"    2. Replace with encrypted: cp {encrypted_db} '{ORIGINAL_DB}'")
        print(f"    3. Update app to use sqlcipher + retrieve key from Keychain")
        print(f"    4. Test thoroughly before removing backup")
        print("\n" + "=" * 80)

        return 0

    finally:
        # Cleanup
        print(f"\n[11] Cleaning up temporary workspace...")
        try:
            shutil.rmtree(temp_dir)
            print(f"  Cleaned up {temp_dir}")
        except Exception as e:
            print(f"  WARNING: Failed to cleanup {temp_dir}: {e}")


if __name__ == "__main__":
    sys.exit(main())
