#!/usr/bin/env python3
"""
CC_firewall_endpoint_patch.py
Rexxie Firewall — Stats API Endpoint Patch
Gold Health Systems · June 4 2026

This file contains the FastAPI endpoint to add to CC_stats_api.py (or main.py)
for monitoring the Rexxie firewall from the dashboard or API.

HOW TO INTEGRATE:
  1. Copy the route function below into CC_stats_api.py
  2. Ensure `import json, os` is already present in the target file
  3. The endpoint will be available at GET /api/firewall/status

DO NOT modify this file directly to make it runnable —
it is a patch snippet for manual integration.
"""

# ── PASTE THIS BLOCK INTO CC_stats_api.py (or main.py) ──────────────────────

import json
import os
from pathlib import Path

# Required: FastAPI app must already be defined as `app` in the target file.

# --- begin paste ---

FIREWALL_STATE_FILE = Path.home() / "Desktop" / "REX" / ".rexxie_firewall_state.json"
REXXIE_DB_PATH      = Path.home() / "Desktop" / "REX" / "rexxie.db"
ZOMBIE_PLIST_PATH   = Path.home() / "Library" / "LaunchAgents" / "com.hermes.rexxie-bot.plist"


# @app.get("/api/firewall/status")
def firewall_status():
    """
    Rexxie firewall current status.
    Returns the last known state from the firewall daemon's state file.

    Response fields:
      status          — "active" | "not_running" | "no_state"
      last_check      — ISO timestamp of last check
      last_clean      — ISO timestamp of last clean check
      check_count     — total checks run since daemon start
      violation_count — total violations recorded
      recent_violations — last 5 violations (type, severity, detail, timestamp)
      db_present      — whether rexxie.db exists on disk
      zombie_present  — whether the zombie plist file exists (should be False)
      zombie_hash     — first 8 chars of zombie plist hash (None if absent)
    """
    if not FIREWALL_STATE_FILE.exists():
        return {
            "status": "not_running",
            "message": "Firewall daemon has not run yet. Install and load com.ghs.rexxie-firewall.plist.",
            "violations": [],
            "last_check": None,
            "db_present": REXXIE_DB_PATH.exists(),
            "zombie_present": ZOMBIE_PLIST_PATH.exists(),
        }

    try:
        with open(FIREWALL_STATE_FILE) as f:
            state = json.load(f)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    violations = state.get("violations", [])
    recent = violations[:5]

    # Determine if daemon appears "active" — last check within 5 minutes
    last_check = state.get("last_check")
    status = "active"
    if last_check:
        from datetime import datetime, timezone, timedelta
        try:
            last_dt = datetime.fromisoformat(last_check)
            if datetime.now(timezone.utc) - last_dt > timedelta(minutes=5):
                status = "stale"  # Daemon may have crashed
        except Exception:
            status = "unknown"
    else:
        status = "no_state"

    zombie_hash = state.get("zombie_hash")

    return {
        "status": status,
        "last_check": last_check,
        "last_clean": state.get("last_clean"),
        "check_count": state.get("check_count", 0),
        "violation_count": len(violations),
        "recent_violations": recent,
        "db_present": REXXIE_DB_PATH.exists(),
        "zombie_present": ZOMBIE_PLIST_PATH.exists(),
        "zombie_hash": (zombie_hash[:8] + "...") if zombie_hash else None,
        "db_table_hash": state.get("db_table_hash"),
    }

# --- end paste ---

# ── DASHBOARD WIDGET (for goj-pipeline datarex app.py) ───────────────────────
# If integrating into the Flask GOJ dashboard (port 8080), use this instead:

FLASK_ROUTE_CODE = '''
@app.route("/api/firewall/status")
def firewall_status():
    import json
    from pathlib import Path
    from datetime import datetime, timezone, timedelta

    state_file = Path.home() / "Desktop" / "REX" / ".rexxie_firewall_state.json"
    rexxie_db  = Path.home() / "Desktop" / "REX" / "rexxie.db"
    zombie     = Path.home() / "Library" / "LaunchAgents" / "com.hermes.rexxie-bot.plist"

    if not state_file.exists():
        return {"status": "not_running", "violation_count": 0, "db_present": rexxie_db.exists()}

    with open(state_file) as f:
        state = json.load(f)

    violations = state.get("violations", [])
    last_check = state.get("last_check")
    status = "active"
    if last_check:
        try:
            dt = datetime.fromisoformat(last_check)
            if datetime.now(timezone.utc) - dt > timedelta(minutes=5):
                status = "stale"
        except Exception:
            pass

    return {
        "status": status,
        "last_check": last_check,
        "check_count": state.get("check_count", 0),
        "violation_count": len(violations),
        "recent_violations": violations[:5],
        "db_present": rexxie_db.exists(),
        "zombie_present": zombie.exists(),
    }
'''

if __name__ == "__main__":
    print("This file is a patch snippet — not meant to run directly.")
    print("Copy the function above into CC_stats_api.py or main.py and register it:")
    print("  app.get('/api/firewall/status')(firewall_status)")
