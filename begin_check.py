#!/usr/bin/env python3
"""
begin_check.py — REX/GOJ Agent Status Engine
Reads agent_registry.json and checks every agent.
Called by begin.sh — not meant to be run directly.

Usage:
  python begin_check.py status        → print colored status table, exit 0=all-ok 1=some-down
  python begin_check.py start         → start all stopped required agents
  python begin_check.py start-all     → start all stopped agents (required + optional)
  python begin_check.py force         → kill + restart everything
  python begin_check.py autocheck     → one-line terminal open summary
"""

import json, os, sys, signal, socket, subprocess, time
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
REX_DIR  = Path.home() / "Desktop" / "REX"
REGISTRY = REX_DIR / "agent_registry.json"
LOGS     = REX_DIR / "logs"

# ── Colors ────────────────────────────────────────────────────────────────────
R   = "\033[0m"
GRN = "\033[92m"; YEL = "\033[93m"; RED = "\033[91m"
CYN = "\033[96m"; GRY = "\033[90m"; WHT = "\033[97m"
BLD = "\033[1m";  DIM = "\033[2m"

# ── Resolve Python ─────────────────────────────────────────────────────────────
def best_python() -> str:
    candidates = [
        str(REX_DIR / ".venv" / "bin" / "python"),
        str(Path.home() / "debate-chamber" / ".venv" / "bin" / "python3"),
        "python3",
    ]
    for c in candidates:
        if Path(c).exists() or c == "python3":
            return c
    return "python3"

PY = best_python()

# ── Load registry ─────────────────────────────────────────────────────────────
def load_registry() -> dict:
    if not REGISTRY.exists():
        print(f"{RED}ERROR: agent_registry.json not found at {REGISTRY}{R}")
        sys.exit(1)
    with open(REGISTRY) as f:
        return json.load(f)

# ── Status probes ──────────────────────────────────────────────────────────────
def proc_running(name: str) -> bool:
    if not name or name == "__ollama__":
        return False
    r = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True)
    pids = [int(p) for p in r.stdout.strip().splitlines()
            if p.strip().isdigit() and int(p) != os.getpid()]
    return len(pids) > 0

def port_open(port: int) -> bool:
    if not port:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def ollama_running() -> tuple[bool, list]:
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "2", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            data   = json.loads(r.stdout)
            models = [m["name"] for m in data.get("models", [])]
            return True, models
    except Exception:
        pass
    return False, []

def launchd_running(label: str) -> bool:
    if not label:
        return False
    r = subprocess.run(["launchctl", "list", label], capture_output=True, text=True)
    return r.returncode == 0

def agent_is_running(a: dict) -> bool:
    detect  = a.get("detect_process", "")
    port    = a.get("detect_port")
    launch  = a.get("launch_mode", "")
    launchd = a.get("launchd_plist", "")

    if detect == "ollama" or launch == "ollama":
        running, _ = ollama_running()
        return running
    if launch == "launchd" and launchd:
        return launchd_running(launchd) or proc_running(detect)
    if detect:
        if proc_running(detect):
            return True
    if port and port_open(port):
        return True
    return False

