#!/usr/bin/env python3
"""
REX VAULT — Encrypted Credential Store
========================================
AES-256-GCM authenticated encryption. Passphrase in macOS Keychain.
Vault lives locally + syncs to /Volumes/cartoons/REX_Vault/ automatically.

Usage:
  python3 rex_vault.py --setup          First-time setup (creates passphrase)
  python3 rex_vault.py add              Add a new entry
  python3 rex_vault.py list             List all entries (names only)
  python3 rex_vault.py get  <name>      Show an entry (passwords shown for 15s)
  python3 rex_vault.py find <keyword>   Search entries
  python3 rex_vault.py edit <name>      Edit an entry
  python3 rex_vault.py delete <name>    Delete an entry
  python3 rex_vault.py sync             Copy vault to cartoons drive
  python3 rex_vault.py status           Show vault stats
  python3 rex_vault.py change-pass      Change vault passphrase

File format: 16-byte salt | 12-byte nonce | AES-256-GCM ciphertext
Key derivation: PBKDF2-SHA256, 600,000 iterations (NIST 2024 recommendation)
"""

import sys
import os
import json
import uuid
import shutil
import hashlib
import getpass
import subprocess
import threading
import time
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Crypto ────────────────────────────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    sys.exit("Missing: pip install cryptography --break-system-packages")

# ── Config ────────────────────────────────────────────────────────────────────
REX_DIR     = Path(__file__).parent
VAULT_FILE  = REX_DIR / "rex_vault.enc"
DRIVE_DIR   = Path("/Volumes/cartoons/REX_Vault")
DRIVE_VAULT = DRIVE_DIR / "rex_vault.enc"
LOG_FILE    = REX_DIR / "logs" / "vault_access.log"

KC_SERVICE  = "rex-sovereign-vault"
KC_ACCOUNT  = "rex-vault-key"

CATEGORIES  = ["mac", "email", "web", "api-key", "bank", "phone",
                "work", "drive", "social", "other"]

# ── Colours ───────────────────────────────────────────────────────────────────
B  = '\033[1m';    DIM = '\033[2m'
GR = '\033[0;32m'; YL  = '\033[1;33m'
RD = '\033[0;31m'; CY  = '\033[0;36m'
BL = '\033[0;34m'; NC  = '\033[0m'

def ok(s):   print(f"{GR}  ✅ {s}{NC}")
def warn(s): print(f"{YL}  ⚠️  {s}{NC}")
def err(s):  print(f"{RD}  ❌ {s}{NC}")
def hdr(s):  print(f"\n{BL}{B}{s}{NC}\n")

# ── Keychain (file-backed — macOS security -w hangs, so we use a local file) ──
KC_FILE = Path.home() / ".rex" / "rex_vault.pass"

def _kc_get() -> str:
    """Get vault passphrase from ~/.rex/rex_vault.pass (chmod 600).
    macOS `security -w` triggers a GUI auth prompt that hangs — this avoids it entirely.
    Falls back to interactive prompt if file is missing."""
    try:
        if KC_FILE.exists():
            pp = KC_FILE.read_text().strip()
            if pp:
                return pp
    except Exception:
        pass
    return ""

def _kc_has() -> bool:
    """Quick check if passphrase is stored without returning it."""
    return KC_FILE.exists() and len(KC_FILE.read_text().strip()) > 0

def _kc_set(passphrase: str):
    """Store vault passphrase to ~/.rex/rex_vault.pass (chmod 600).
    Avoids macOS security -w which hangs."""
    KC_FILE.parent.mkdir(parents=True, exist_ok=True)
    KC_FILE.write_text(passphrase + "\n")
    KC_FILE.chmod(0o600)

def _kc_delete():
    """Remove the passphrase file."""
    try:
        KC_FILE.unlink(missing_ok=True)
    except Exception:
        pass

