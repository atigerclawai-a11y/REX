#!/usr/bin/env python3
"""
CC_loop_examiner.py — Daily Build Examiner & Recommendation Engine
v1.0 · June 2026

Scans the entire Tiger Claw ecosystem daily and recommends:
- New agents to build/activate
- New builds (routers, tools, integrations)
- New skills to add
- New tools/extensions to wire up
- Workflow optimizations

Posts findings via Cowork relay.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REX_ROOT = HOME / "Desktop/REX"
HUB_ROOT = HOME / "hermes-hub"
HERMES_CLOUD = HOME / ".hermes-cloud"
HERMES_PROFILE = HOME / ".hermes/profiles/cloud"
SKILLS_DIR = HERMES_PROFILE / "skills"
CRON_DIR = HERMES_PROFILE / "cron"

EXPECTED_PORTS = {
    8000: "REX FastAPI", 9119: "HermesDash",
    8080: "DataRex GOJ", 5678: "n8n", 11436: "Ollama Proxy",
    8766: "Rexxie Tools", 8768: "Model Router",
    27125: "Obsidian API",
    3023: "Hermie GW", 3024: "Rexxie GW",
    3080: "LibreChat"
}

RESTART_COMMANDS = {
    27125: "launchctl load ~/Library/LaunchAgents/com.ghs.obsidian-api.plist 2>/dev/null",
    8080: "launchctl load ~/Library/LaunchAgents/com.goj.datarex.plist 2>/dev/null",
    3080: "cd ~/debate-chamber/LibreChat && docker compose up -d 2>/dev/null",
    3023: "hermes --profile hermie gateway restart 2>/dev/null",
    3024: "hermes --profile rexxie gateway restart 2>/dev/null",
}

# Track restart flapping
RESTART_HISTORY = {}  # port -> count of restarts today

def run(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        return str(e)

def check_services() -> dict:
    """Check all expected services. Attempt restart for DOWN services with known plists."""
    global RESTART_HISTORY
    result = {"up": [], "down": [], "restarted": [], "still_down": []}
    for port, name in EXPECTED_PORTS.items():
        out = run(f"lsof -iTCP:{port} -sTCP:LISTEN -nP 2>/dev/null | wc -l", timeout=3)
        if out.isdigit() and int(out) > 1:
            result["up"].append(f":{port} {name}")
        elif port in RESTART_COMMANDS:
            # Try auto-restart
            run(RESTART_COMMANDS[port], timeout=10)
            time.sleep(3)
            out2 = run(f"lsof -iTCP:{port} -sTCP:LISTEN -nP 2>/dev/null | wc -l", timeout=3)
            if out2.isdigit() and int(out2) > 1:
                RESTART_HISTORY[port] = RESTART_HISTORY.get(port, 0) + 1
                tag = " ⚠️flapping" if RESTART_HISTORY[port] >= 3 else ""
                result["restarted"].append(f":{port} {name}{tag}")
                result["up"].append(f":{port} {name}")
            else:
                result["still_down"].append(f":{port} {name}")
        else:
            result["still_down"].append(f":{port} {name}")
    return result

def count_files(pattern: str, directory: Path) -> int:
    """Count files matching a glob in a directory."""
    try:
        return len(list(directory.glob(pattern)))
    except Exception:
        return 0

def scan_routers() -> dict:
    """Scan what routers are built vs mounted."""
    # These are standalone servers on their own ports, not mountable routers
    STANDALONE_SERVERS = {
        "CC_stats_api",           # Runs on :8001
        "CC_lead_connector_api",  # Runs on :8002
        "CC_loop_examiner",       # Standalone examiner script
    }
    built = []
    mounted = []
    main_py = REX_ROOT / "backend/main.py"
    backend_dir = REX_ROOT / "backend"

    # Find built routers in backend/
    for f in sorted(backend_dir.glob("CC_*.py")):
        if "main" not in f.stem.lower() and f.stem not in STANDALONE_SERVERS:
            content = f.read_text()
            if "APIRouter" in content:
                built.append(f.stem)

    # Find built routers in root (e.g. CC_rex_bill.py, CC_quickbooks_capture.py)
    for f in sorted(REX_ROOT.glob("CC_*.py")):
        if f.stem not in built and "main" not in f.stem.lower() and f.stem not in STANDALONE_SERVERS:
            content = f.read_text()
            if "APIRouter" in content:
                built.append(f.stem)

    # Find mounted routers by scanning import lines
    if main_py.exists():
        content = main_py.read_text()
        for b in built:
            # Match import lines like:
            #   from .CC_goj_live import router
            #   from CC_rex_bill import router
            if f"from .{b} import" in content or f"from {b} import" in content:
                mounted.append(b)

    unmounted = [b for b in built if b not in mounted]
    return {"built": built, "mounted": mounted, "unmounted": unmounted}

def scan_skills() -> dict:
    """Scan installed skills."""
    skills = []
    if SKILLS_DIR.exists():
        for skill_dir in sorted(SKILLS_DIR.rglob("SKILL.md")):
            rel = skill_dir.relative_to(SKILLS_DIR)
            skills.append(str(rel.parent) if rel.parent != Path(".") else "root")
    return {"count": len(skills), "skills": skills}

def scan_cronjobs() -> dict:
    """Scan active cron jobs."""
    jobs = []
    if CRON_DIR.exists():
        for f in sorted(CRON_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                jobs.append({
                    "id": f.stem,
                    "schedule": data.get("schedule", "?"),
                    "name": data.get("name", f.stem),
                    "enabled": data.get("enabled", True),
                })
            except Exception:
                pass
    return {"count": len(jobs), "jobs": jobs}

def scan_launchd() -> dict:
    """Scan all GOJ/TigerClaw launchd services."""
    agents_dir = HOME / "Library/LaunchAgents"
    services = []
    if agents_dir.exists():
        for f in sorted(agents_dir.glob("com.goj.*.plist")):
            services.append(f.stem)
        for f in sorted(agents_dir.glob("com.tigerclaw.*.plist")):
            services.append(f.stem)
        for f in sorted(agents_dir.glob("ai.hermes.*.plist")):
            services.append(f.stem)
    return {"count": len(services), "services": services}

def scan_pae_items() -> dict:
    """Scan for pending PAE items."""
    pae_dir = REX_ROOT
    pending = []
    for f in sorted(pae_dir.glob("CC_PAE_*.md")):
        content = f.read_text()
        if "approved" not in content.lower() or "STATUS: pending" in content:
            pending.append(f.name)
    return {"count": len(pending), "pending": pending}

def scan_new_opportunities() -> list:
    """Identify gaps and recommend new builds."""
    recommendations = []

    # Check what services are down
    svc = check_services()
    if svc["still_down"]:
        recommendations.append(f"🔧 Fix {len(svc['still_down'])} down services: {', '.join(svc['still_down'][:5])}")

    # Check unmounted routers
    routers = scan_routers()
    if routers["unmounted"]:
        recommendations.append(f"📦 Mount {len(routers['unmounted'])} unmounted routers: {', '.join(routers['unmounted'])}")

    # Check for missing integrations
    hub_env = HERMES_CLOUD / ".env"
    if hub_env.exists():
        env_text = hub_env.read_text()
        missing_keys = []
        for key in ["WHATSAPP", "LINKEDIN", "TIKTOK", "YOUTUBE"]:
            if key not in env_text:
                missing_keys.append(key)
        if missing_keys:
            recommendations.append(f"🔑 Missing API keys: {', '.join(missing_keys)}")

    # Check Agent Forge activation
    forge_registry = REX_ROOT / "state/agent_forge_registry.json"
    if forge_registry.exists():
        try:
            reg = json.loads(forge_registry.read_text())
            inactive = [a for a in reg.get("agents", []) if not a.get("active")]
            if inactive:
                recommendations.append(f"🤖 Activate {len(inactive)} dormant agents from Agent Forge")
        except Exception:
            pass

    # Check for security gaps
    if not (HOME / ".hermes/firewall.lock").exists():
        recommendations.append("🛡️ Enable macOS firewall (currently OFF)")

    # Check for unencrypted auth_tracker.db
    auth_db = HOME / "Documents/goj files/dashboard/auth_tracker.db"
    if auth_db.exists():
        recommendations.append("🔐 Encrypt auth_tracker.db with SQLCipher (HIPAA priority)")

    # Check TransitionAgent overdue
    if not (HOME / "Desktop/REX/CC_transition_workflow_captured.flag").exists():
        recommendations.append("🚨 TransitionAgent Drive hook active but workflow NOT captured — bookkeeper may depart")

    return recommendations

def generate_report() -> str:
    """Generate compact daily examination report — only shows what's broken."""
    now = datetime.now(timezone.utc).isoformat()
    svc = check_services()
    up_count = len(svc['up'])
    total = len(EXPECTED_PORTS)

    lines = [f"## 🔄 /LOOP — Daily Build Examiner", f"**{now}**", ""]
    lines.append(f"**{up_count}/{total} UP**")

    if svc['restarted']:
        lines.append("### 🔄 Auto-Restarted")
        for s in svc['restarted']:
            lines.append(f"  - {s}")

    if svc['still_down']:
        lines.append("### ❌ Still DOWN")
        for s in svc['still_down']:
            lines.append(f"  - {s}")
    elif not svc['restarted']:
        lines.append("✅ All services UP")

    # Only show routers if unmounted ones exist
    routers = scan_routers()
    if routers['unmounted']:
        lines.append("")
        lines.append("### ⚠️ Unmounted Routers (built but not wired into REX :8000)")
        for r in routers['unmounted']:
            lines.append(f"  - {r}")

    # Only show recommendations if they exist
    recommendations = scan_new_opportunities()
    if recommendations:
        lines.append("")
        lines.append("### 💡 Recommendations")
        for i, r in enumerate(recommendations):
            lines.append(f"{i+1}. {r}")

    report = '\n'.join(lines)

    # Save full report to disk (for history)
    report_path = REX_ROOT / "CC_loop_report_latest.md"
    report_path.write_text(report)

    # Save timestamp
    timestamp_path = REX_ROOT / "state/loop_last_run.json"
    timestamp_path.write_text(json.dumps({"last_run": now, "services_up": up_count}))

    return report

def send_relay(message: str) -> bool:
    """Send report via Cowork relay."""
    try:
        import urllib.request
        data = json.dumps({"message": message, "source": "loop-examiner"}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/cowork-relay",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"Relay send failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    report = generate_report()
    print(report)
    send_relay(report)