# ── Start an agent ─────────────────────────────────────────────────────────────
def kill_conflicts(conflicts: list):
    for c in conflicts:
        r = subprocess.run(["pgrep", "-f", c], capture_output=True, text=True)
        pids = [int(p) for p in r.stdout.strip().splitlines() if p.strip().isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    if conflicts:
        time.sleep(1)

def start_agent(a: dict) -> bool:
    """Start an agent. Returns True if it came up."""
    launch = a.get("launch_mode", "nohup_bg")
    detect = a.get("detect_process", "")
    port   = a.get("detect_port")

    # Kill conflicts first
    conflicts = a.get("conflicts", [])
    if conflicts:
        kill_conflicts(conflicts)

    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = a.get("log", str(LOGS / f"{a['id']}.log"))

    if launch == "ollama":
        if Path("/Applications/Ollama.app").exists():
            subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=open(log_path, "a"), stderr=subprocess.STDOUT, start_new_session=True
            )
        time.sleep(4)
        return agent_is_running(a)

    if launch == "launchd":
        plist = a.get("launchd_plist", "")
        if plist:
            subprocess.run(["launchctl", "load", f"{Path.home()}/Library/LaunchAgents/{plist}.plist"],
                          capture_output=True)
            time.sleep(2)
            return agent_is_running(a)
        return False

    # nohup_bg — build the command
    script     = a.get("script", "")
    script_dir = Path(a.get("script_dir", str(REX_DIR))).expanduser()
    venv_py    = a.get("venv", PY)
    if not Path(venv_py).exists():
        venv_py = PY

    env_vars = dict(os.environ)
    env_vars.update(a.get("env", {}))
    settings = load_registry().get("settings", {})
    if env_vars.get("TELEGRAM_TOKEN") == "__from_env__":
        env_vars["TELEGRAM_TOKEN"] = settings.get("telegram_token", "")

    cmd = [venv_py, str(script_dir / script)]
    with open(log_path, "a") as logf:
        subprocess.Popen(
            cmd, cwd=str(script_dir), env=env_vars,
            stdout=logf, stderr=logf, start_new_session=True
        )

    time.sleep(3)
    return agent_is_running(a)

# ── Category styling ──────────────────────────────────────────────────────────
CATEGORY_COLOR = {
    "assistant": CYN,
    "service":   GRN,
    "llm":       YEL,
    "daemon":    GRY,
}

def category_label(cat: str) -> str:
    col = CATEGORY_COLOR.get(cat, R)
    return f"{col}{cat.upper():<10}{R}"

