#!/usr/bin/env python3
"""CC_mcp_guardian.py — MCP Process Duplication Monitor

Checks for zombie MCP processes spawned by the Hermes gateway.
Alerts via Telegram when any MCP server has more than MAX_COPIES_ALLOWED duplicates
or total MCP processes exceed MAX_TOTAL.

Usage:
  python3 CC_mcp_guardian.py          # Run once, alert if issues
  python3 CC_mcp_guardian.py --fix    # Auto-kill duplicates above threshold
  python3 CC_mcp_guardian.py --quiet  # Silent unless problems found

Cron: run every 30 minutes via Hermes cronjob or launchd.
"""

import subprocess
import sys
import os
from collections import Counter
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
MAX_COPIES_ALLOWED = 2        # Alert if any MCP has >2 running copies
MAX_TOTAL = 50                # Alert if total MCP processes >50
TELEGRAM_CHAT_ID = "5587703834"
LOG_FILE = os.path.expanduser("~/Desktop/REX/logs/mcp_guardian.log")

# ── Helpers ─────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_mcp_processes() -> dict[str, int]:
    """Returns {mcp_name: count} for all running MCP server processes."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=10
        )
    except Exception as e:
        log(f"ERROR: ps failed: {e}")
        return {}

    counts: Counter = Counter()
    total = 0
    for line in result.stdout.splitlines():
        if "mcp-servers/" in line and "grep" not in line:
            total += 1
            # Extract the script filename
            parts = line.split()
            for p in parts:
                if "mcp-servers/" in p:
                    name = os.path.basename(p)
                    counts[name] += 1
                    break

    # Also count node-based MCP servers
    result2 = subprocess.run(
        ["pgrep", "-fl", "mcp-server"],
        capture_output=True, text=True, timeout=5
    )
    for line in result2.stdout.splitlines():
        if "grep" in line:
            continue
        if "mcp-server-filesystem" in line:
            counts["filesystem (node)"] += 1
            total += 1
        elif "mcp-server-github" in line:
            counts["github (node)"] += 1
            total += 1
        elif "mcp-server-sqlite" in line:
            counts["sqlite (node)"] += 1
            total += 1

    # n8n MCP
    result3 = subprocess.run(
        ["pgrep", "-fl", "n8n-mcp"],
        capture_output=True, text=True, timeout=5
    )
    for line in result3.stdout.splitlines():
        if "grep" in line:
            continue
        counts["n8n-mcp (node)"] += 1
        total += 1

    # Add total to the dict for reporting
    counts["__TOTAL__"] = total
    return dict(counts)


def kill_duplicates(processes: dict[str, int], dry_run: bool = False):
    """Kill all processes for MCPs that have more than MAX_COPIES_ALLOWED copies."""
    for name, count in processes.items():
        if name == "__TOTAL__":
            continue
        if count > MAX_COPIES_ALLOWED:
            excess = count - MAX_COPIES_ALLOWED
            log(f"  {'[DRY RUN] ' if dry_run else ''}Killing {excess} excess copies of {name} ({count} → {MAX_COPIES_ALLOWED})")
            if not dry_run:
                # Kill all instances of this MCP server
                script_name = name.replace(" (node)", "")
                if "(node)" in name:
                    subprocess.run(["pkill", "-f", script_name], timeout=10)
                else:
                    subprocess.run(["pkill", "-f", f"mcp-servers/{script_name}"], timeout=10)


def send_telegram_alert(message: str):
    """Send alert via Telegram bot."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            # Try env files
            for env_path in [
                os.path.expanduser("~/Desktop/REX/.env"),
                os.path.expanduser("~/.hermes/profiles/cloud/.env"),
            ]:
                if os.path.exists(env_path):
                    with open(env_path) as ef:
                        for line in ef:
                            if line.startswith("TELEGRAM_BOT_TOKEN="):
                                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                if token:
                    break

        if not token:
            log("WARNING: No Telegram bot token found, cannot send alert")
            return

        import urllib.request, json
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log(f"Alert sent to Telegram chat {TELEGRAM_CHAT_ID}")
    except Exception as e:
        log(f"ERROR sending Telegram alert: {e}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    fix_mode = "--fix" in sys.argv
    quiet = "--quiet" in sys.argv

    log(f"=== MCP Guardian {'(fix mode)' if fix_mode else '(check mode)'} ===")
    processes = get_mcp_processes()
    total = processes.pop("__TOTAL__", 0)

    if not quiet:
        log(f"Total MCP processes: {total}")
        log(f"Unique MCP servers: {len(processes)}")

    alerts = []
    worst_offenders = []

    # Check per-MCP duplication
    for name, count in sorted(processes.items(), key=lambda x: -x[1]):
        status = "⚠️" if count > MAX_COPIES_ALLOWED else "✅"
        if count > MAX_COPIES_ALLOWED:
            alerts.append(f"{status} <b>{name}</b>: {count} copies (max {MAX_COPIES_ALLOWED})")
            if len(worst_offenders) < 5:
                worst_offenders.append(f"  • {name}: {count}x")

    # Check total
    if total > MAX_TOTAL:
        alerts.append(f"🔴 <b>Total MCP processes: {total}</b> (max {MAX_TOTAL})")

    if alerts:
        # Build alert message
        alert_msg = f"🚨 <b>MCP Guardian Alert</b>\n\n"
        alert_msg += f"Total MCP processes: <b>{total}</b>\n"
        alert_msg += f"Max allowed per server: <b>{MAX_COPIES_ALLOWED}</b>\n\n"
        alert_msg += "<b>Worst offenders:</b>\n"
        alert_msg += "\n".join(worst_offenders[:5])
        alert_msg += f"\n\n{len(alerts)} alert(s) total"

        if fix_mode:
            alert_msg += "\n\n🔧 Auto-fix engaged — killing excess processes..."
            log("Auto-fix engaged")
            kill_duplicates(processes, dry_run=False)
        else:
            alert_msg += "\n\nRun with --fix to auto-kill duplicates."

        log(f"ALERT: {len(alerts)} issues found")
        send_telegram_alert(alert_msg)
        if fix_mode:
            # Check again after fix
            processes2 = get_mcp_processes()
            total2 = processes2.pop("__TOTAL__", 0)
            log(f"After fix: {total2} total MCP processes, {len(processes2)} unique")
    else:
        log("✅ All MCP servers within limits — no alerts")
        if not quiet:
            for name, count in sorted(processes.items(), key=lambda x: -x[1]):
                log(f"  ✅ {name}: {count}x")

    log("=== MCP Guardian done ===")


if __name__ == "__main__":
    main()