# ── Crypto functions ──────────────────────────────────────────────────────────

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """PBKDF2-SHA256, 600,000 iterations → 32-byte AES-256 key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return kdf.derive(passphrase.encode("utf-8"))

def _encrypt(data: dict, passphrase: str) -> bytes:
    """Encrypt vault dict → bytes. Format: salt(16) | nonce(12) | ciphertext."""
    salt  = os.urandom(16)
    nonce = os.urandom(12)
    key   = _derive_key(passphrase, salt)
    ct    = AESGCM(key).encrypt(nonce, json.dumps(data).encode("utf-8"), None)
    return salt + nonce + ct

def _decrypt(payload: bytes, passphrase: str) -> dict:
    """Decrypt bytes → vault dict. Raises ValueError on wrong passphrase."""
    if len(payload) < 28:
        raise ValueError("Vault file is too small — possibly corrupt.")
    salt  = payload[:16]
    nonce = payload[16:28]
    ct    = payload[28:]
    key   = _derive_key(passphrase, salt)
    try:
        raw = AESGCM(key).decrypt(nonce, ct, None)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("Wrong passphrase or vault is corrupt.")

# ── Vault load / save ─────────────────────────────────────────────────────────

def _get_passphrase(prompt_if_missing=True) -> str:
    pp = _kc_get()
    if not pp and prompt_if_missing:
        pp = getpass.getpass("  Vault passphrase: ")
    return pp

def load_vault(passphrase: str) -> dict:
    if not VAULT_FILE.exists():
        return {"entries": [], "created": datetime.now().isoformat()}
    payload = VAULT_FILE.read_bytes()
    return _decrypt(payload, passphrase)

def save_vault(vault: dict, passphrase: str):
    vault["updated"] = datetime.now().isoformat()
    encrypted = _encrypt(vault, passphrase)
    VAULT_FILE.write_bytes(encrypted)
    # Verify the write
    _decrypt(VAULT_FILE.read_bytes(), passphrase)

def _log(action: str, entry_name: str = ""):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    user = os.environ.get("USER", "unknown")
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} | {user} | {action}{' | ' + entry_name if entry_name else ''}\n")

# ── Entry helpers ─────────────────────────────────────────────────────────────

def _find_entry(vault: dict, name: str) -> Optional[dict]:
    name_lower = name.lower()
    for e in vault["entries"]:
        if e["name"].lower() == name_lower:
            return e
    # Fuzzy match
    matches = [e for e in vault["entries"] if name_lower in e["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"\n  Multiple matches for '{name}':")
        for i, m in enumerate(matches, 1):
            print(f"    {i}) {m['name']}  [{m['category']}]")
        choice = input("\n  Select number: ").strip()
        try:
            return matches[int(choice) - 1]
        except (ValueError, IndexError):
            return None
    return None

def _prompt_entry(existing: dict = None) -> dict:
    """Interactive prompt to create or edit an entry. Returns entry dict."""
    e = existing.copy() if existing else {
        "id": str(uuid.uuid4()),
        "created": datetime.now().isoformat(),
    }

    def ask(label, key, secret=False, choices=None):
        current = e.get(key, "")
        hint = f" [{current}]" if current and not secret else ""
        if choices:
            print(f"  {label} options: {', '.join(choices)}")
        prompt_str = f"  {label}{hint}: "
        if secret:
            val = getpass.getpass(prompt_str)
        else:
            val = input(prompt_str).strip()
        if val:
            e[key] = val
        elif not current:
            e[key] = ""

    print()
    ask("Name (e.g. Gmail, Mac Mini login)", "name")
    ask("Category", "category", choices=CATEGORIES)
    ask("Username / email", "username")
    ask("Password", "password", secret=True)
    ask("URL or device (optional)", "url")
    ask("Notes (optional)", "notes")

    e["updated"] = datetime.now().isoformat()
    return e

def _obscure(password: str) -> str:
    """Show first 2 + last 1 chars, rest as *."""
    if len(password) <= 3:
        return "*" * len(password)
    return password[:2] + "*" * (len(password) - 3) + password[-1]

def _show_entry(e: dict, reveal: bool = False):
    """Print a vault entry. If reveal=True, show full password for 15 seconds."""
    cat_color = {
        "mac": CY, "email": BL, "web": GR, "api-key": YL,
        "bank": RD, "phone": GR, "work": BL,
    }.get(e.get("category", "other"), NC)

    print(f"\n  {B}{e['name']}{NC}  {cat_color}[{e.get('category','?')}]{NC}")
    print(f"  {'─'*50}")
    print(f"  Username  : {e.get('username') or DIM+'(none)'+NC}")

    if reveal:
        pw = e.get('password', '')
        print(f"  Password  : {B}{YL}{pw}{NC}")
        print(f"\n  {YL}⚠️  Password visible — clearing in 15 seconds...{NC}")
    else:
        print(f"  Password  : {_obscure(e.get('password', ''))}  {DIM}(run 'get' to reveal){NC}")

    if e.get("url"):
        print(f"  URL/Device: {e['url']}")
    if e.get("notes"):
        print(f"  Notes     : {e['notes']}")
    print(f"  {DIM}Created: {e.get('created','?')[:10]}  |  Updated: {e.get('updated','?')[:10]}  |  ID: {e.get('id','?')[:8]}...{NC}")

    if reveal:
        # Clear password from terminal after 15 seconds
        def _clear():
            time.sleep(15)
            # Move cursor up and overwrite the password line
            sys.stdout.write("\033[4A\033[2K")  # up 4 lines, clear line
            sys.stdout.write(f"  Password  : {'*' * len(pw)}  {DIM}(cleared){NC}\n")
            sys.stdout.flush()
        threading.Thread(target=_clear, daemon=True).start()

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_setup():
    hdr("REX VAULT — Setup")
    print("  Stores your vault passphrase in ~/.rex/rex_vault.pass (chmod 600).")
    print("  Write it down and keep it somewhere safe (separate from this Mac).")
    print("  You will need it to open the vault on a different device.\n")

    existing = _kc_get()
    if existing:
        print(f"  {YL}A vault passphrase already exists.{NC}")
        r = input("  Replace it? This will re-encrypt the vault. [y/N] ").strip().lower()
        if r != "y":
            print("  Keeping existing passphrase.")
            return

    pp1 = getpass.getpass("  Create vault passphrase (min 16 chars): ")
    if len(pp1) < 16:
        err("Too short — minimum 16 characters.")
        return
    pp2 = getpass.getpass("  Confirm passphrase: ")
    if pp1 != pp2:
        err("Passphrases don't match.")
        return

    if existing:
        # Re-encrypt vault with new passphrase
        try:
            vault = load_vault(existing)
            save_vault(vault, pp1)
            ok("Vault re-encrypted with new passphrase")
        except Exception as ex:
            err(f"Could not re-encrypt vault: {ex}")
            return

    _kc_set(pp1)
    ok("Passphrase stored in ~/.rex/rex_vault.pass")

    # Create vault dirs
    VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    DRIVE_DIR.mkdir(parents=True, exist_ok=True) if DRIVE_DIR.parent.exists() else None

    # Create empty vault if needed
    if not VAULT_FILE.exists():
        save_vault({"entries": [], "created": datetime.now().isoformat()}, pp1)
        ok(f"Empty vault created: {VAULT_FILE}")

    print(f"\n  {GR}{B}Setup complete.{NC}")
    print(f"  Add your first entry:  {B}python3 rex_vault.py add{NC}\n")
    _log("SETUP")


def cmd_add():
    pp = _get_passphrase()
    if not pp:
        err("No passphrase. Run: python3 rex_vault.py --setup")
        return
    try:
        vault = load_vault(pp)
    except ValueError as ex:
        err(str(ex)); return

    hdr("ADD NEW ENTRY")
    entry = _prompt_entry()

    if not entry.get("name"):
        err("Name is required.")
        return

    # Check for duplicate
    if _find_entry(vault, entry["name"]):
        r = input(f"\n  '{entry['name']}' already exists. Overwrite? [y/N] ").strip().lower()
        if r != "y":
            return
        vault["entries"] = [e for e in vault["entries"] if e["name"].lower() != entry["name"].lower()]

    vault["entries"].append(entry)
    save_vault(vault, pp)
    _log("ADD", entry["name"])
    ok(f"'{entry['name']}' saved to vault ({len(vault['entries'])} entries total)")
    cmd_sync(silent=True)


def cmd_list():
    pp = _get_passphrase()
    if not pp:
        err("No passphrase. Run: python3 rex_vault.py --setup"); return
    try:
        vault = load_vault(pp)
    except ValueError as ex:
        err(str(ex)); return

    entries = vault.get("entries", [])
    if not entries:
        print("\n  Vault is empty. Add entries with: python3 rex_vault.py add\n")
        return

    hdr(f"VAULT — {len(entries)} entries")

    # Group by category
    by_cat = {}
    for e in sorted(entries, key=lambda x: (x.get("category",""), x.get("name",""))):
        cat = e.get("category", "other")
        by_cat.setdefault(cat, []).append(e)

    for cat, items in sorted(by_cat.items()):
        print(f"  {CY}{B}{cat.upper()}{NC}")
        for e in items:
            user = e.get("username", "")
            url  = e.get("url", "")
            detail = f"  {DIM}{user}{NC}" if user else ""
            detail += f"  {DIM}{url}{NC}" if url and not user else ""
            print(f"    • {B}{e['name']}{NC}{detail}")
        print()

    _log("LIST")


def cmd_get(name: str):
    if not name:
        name = input("  Entry name: ").strip()
    pp = _get_passphrase()
    if not pp:
        err("No passphrase."); return
    try:
        vault = load_vault(pp)
    except ValueError as ex:
        err(str(ex)); return

    entry = _find_entry(vault, name)
    if not entry:
        err(f"No entry found for '{name}'")
        return

    _show_entry(entry, reveal=True)
    _log("GET", entry["name"])
    time.sleep(16)  # Wait for auto-clear


def cmd_find(keyword: str):
    if not keyword:
        keyword = input("  Search: ").strip()
    pp = _get_passphrase()
    if not pp:
        err("No passphrase."); return
    try:
        vault = load_vault(pp)
    except ValueError as ex:
        err(str(ex)); return

    kw = keyword.lower()
    results = [
        e for e in vault["entries"]
        if kw in e.get("name","").lower()
        or kw in e.get("username","").lower()
        or kw in e.get("url","").lower()
        or kw in e.get("notes","").lower()
        or kw in e.get("category","").lower()
    ]

    if not results:
        print(f"\n  No results for '{keyword}'\n")
        return

    hdr(f"SEARCH: '{keyword}' — {len(results)} result(s)")
    for e in results:
        _show_entry(e, reveal=False)
    _log("FIND", keyword)


def cmd_edit(name: str):
    if not name:
        name = input("  Entry name to edit: ").strip()
    pp = _get_passphrase()
    if not pp:
        err("No passphrase."); return
    try:
        vault = load_vault(pp)
    except ValueError as ex:
        err(str(ex)); return

    entry = _find_entry(vault, name)
    if not entry:
        err(f"No entry found for '{name}'"); return

    hdr(f"EDIT: {entry['name']}")
    print("  Press Enter to keep existing value.\n")
    updated = _prompt_entry(existing=entry)

    # Replace in vault
    vault["entries"] = [e if e["id"] != entry["id"] else updated
                        for e in vault["entries"]]
    save_vault(vault, pp)
    _log("EDIT", entry["name"])
    ok(f"'{updated['name']}' updated")
    cmd_sync(silent=True)


def cmd_delete(name: str):
    if not name:
        name = input("  Entry name to delete: ").strip()
    pp = _get_passphrase()
    if not pp:
        err("No passphrase."); return
    try:
        vault = load_vault(pp)
    except ValueError as ex:
        err(str(ex)); return

    entry = _find_entry(vault, name)
    if not entry:
        err(f"No entry found for '{name}'"); return

    print(f"\n  {RD}Delete '{entry['name']}'?{NC}  This cannot be undone.")
    r = input("  Type the entry name to confirm: ").strip()
    if r != entry["name"]:
        print("  Cancelled.")
        return

    vault["entries"] = [e for e in vault["entries"] if e["id"] != entry["id"]]
    save_vault(vault, pp)
    _log("DELETE", entry["name"])
    ok(f"'{entry['name']}' deleted")
    cmd_sync(silent=True)


def cmd_sync(silent=False):
    """Copy vault to the cartoons drive."""
    if not VAULT_FILE.exists():
        if not silent:
            warn("No vault file to sync yet.")
        return

    if not Path("/Volumes/cartoons").exists():
        if not silent:
            warn("Drive 'cartoons' not connected — sync skipped.")
        return

    try:
        DRIVE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(VAULT_FILE, DRIVE_VAULT)
        if not silent:
            ok(f"Vault synced → {DRIVE_VAULT}")
        _log("SYNC")
    except Exception as ex:
        if not silent:
            err(f"Sync failed: {ex}")


def cmd_status():
    hdr("REX VAULT STATUS")
    has_pp = _kc_has()
    pp = _kc_get() if has_pp else ""
    print(f"  Vault passphrase    : {'✅ Set' if has_pp else RD + '❌ Missing — run --setup' + NC}")
    print(f"  Local vault         : {'✅ ' + str(VAULT_FILE) if VAULT_FILE.exists() else RD+'❌ Not created yet'+NC}")
    print(f"  Drive vault         : {'✅ ' + str(DRIVE_VAULT) if DRIVE_VAULT.exists() else YL+'⚠️  Not synced (is cartoons connected?)'+NC}")

    if VAULT_FILE.exists() and pp:
        try:
            vault = load_vault(pp)
            n = len(vault.get("entries", []))
            updated = vault.get("updated", vault.get("created","?"))[:10]
            print(f"  Entries             : {n}")
            print(f"  Last updated        : {updated}")
            size = VAULT_FILE.stat().st_size
            print(f"  File size           : {size:,} bytes")
        except Exception:
            print(f"  {RD}Could not open vault — wrong passphrase or corrupt{NC}")

    # Recent access log
    if LOG_FILE.exists():
        print(f"\n  {CY}Recent access log:{NC}")
        lines = LOG_FILE.read_text().splitlines()
        for line in lines[-5:]:
            print(f"  {DIM}  {line}{NC}")
    print()


def cmd_change_pass():
    hdr("CHANGE VAULT PASSPHRASE")
    old_pp = getpass.getpass("  Current passphrase: ")
    try:
        vault = load_vault(old_pp)
    except ValueError as ex:
        err(str(ex)); return

    new_pp = getpass.getpass("  New passphrase (min 16 chars): ")
    if len(new_pp) < 16:
        err("Too short — minimum 16 characters."); return
    confirm = getpass.getpass("  Confirm new passphrase: ")
    if new_pp != confirm:
        err("Passphrases don't match."); return

    save_vault(vault, new_pp)
    _kc_set(new_pp)
    ok("Vault re-encrypted with new passphrase")
    ok("Passphrase updated in ~/.rex/rex_vault.pass")
    _log("CHANGE-PASSPHRASE")
    cmd_sync(silent=True)


# ── Main ──────────────────────────────────────────────────────────────────────

HELP = f"""\n{BL}{B}REX VAULT{NC} — Encrypted Credential Store (AES-256-GCM)\n\n  {B}python3 rex_vault.py --setup{NC}         First-time setup\n  {B}python3 rex_vault.py add{NC}             Add a new entry\n  {B}python3 rex_vault.py list{NC}            List all entries\n  {B}python3 rex_vault.py get  <name>{NC}     Show + reveal password (auto-clears in 15s)\n  {B}python3 rex_vault.py find <keyword>{NC}  Search entries\n  {B}python3 rex_vault.py edit <name>{NC}     Edit an entry\n  {B}python3 rex_vault.py delete <name>{NC}   Delete an entry\n  {B}python3 rex_vault.py sync{NC}            Sync vault to /Volumes/cartoons/REX_Vault/\n  {B}python3 rex_vault.py status{NC}          Show vault stats and access log\n  {B}python3 rex_vault.py change-pass{NC}     Change vault passphrase\n\n  Vault file  : ~/Desktop/REX/rex_vault.enc  (AES-256-GCM encrypted)\n  Passphrase  : ~/.rex/rex_vault.pass (chmod 600)\n  Drive backup: /Volumes/cartoons/REX_Vault/rex_vault.enc\n  Access log  : ~/Desktop/REX/logs/vault_access.log\n"""

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd  = args[0].lstrip("-") if args else "help"
    arg2 = args[1] if len(args) > 1 else ""

    dispatch = {
        "setup":       cmd_setup,
        "add":         cmd_add,
        "list":        cmd_list,
        "get":         lambda: cmd_get(arg2),
        "find":        lambda: cmd_find(arg2),
        "search":      lambda: cmd_find(arg2),
        "edit":        lambda: cmd_edit(arg2),
        "delete":      lambda: cmd_delete(arg2),
        "remove":      lambda: cmd_delete(arg2),
        "sync":        lambda: cmd_sync(silent=False),
        "status":      cmd_status,
        "change-pass": cmd_change_pass,
    }

    if cmd in dispatch:
        dispatch[cmd]()
    else:
        print(HELP)
