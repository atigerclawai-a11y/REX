#!/usr/bin/env python3
"""
CC_himalaya_set_app_password.py — Update himalaya IMAP/SMTP app password.

Usage:
    python3 CC_himalaya_set_app_password.py --account olympusbbg --password "abcd efgh ijkl mnop"
    python3 CC_himalaya_set_app_password.py --account atigerclawai --password abcdefghijklmnop
"""
import sys, re, subprocess
from pathlib import Path

HIMALAYA_CONFIG = Path.home() / ".config" / "himalaya" / "config.toml"

def main():
    account = None
    password = None
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--account' and i + 1 < len(args):
            account = args[i + 1]
            i += 2
        elif args[i] == '--password' and i + 1 < len(args):
            password = args[i + 1].replace(' ', '')  # strip spaces
            i += 2
        else:
            i += 1
    
    if not account or not password:
        print("Usage: CC_himalaya_set_app_password.py --account NAME --password 'xxxx xxxx xxxx xxxx'")
        sys.exit(1)
    
    if len(password) != 16:
        print(f"⚠️  Password is {len(password)} chars — expected 16. Check for copy errors.")
        if input("Continue anyway? (y/n): ").lower() != 'y':
            sys.exit(1)
    
    config = HIMALAYA_CONFIG.read_text()
    
    # Find the account section
    section_header = f"[accounts.{account}]"
    if section_header not in config:
        print(f"❌ Account '{account}' not found in {HIMALAYA_CONFIG}")
        print(f"   Run: himalaya account configure {account}")
        sys.exit(1)
    
    # Replace password in auth.raw lines for this account
    # Pattern: backend.auth.raw = "..."  and message.send.backend.auth.raw = "..."
    updated = config
    replacements = 0
    
    # Find start of account section
    start = config.index(section_header)
    # Find start of next section (or end)
    rest = config[start:]
    next_section = re.search(r'\n\[accounts\.', rest[len(section_header):])
    if next_section:
        section_end = start + len(section_header) + next_section.start()
    else:
        section_end = len(config)
    
    section = config[start:section_end]
    
    # Replace all auth.raw lines in this section
    def replace_auth(match):
        nonlocal replacements
        replacements += 1
        return f'{match.group(1)}"{password}"'
    
    updated_section = re.sub(
        r'(backend\.auth\.raw\s*=\s*)".*?"',
        replace_auth,
        section
    )
    
    if replacements == 0:
        print(f"❌ No auth.raw lines found in [{account}] section")
        sys.exit(1)
    
    updated = config[:start] + updated_section + config[section_end:]
    
    # Backup and write
    backup = HIMALAYA_CONFIG.with_suffix(".toml.bak")
    HIMALAYA_CONFIG.rename(backup)
    HIMALAYA_CONFIG.write_text(updated)
    
    print(f"✅ Updated {replacements} auth.raw line(s) for {account}")
    print(f"   Backup: {backup}")
    print(f"   Password: {'*' * 16}")
    print()
    print("Verify with:")
    print(f"   himalaya envelope list --account {account} --folder INBOX --max 1")
    
    # Store in Keychain
    try:
        subprocess.run([
            "security", "add-generic-password",
            "-a", f"{account}@gmail.com" if '@' not in account else account,
            "-s", "gmail-app-password",
            "-w", password,
            "-U"
        ], check=True, capture_output=True)
        print(f"\n🔑 Stored in macOS Keychain (gmail-app-password / {account})")
    except subprocess.CalledProcessError:
        print(f"\n⚠️  Keychain storage failed (may already exist). Manual: security add-generic-password ...")

if __name__ == "__main__":
    main()
