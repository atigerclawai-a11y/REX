#!/usr/bin/env python3
"""
OmniRoute Health Watchdog — reports bridge health ONLY when OmniRoute is
being actively used. Silent when idle (no cron noise).

Logic:
  1. Detect "in use": active TCP connections to :20128 OR log activity in the
     last 20 minutes (ProxyEgress/CHAT entries).
  2. If idle → print NOTHING (cron watchdog pattern: empty = silent).
  3. If in use → run the quick family sweep and print alive/dead summary.

Usage: python3 ~/Desktop/REX/omniroute_health_watchdog.py
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

LOG = os.path.expanduser("~/.omniroute/logs/application/app.log")
SWEEP = os.path.expanduser("~/Desktop/REX/omniroute_health.py")
ACTIVITY_WINDOW_MIN = 20  # considered "in use" if traffic within this window
CHECK_TIMEOUT = 200  # total budget for the health sweep

# ── 1. Detect usage ──────────────────────────────────────────────────────────

def recent_log_activity() -> bool:
    """Any ProxyEgress / CHAT / COMBO log line in the last N minutes?"""
    if not os.path.exists(LOG):
        return False
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=ACTIVITY_WINDOW_MIN)
        with open(LOG, "r", errors="ignore") as f:
            for line in f:
                if "ProxyEgress" not in line and '"tag":"CHAT"' not in line:
                    continue
                m = re.search(r'"time":"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                if not m:
                    continue
                try:
                    ts = datetime.fromisoformat(m.group(1) + "+00:00")
                except ValueError:
                    continue
                if ts >= cutoff:
                    return True
    except Exception:
        return False
    return False

def active_connections() -> bool:
    """Any established TCP connection to :20128 (someone is actively chatting)?"""
    try:
        out = subprocess.run(
            ["lsof", "-iTCP:20128", "-sTCP:ESTABLISHED"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        return len([l for l in out.splitlines() if "->" in l and "127.0.0.1" in l]) > 0
    except Exception:
        return False

# ── 2. Main ─────────────────────────────────────────────────────────────────

def main():
    in_use = recent_log_activity() or active_connections()
    if not in_use:
        # Idle → silent. The cron scheduler sends nothing for empty stdout.
        return 0

    # In use → sweep and report
    t0 = time.time()
    try:
        out = subprocess.run(
            ["/opt/homebrew/bin/python3.11", SWEEP, "--quick", "--json"],
            capture_output=True, text=True, timeout=CHECK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print("⏳ OmniRoute health sweep timed out (bridges very slow right now).")
        return 0

    data = None
    # JSON is the last block printed; it spans multiple lines. Grab everything
    # from the first '{' onward and parse it as one document.
    lines_out = out.stdout.splitlines()
    start = next((i for i, l in enumerate(lines_out) if l.strip().startswith("{")), None)
    if start is not None:
        blob = "\n".join(lines_out[start:])
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            pass
    if data is None:
        print("⚠️  OmniRoute in use but health sweep produced no JSON output.")
        return 0

    alive = data.get("alive", 0)
    total = data.get("total", 0)
    results = data.get("results", [])
    good = [r for r in results if r.get("alive")]
    bad = [r for r in results if not r.get("alive")]

    lines = [f"🧪 OmniRoute health (in use, {int(time.time()-t0)}s): **{alive}/{total} bridges alive**"]
    if good:
        names = ", ".join(r["model"] for r in good)
        lines.append(f"✅ Working: {names}")
    if bad:
        # compact: group by failure reason
        by_reason = {}
        for r in bad:
            m = re.search(r"\[(\d+)\]", r.get("msg", ""))
            key = f"HTTP {m.group(1)}" if m else (r.get("msg", "")[:50] or "unknown")
            by_reason.setdefault(key, []).append(r["model"])
        for reason, models in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            lines.append(f"❌ {reason}: {len(models)} ({', '.join(models[:5])})")
    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
