#!/usr/bin/env python3
"""REXXIE_VAULT access — read/write to encrypted USB flash drive."""
import json, os, sys
from pathlib import Path

VAULT = "/Volumes/REXXIE_VAULT"
PASSWORDS = os.path.join(VAULT, "passwords")
SENSITIVE = os.path.join(VAULT, "sensitive")

def ensure_mounted():
    """Unlock and mount the vault if not already."""
    if os.path.ismount(VAULT):
        return True
    import subprocess
    # Try Keychain unlock
    r = subprocess.run(
        ["security", "find-generic-password", "-s", "REXXIE_VAULT", "-w"],
        capture_output=True, text=True)
    if r.returncode == 0:
        passphrase = r.stdout.strip()
        # Unlock and mount
        subprocess.run(
            ["diskutil", "apfs", "unlockVolume", "disk12s1"],
            input=passphrase + "\n", text=True, capture_output=True)
        return os.path.ismount(VAULT)
    return False

def list_entries(directory):
    """List all entries in a directory."""
    if not os.path.exists(directory):
        return []
    return sorted([f for f in os.listdir(directory) if f.endswith('.md')])

def read_entry(filename, directory=PASSWORDS):
    """Read an entry from the vault."""
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()

def write_entry(filename, content, directory=PASSWORDS):
    """Write an entry to the vault."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, 'w') as f:
        f.write(content)
    return True

def delete_entry(filename, directory=PASSWORDS):
    """Delete an entry."""
    path = os.path.join(directory, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False

if __name__ == "__main__":
    if not ensure_mounted():
        print(json.dumps({"error": "Vault not mounted"}))
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print(json.dumps({
            "mounted": True,
            "passwords": list_entries(PASSWORDS),
            "sensitive": list_entries(SENSITIVE)
        }))
    elif sys.argv[1] == "read" and len(sys.argv) >= 3:
        content = read_entry(sys.argv[2]) or read_entry(sys.argv[2], SENSITIVE)
        print(content if content else json.dumps({"error": "not found"}))
    elif sys.argv[1] == "write" and len(sys.argv) >= 4:
        # Read content from stdin
        content = sys.stdin.read() if not sys.stdin.isatty() else sys.argv[3]
        cat = PASSWORDS if "--passwords" in sys.argv else SENSITIVE
        result = write_entry(sys.argv[2], content, cat)
        print(json.dumps({"ok": result}))
    elif sys.argv[1] == "delete" and len(sys.argv) >= 3:
        result = delete_entry(sys.argv[2]) or delete_entry(sys.argv[2], SENSITIVE)
        print(json.dumps({"ok": result}))