# ── Status command ─────────────────────────────────────────────────────────────
def cmd_status(start_stopped: bool = False, start_required_only: bool = True,
               force: bool = False, show_only: bool = False):
    reg = load_registry()
    agents = reg.get("agents", [])

    now = datetime.now().strftime("%a %b %-d  %H:%M")
    print(f"\n{CYN}{BLD}╔══════════════════════════════════════════════════════╗{R}")
    print(f"{CYN}{BLD}║  🦖  GOJ/REX Agent Status              {DIM}{now}{R}{CYN}{BLD}  ║{R}")
    print(f"{CYN}{BLD}╚══════════════════════════════════════════════════════╝{R}\n")

    statuses = {}
    any_down = False
    any_required_down = False

    # ── Check all agents ──────────────────────────────────────────────────────
    prev_cat = None
    for a in agents:
        cat = a.get("category", "service")
        if cat != prev_cat:
            print(f"  {DIM}{category_label(cat)}{R}")
            prev_cat = cat

        running  = agent_is_running(a)
        required = a.get("required", False)
        statuses[a["id"]] = running

        if not running:
            any_down = True
            if required:
                any_required_down = True

        # Icon
        if running:
            icon = f"{GRN}●{R}"
        elif required:
            icon = f"{RED}✗{R}"
        else:
            icon = f"{YEL}○{R}"

        # Detail
        port = a.get("detect_port")
        if running and port:
            detail = f"{GRY}→ http://localhost:{port}{R}"
        elif running:
            detail = f"{GRY}running{R}"
        elif required:
            detail = f"{RED}DOWN{R}"
        else:
            detail = f"{YEL}stopped{R}"

        tag_str = " ".join(f"{GRY}[{t}]{R}" for t in a.get("tags", [])[:3])
        name    = a.get("name", a["id"])
        print(f"    {icon}  {BLD}{name:<28}{R}  {detail}  {tag_str}")

        # Extra: Ollama models
        if a.get("detect_process") == "ollama" and running:
            _, models = ollama_running()
            if models:
                model_str = "  ".join(f"{GRN}{m}{R}" for m in models)
                print(f"         {DIM}Models: {model_str}{R}")

    # ── Gmail watcher ─────────────────────────────────────────────────────────
    print(f"\n  {DIM}{'DAEMON':<10}{R}")
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    if "com.rex.pdf-watcher" in r.stdout:
        print(f"    {GRN}●{R}  {BLD}{'Gmail PDF Watcher':<28}{R}  {GRY}every 10 min (launchd){R}  {GRY}[gmail] [auto-ingest]{R}")
    else:
        print(f"    {YEL}○{R}  {BLD}{'Gmail PDF Watcher':<28}{R}  {YEL}not scheduled{R}  {GRY}run SETUP_GMAIL.command to activate{R}")

    print(f"\n  {DIM}Python: {PY}{R}")
    print()

    if not any_down and not force:
        print(f"  {GRN}{BLD}✅  All agents running.{R}")
        print()
        return 0

    if show_only:
        if any_required_down:
            print(f"  {RED}⚠  Some required agents are DOWN.{R}  {YEL}Type:  begin --start{R}")
        else:
            print(f"  {YEL}Some optional agents stopped.{R}  {GRY}Type:  begin --start  to start all{R}")
        print()
        return 1

    # ── Offer to start ─────────────────────────────────────────────────────────
    if not start_stopped:
        try:
            ans = input(f"  {WHT}Start stopped agents? [Y/n] {R}").strip() or "y"
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if not ans.lower().startswith("y"):
            print(f"\n  {GRY}Skipped. Type  begin --start  any time.{R}\n")
            return 1

    print(f"\n  {BLD}Starting agents...{R}\n")

    for a in agents:
        running  = statuses[a["id"]]
        required = a.get("required", False)
        name     = a.get("name", a["id"])
        cat      = a.get("category", "service")

        # Skip: assistant non-required, running, or not needed
        if not force and running:
            continue
        if not force and not required and not start_stopped:
            continue
        # Never auto-start the GHS private bot (it conflicts with GOJ)
        if a["id"] in ("rexxie_private", "rexxie_employee", "rexxie_admin"):
            continue

        if force and running:
            detect = a.get("detect_process", "")
            if detect and detect != "ollama":
                r = subprocess.run(["pgrep", "-f", detect], capture_output=True, text=True)
                for pid in r.stdout.strip().splitlines():
                    try: os.kill(int(pid), signal.SIGTERM)
                    except: pass
                time.sleep(1)

        print(f"  {YEL}⏳{R}  {name} — starting...", end="", flush=True)
        ok = start_agent(a)
        if ok:
            print(f"\r  {GRN}✓{R}  {name} — started     ")
        else:
            log_path = a.get("log", str(LOGS / f"{a['id']}.log"))
            print(f"\r  {RED}✗{R}  {name} — failed  (check {log_path})")

    print(f"\n  {GRY}Done. Type  begin --check  to verify.{R}\n")
    return 0

# ── Autocheck (one-liner for terminal open) ────────────────────────────────────
def cmd_autocheck():
    reg    = load_registry()
    agents = reg.get("agents", [])

    # Only check the critical ones for the one-liner
    critical = {a["id"]: a for a in agents if a.get("required", False)}
    down = [a["name"] for aid, a in critical.items() if not agent_is_running(a)]

    if not down:
        print(f"{GRN}🦖 REX: all required agents running{R}  {GRY}— type 'begin' for full status{R}")
    else:
        names = ", ".join(down)
        print(f"{RED}🦖 REX: DOWN →{R} {YEL}{names}{R}  {GRY}— type 'begin --start' to fix{R}")

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "autocheck":
        cmd_autocheck()
    elif cmd == "status":
        sys.exit(cmd_status(start_stopped=False, show_only=True))
    elif cmd == "check":
        sys.exit(cmd_status(start_stopped=False, show_only=True))
    elif cmd == "start":
        sys.exit(cmd_status(start_stopped=False, start_required_only=True, show_only=False))
    elif cmd == "start-all":
        sys.exit(cmd_status(start_stopped=True, start_required_only=False, show_only=False))
    elif cmd == "force":
        sys.exit(cmd_status(start_stopped=True, force=True, show_only=False))
    else:
        print(f"Usage: begin_check.py [status|check|start|start-all|force|autocheck]")
        sys.exit(1)
