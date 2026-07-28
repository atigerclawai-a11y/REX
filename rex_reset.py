#!/usr/bin/env python3
"""
REX — Emergency Memory Reset (The Red Button)
===============================================
Wipes REX's memory completely and restarts him clean.
Use this if REX goes off-rails, starts behaving incorrectly,
or you need a clean slate.

The secret keyword to trigger this from inside the REX chat:
    "SOVEREIGN RESET"

Or run this script directly:
    cd ~/Desktop/REX
    python rex_reset.py

Options:
    python rex_reset.py --wipe-all       Wipe ALL memory + ALL session history
    python rex_reset.py --wipe-sessions  Wipe session history only (keep memory)
    python rex_reset.py --wipe-memory    Wipe long-term memory only (keep sessions)
    python rex_reset.py --reseed         Wipe all + re-seed from scratch
"""

import os
import sys
import argparse
from pathlib import Path

# ── Auto-switch to venv Python ─────────────────────────────────────────────────
_HERE    = Path(__file__).parent.resolve()
_VENV_PY = _HERE / ".venv" / "bin" / "python"

try:
    import keyring
    import cryptography  # noqa: F401
except ImportError:
    if _VENV_PY.exists():
        print("🔄 Re-launching with REX venv Python...")
        os.execv(str(_VENV_PY), [str(_VENV_PY)] + sys.argv)
        sys.exit(0)
    else:
        print("❌  Run ./setup.sh first.")
        sys.exit(1)

import base64, sqlite3  # noqa: E402
sys.path.insert(0, str(_HERE))

DB_PATH  = Path.home() / ".rex" / "rex_journeys.db"
APP_NAME = "REX-PrivacyProxy"
KEY_NAME = "rex_master_encryption_key"

RED   = '\033[91m'
GREEN = '\033[92m'
YELLOW= '\033[93m'
BOLD  = '\033[1m'
RESET = '\033[0m'

def get_key():
    stored = keyring.get_password(APP_NAME, KEY_NAME)
    if stored:
        return base64.b64decode(stored)
    return os.urandom(32)


def confirm(prompt: str) -> bool:
    ans = input(f"{YELLOW}{prompt} (yes/no): {RESET}").strip().lower()
    return ans in ("yes", "y")


def wipe_memory(conn):
    before = conn.execute("SELECT COUNT(*) FROM rex_memory WHERE active=1").fetchone()[0]
    conn.execute("UPDATE rex_memory SET active=0")
    conn.commit()
    print(f"  🗑️  Long-term memory: {before} entries wiped.")
    return before


def wipe_sessions(conn):
    before = conn.execute("SELECT COUNT(*) FROM rex_session_log WHERE active=1").fetchone()[0]
    conn.execute("UPDATE rex_session_log SET active=0")
    conn.commit()
    print(f"  🗑️  Session history: {before} sessions wiped.")
    return before


def wipe_journeys(conn):
    before = conn.execute("SELECT COUNT(*) FROM journeys").fetchone()[0]
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM journeys")
    conn.execute("DELETE FROM phi_mappings")
    conn.commit()
    print(f"  🗑️  Journey conversations: {before} wiped.")
    return before


def do_reset(mode: str):
    print()
    print(f"{BOLD}{RED}⚠️  REX EMERGENCY RESET{RESET}")
    print("=" * 44)

    if not DB_PATH.exists():
        print(f"  ℹ️  No database found at {DB_PATH}. Nothing to wipe.")
        return

    conn = sqlite3.connect(str(DB_PATH))

    # Ensure tables exist (in case DB is partial)
    try:
        conn.execute("SELECT 1 FROM rex_memory LIMIT 1")
    except sqlite3.OperationalError:
        print("  ℹ️  Memory tables not found — database may be from an older REX version.")

    if mode == "wipe-all":
        print(f"\n{RED}This will wipe ALL of REX's memory and ALL session history.{RESET}")
        print("REX will wake up with no knowledge of past conversations.")
        if not confirm("Are you sure you want to completely wipe REX?"):
            print("  ✅  Reset cancelled.")
            return
        try:
            wipe_memory(conn)
        except Exception:
            pass
        try:
            wipe_sessions(conn)
        except Exception:
            pass
        print(f"\n{GREEN}✅  REX memory completely wiped. He starts fresh on next launch.{RESET}")

    elif mode == "wipe-sessions":
        print(f"\n{YELLOW}This will wipe session history only. Long-term memory facts are kept.{RESET}")
        if not confirm("Wipe session history?"):
            print("  ✅  Reset cancelled.")
            return
        try:
            wipe_sessions(conn)
        except Exception as e:
            print(f"  ⚠️  {e}")
        print(f"\n{GREEN}✅  Session history cleared. REX still remembers stored facts.{RESET}")

    elif mode == "wipe-memory":
        print(f"\n{YELLOW}This will wipe long-term memory only. Session history is kept.{RESET}")
        if not confirm("Wipe long-term memory?"):
            print("  ✅  Reset cancelled.")
            return
        try:
            wipe_memory(conn)
        except Exception as e:
            print(f"  ⚠️  {e}")
        print(f"\n{GREEN}✅  Memory wiped. REX will rebuild knowledge from future conversations.{RESET}")

    elif mode == "reseed":
        print(f"\n{RED}This will wipe everything and then re-seed from the base GOJ knowledge.{RESET}")
        if not confirm("Wipe all and reseed?"):
            print("  ✅  Reset cancelled.")
            return
        try:
            wipe_memory(conn)
        except Exception:
            pass
        try:
            wipe_sessions(conn)
        except Exception:
            pass
        conn.close()
        print()
        print("🌱 Re-seeding foundational knowledge...")
        os.system(f"{sys.executable} {_HERE}/seed_rex_memory.py")
        print()
        print("🌱 Re-seeding Claude conversation knowledge...")
        os.system(f"{sys.executable} {_HERE}/seed_rex_from_claude.py")
        print(f"\n{GREEN}✅  REX fully reset and reseeded with clean GOJ knowledge.{RESET}")
        return

    conn.close()
    print()
    print("Restart REX to apply: cd ~/Desktop/REX && ./run.sh")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="REX Emergency Memory Reset")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--wipe-all",      action="store_true", help="Wipe ALL memory + session history")
    group.add_argument("--wipe-sessions", action="store_true", help="Wipe session history only")
    group.add_argument("--wipe-memory",   action="store_true", help="Wipe long-term memory only")
    group.add_argument("--reseed",        action="store_true", help="Wipe all + re-seed from scratch")
    args = parser.parse_args()

    if args.wipe_sessions:
        do_reset("wipe-sessions")
    elif args.wipe_memory:
        do_reset("wipe-memory")
    elif args.reseed:
        do_reset("reseed")
    else:
        # Default: wipe-all (the red button)
        do_reset("wipe-all")


if __name__ == "__main__":
    main()
