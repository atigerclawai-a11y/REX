#!/usr/bin/env python3
"""
GHS Cross-Agent Log — single entry point for all agents to log to log.md.

Usage:
    python3 cross_agent_log.py --agent "Claude Code" --action "build" --summary "Fixed auth_tracker schema"
    echo "Details about what was done" | python3 cross_agent_log.py --agent "JARVIS" --action "deploy"

Accepts details via stdin or --detail argument.
Appends to ~/Documents/GHS-Vault/log.md (canonical), falls back to ~/GHS-Vault/.
"""

import argparse
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

HOME = os.path.expanduser("~")
CANONICAL = Path(HOME) / "Documents" / "GHS-Vault" / "log.md"
MIRROR = Path(HOME) / "GHS-Vault" / "log.md"
KNOWN_AGENTS = {"Hermes", "Claude Code", "JARVIS", "NotebookLM", "Rexxie", "Nemobot", "Cron", "Night Shift", "Red Team", "Blue Team", "Kimi K3"}
VALID_ACTIONS = {"build", "fix", "deploy", "audit", "ingest", "update", "create", "archive", "flag", "approve", "reject", "inject", "ocr", "lint", "maintenance", "briefing", "consolidate", "review", "investigate", "config", "monitor"}


def est_now() -> str:
    """Return EST/EDT timestamp (UTC-4 or UTC-5)."""
    utc = datetime.now(timezone.utc)
    # EDT = UTC-4 (Mar~Nov), EST = UTC-5 (Nov~Mar)
    # Rough: April-October = EDT
    month = utc.month
    offset = timedelta(hours=4) if 3 <= month <= 10 else timedelta(hours=5)
    est = utc - offset
    return est.strftime("%Y-%m-%d %H:%M")


def append_log(agent: str, action: str, summary: str, detail: str = ""):
    timestamp = est_now()
    entry = f"\n## [{timestamp}] {agent} | {action} | {summary}\n"
    if detail:
        # Prefix each line with "- " for bullet formatting
        for line in detail.strip().split("\n"):
            stripped = line.strip()
            if stripped:
                entry += f"- {stripped}\n"
            else:
                entry += "\n"

    # Try canonical first
    target = CANONICAL
    try:
        os.makedirs(str(target.parent), exist_ok=True)
        with open(str(target), "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"✅ Logged to {target}")
        return 0
    except PermissionError:
        pass

    # Fallback to mirror
    target = MIRROR
    try:
        os.makedirs(str(target.parent), exist_ok=True)
        with open(str(target), "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"✅ Logged to {target} (mirror fallback)")
        return 0
    except Exception as e:
        print(f"❌ Failed to log: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Cross-agent logger for GHS log.md")
    parser.add_argument("--agent", required=True, help="Agent name (e.g. 'Claude Code', 'JARVIS')")
    parser.add_argument("--action", required=True, choices=sorted(VALID_ACTIONS), help="Action type")
    parser.add_argument("--summary", required=True, help="One-line summary of what happened")
    parser.add_argument("--detail", default="", help="Optional detail (newlines supported via \\n)")
    args = parser.parse_args()

    # Validate agent (warn but allow unknown)
    if args.agent not in KNOWN_AGENTS:
        print(f"⚠️  Unknown agent '{args.agent}' — known: {', '.join(sorted(KNOWN_AGENTS))}", file=sys.stderr)

    # Read stdin for detail if no --detail provided
    detail = args.detail
    if not detail and not sys.stdin.isatty():
        detail = sys.stdin.read().strip()

    return append_log(args.agent, args.action, args.summary, detail)


if __name__ == "__main__":
    sys.exit(main())
