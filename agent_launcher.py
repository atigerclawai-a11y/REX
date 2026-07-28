#!/usr/bin/env python3
"""
GOJ/GHS Local Agent Launcher  v1.2
────────────────────────────────────
Type `agent` in Terminal to pop this up.

Fixes in v1.2:
  - Only kills an agent if the NEW one requires the same process (Rexxie lane switch)
  - Services/daemons never kill other running agents
  - Dashboard / web services print clickable URL in the list
  - Categories: ASSISTANTS | SERVICES | DAEMONS | TOOLS
  - Smarter display with ports, URLs, model names visible at a glance
"""

import json, os, sys, signal, socket, subprocess, time, webbrowser
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
REX_DIR     = Path.home() / "Desktop" / "REX"
REGISTRY    = REX_DIR / "agent_registry.json"
VENV_PYTHON = Path("/Users/mainsobhelper/debate-chamber/.venv/bin/python3")

# ── ANSI ──────────────────────────────────────────────────────────────────────
R   = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
GRN = "\033[92m"; YEL = "\033[93m"; RED = "\033[91m"
CYN = "\033[96m"; MAG = "\033[95m"; BLU = "\033[94m"; GRY = "\033[90m"

# ── Load registry ─────────────────────────────────────────────────────────────
def load_registry():
    if not REGISTRY.exists():
        print(f"{RED}ERROR: Registry not found at {REGISTRY}{R}")
        sys.exit(1)
    with open(REGISTRY) as f:
        return json.load(f)

# ── Status probes ─────────────────────────────────────────────────────────────
def proc_running(script_name: str):
    if not script_name or script_name == "__ollama__":
        return False, None
    r = subprocess.run(["pgrep", "-f", script_name], capture_output=True, text=True)
    pids = [int(p) for p in r.stdout.strip().splitlines() if p.strip().isdigit() and int(p) != os.getpid()]
    return (True, pids[0]) if pids else (False, None)

def port_open(port: int):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except: return False

def ollama_status():
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "2", "http://localhost:11434/api/tags"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            models = [m["name"] for m in json.loads(r.stdout).get("models", [])]
            return {"running": True, "models": models}
    except: pass
    return {"running": False, "models": []}

def agent_status(a: dict):
    running, pid = proc_running(a.get("detect_process", ""))
    if not running and a.get("detect_port"):
        running = port_open(a["detect_port"])
    if not running and a.get("launch_mode") == "ollama":
        running = port_open(11434)
    if not running and a.get("launch_mode") == "launchd":
        label = a.get("launchd_plist", "")
        if label:
            r = subprocess.run(["launchctl", "list", label], capture_output=True, text=True)
            running = r.returncode == 0
    return {"running": running, "pid": pid}

# ── Helpers ───────────────────────────────────────────────────────────────────
def clear(): os.system("clear")

def extra_info(a: dict, status: dict) -> str:
    """One-line detail shown under an agent row."""
    parts = []
    if status.get("pid"):       parts.append(f"pid:{status['pid']}")
    if a.get("detect_port"):    parts.append(f"http://localhost:{a['detect_port']}")
    env = a.get("env", {})
    if env.get("OLLAMA_MODEL"): parts.append(env["OLLAMA_MODEL"])
    if env.get("DEFAULT_MODE"): parts.append(f"mode:{env['DEFAULT_MODE']}")
    if a.get("ollama_model"):   parts.append(a["ollama_model"])
    return "  ".join(parts)

def tag_str(a: dict, n=3):
    return " ".join(f"{GRY}[{t}]{R}" for t in a.get("tags", [])[:n])

# ── Rendering ─────────────────────────────────────────────────────────────────
def render_header(ollama: dict):
    ts = datetime.now().strftime("%a %b %d  %H:%M")
    if ollama["running"]:
        models = "  ".join(f"{GRN}{m}{R}" for m in ollama["models"]) or f"{GRN}running{R}"
        ol = f"{GRN}● Ollama{R}  {models}"
    else:
        ol = f"{RED}✗ Ollama OFF{R}  {DIM}— start-all.command to fix{R}"
    print(f"""
{CYN}{B}╔═══════════════════════════════════════════════════════════╗{R}
{CYN}{B}║   🦖  LOCAL AGENT LAUNCHER  ·  KATO  ·  GHS / GOJ        ║{R}
{CYN}{B}╚═══════════════════════════════════════════════════════════╝{R}
  {GRY}{ts}{R}   {ol}
""")

def section(title: str):
    print(f"  {B}{title}{R}")
    print(f"  {GRY}{'─'*57}{R}")

def agent_row(idx: int, a: dict, status: dict):
    running = status["running"]
    dot   = f"{GRN}●{R}" if running else f"{GRY}○{R}"
    badge = f"{GRN}RUNNING{R}" if running else f"{GRY}stopped{R}"
    extra = extra_info(a, status)
    print(f"  {dot} {B}[{idx}]{R} {a['name']:<30} {badge}")
    if extra:
        print(f"         {CYN}{extra}{R}")
    print(f"         {DIM}{a['subtitle']}{R}")
    print()

def tool_row(idx: int, t: dict):
    print(f"  {YEL}▶{R} {B}[{idx}]{R} {t['name']:<30} {DIM}{t['subtitle']}{R}")

def render_footer(max_idx: int):
    print(f"\n  {GRY}{'─'*57}{R}")
    print(f"  {DIM}[1–{max_idx}] select   [s] stop one   [b] backup all   [q] quit{R}\n")

# ── Index builder ─────────────────────────────────────────────────────────────
CATEGORIES = [
    ("ASSISTANTS",  ["assistant"]),
    ("SERVICES",    ["service", "llm"]),
    ("DAEMONS",     ["daemon"]),
]

def build_index(agents, tools, statuses):
    """Returns ordered list of items and a {n → item} map."""
    ordered = []
    for _, cats in CATEGORIES:
        for a in agents:
            if a.get("category") in cats:
                ordered.append(a)
    for t in tools:
        ordered.append(t)
    idx_map = {i+1: item for i, item in enumerate(ordered)}
    return ordered, idx_map

def render_all(agents, tools, statuses):
    rendered_ids = set()
    idx = 1

    for cat_label, cats in CATEGORIES:
        cat_agents = [a for a in agents if a.get("category") in cats]
        if not cat_agents: continue
        section(cat_label)
        for a in cat_agents:
            agent_row(idx, a, statuses[a["id"]])
            rendered_ids.add(a["id"])
            idx += 1

    # Any uncategorized agents
    others = [a for a in agents if a["id"] not in rendered_ids]
    if others:
        section("OTHER")
        for a in others:
            agent_row(idx, a, statuses[a["id"]])
            idx += 1

    section("QUICK TOOLS")
    for t in tools:
        tool_row(idx, t)
        idx += 1

    render_footer(idx - 1)
    return idx - 1

# ── Backup & switch ───────────────────────────────────────────────────────────
def backup_and_confirm(conflict_agents: list[dict]) -> bool:
    """Only called when launching an agent that shares a process with running agents."""
    sys.path.insert(0, str(REX_DIR))
    try:
        import session_backup as sb
    except ImportError:
        sb = None

    print(f"\n  {YEL}⚠  Switching will restart:{R}")
    for a in conflict_agents:
        print(f"     {GRN}● {a['name']}{R}  {GRY}(same process){R}")

    if sb:
        for a in conflict_agents:
            if a.get("backup_on_switch") and a.get("db"):
                print(f"\n  {CYN}Backing up: {a['name']}...{R}")
                sb.backup_agent(a)

    print(f"\n  {YEL}Restart and switch? [y/N]{R} ", end="", flush=True)
    return input().strip().lower() == "y"

def kill_agent(a: dict, status: dict):
    pid = status.get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  {YEL}Stopped {a['name']} (pid {pid}){R}")
            time.sleep(0.8)
            return
        except ProcessLookupError: pass
    script = a.get("detect_process", "")
    if script:
        subprocess.run(["pkill", "-f", script], capture_output=True)
        print(f"  {YEL}Stopped {a['name']}{R}")
        time.sleep(0.8)

# ── Launch ────────────────────────────────────────────────────────────────────
def launch_agent(a: dict, reg: dict):
    python   = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    script   = a["script"]
    work_dir = Path(a["script_dir"]).expanduser()
    mode     = a.get("launch_mode", "foreground")
    logs_dir = Path(reg["settings"]["logs_dir"]).expanduser()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(a.get("log", str(logs_dir / f"{a['id']}.log"))).expanduser()

    env = os.environ.copy()
    for k, v in a.get("env", {}).items():
        if v != "__from_env__":
            env[k] = v

    print(f"\n  {GRN}▶ Launching: {B}{a['name']}{R}")
    print(f"  {DIM}{a['description']}{R}\n")

    if mode == "foreground":
        try:
            subprocess.run([python, script], cwd=work_dir, env=env)
        except KeyboardInterrupt:
            print(f"\n  {YEL}Interrupted.{R}")

    elif mode == "nohup_bg":
        with open(log_path, "a") as lf:
            subprocess.Popen([python, script], cwd=work_dir, env=env,
                             stdout=lf, stderr=lf, start_new_session=True)
        time.sleep(1.5)
        running, pid = proc_running(a.get("detect_process", script))
        if running:
            print(f"  {GRN}✓ Running  (pid {pid}){R}")
        else:
            print(f"  {RED}✗ Crashed? Check log:{R}  {log_path}")

    elif mode == "ollama":
        if Path("/Applications/Ollama.app").exists():
            subprocess.run(["open", "-a", "Ollama"])
            print(f"  {GRN}✓ Ollama.app opened{R}")
        elif subprocess.run(["which", "ollama"], capture_output=True).returncode == 0:
            with open(log_path, "a") as lf:
                subprocess.Popen(["ollama", "serve"], stdout=lf, stderr=lf, start_new_session=True)
            print(f"  {GRN}✓ ollama serve started{R}")
        else:
            print(f"  {RED}✗ Ollama not installed — https://ollama.com{R}")
        time.sleep(2)
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if r.stdout:
            print(f"\n  {CYN}Installed models:{R}")
            for line in r.stdout.strip().splitlines()[1:]:
                print(f"    {GRY}{line}{R}")

    elif mode == "launchd":
        label = a.get("launchd_plist", "")
        if label:
            subprocess.run(["launchctl", "start", label])
            print(f"  {GRN}✓ launchctl start {label}{R}")

    # Always print URL for web services
    port = a.get("detect_port")
    if port and port not in (11434,):
        url = f"http://localhost:{port}"
        print(f"\n  {CYN}🌐 Open in browser: {B}{url}{R}")
        time.sleep(0.5)
        try:
            webbrowser.open(url)
            print(f"  {GRY}(opening automatically...){R}")
        except: pass

def launch_tool(t: dict):
    python   = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    work_dir = Path(t["script_dir"]).expanduser()
    print(f"\n  {YEL}▶ Running: {B}{t['name']}{R}")
    print(f"  {DIM}{t['description']}{R}\n")
    try:
        subprocess.run([python, t["script"]], cwd=work_dir)
    except KeyboardInterrupt:
        print(f"\n  {YEL}Interrupted.{R}")
    input(f"\n  {DIM}Press Enter to return to launcher...{R}")

# ── Stop-one flow ─────────────────────────────────────────────────────────────
def prompt_stop_one(agents, statuses, idx_map):
    running = [(i, a) for i, a in idx_map.items()
               if "detect_process" in a and statuses.get(a.get("id", ""), {}).get("running")]
    if not running:
        print(f"\n  {GRY}No agents are currently running.{R}")
        input(f"  {DIM}Press Enter...{R}")
        return
    print(f"\n  {YEL}Which agent to stop?{R}")
    for i, a in running:
        print(f"    [{i}] {a['name']}")
    print(f"    [Enter] cancel")
    print(f"\n  Select: ", end="", flush=True)
    choice = input().strip()
    if choice.isdigit():
        n = int(choice)
        if n in idx_map and "detect_process" in idx_map[n]:
            a = idx_map[n]
            st = statuses.get(a.get("id", ""), {})
            if st.get("running"):
                kill_agent(a, st)
                print(f"  {GRN}Stopped.{R}")
            else:
                print(f"  {GRY}{a['name']} is not running.{R}")
    time.sleep(0.5)

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    reg    = load_registry()
    agents = reg.get("agents", [])
    tools  = reg.get("tools", [])

    while True:
        statuses  = {a["id"]: agent_status(a) for a in agents}
        ol        = ollama_status()
        ordered, idx_map = build_index(agents, tools, statuses)

        clear()
        render_header(ol)
        max_idx = render_all(agents, tools, statuses)

        print(f"  {B}Select: {R}", end="", flush=True)
        try:
            choice = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {GRY}bye.{R}"); break

        if choice == "q":
            print(f"\n  {GRY}bye.{R}"); break

        elif choice == "b":
            sys.path.insert(0, str(REX_DIR))
            try:
                import session_backup as sb
                print(f"\n  {CYN}Backing up all sessions...{R}")
                for a in agents:
                    if a.get("backup_on_switch") and a.get("db"):
                        sb.backup_agent(a)
                print(f"  {GRN}Done.{R}")
            except ImportError:
                print(f"  {RED}session_backup.py not found{R}")
            input(f"\n  {DIM}Press Enter...{R}")

        elif choice == "s":
            prompt_stop_one(agents, statuses, idx_map)

        elif choice.isdigit():
            n = int(choice)
            if n not in idx_map:
                print(f"  {RED}Invalid — choose 1–{max_idx}{R}")
                time.sleep(0.8); continue

            item = idx_map[n]

            # ── TOOL ──────────────────────────────────────────────────────────
            is_tool = "id" not in item or item.get("launch_mode") == "foreground"
            if is_tool:
                launch_tool(item)
                continue

            # ── AGENT ─────────────────────────────────────────────────────────
            target = item
            target_id     = target["id"]
            target_status = statuses.get(target_id, {})
            target_script = target.get("detect_process", "")

            # Already running → show options
            if target_status.get("running"):
                port = target.get("detect_port")
                url  = f"http://localhost:{port}" if port and port != 11434 else ""
                print(f"\n  {GRN}● {target['name']} is already running.{R}")
                if url:
                    print(f"  {CYN}🌐 {url}{R}")
                    try: webbrowser.open(url)
                    except: pass
                print(f"\n  {DIM}[r] restart   [s] stop   [Enter] back{R}  ", end="", flush=True)
                sub = input().strip().lower()
                if sub == "s":
                    kill_agent(target, target_status)
                elif sub == "r":
                    kill_agent(target, target_status)
                    time.sleep(0.5)
                    launch_agent(target, reg)
                    input(f"\n  {DIM}Press Enter to continue...{R}")
                continue

            # ── CONFLICT CHECK ─────────────────────────────────────────────────
            # Only stop agents that share the SAME script (e.g. Rexxie lane switch)
            # Never stop unrelated agents (dashboard, scheduler, etc.)
            conflicts = [a for a in agents
                         if a["id"] != target_id
                         and statuses[a["id"]]["running"]
                         and a.get("detect_process") == target_script
                         and target_script not in ("", None)]

            if conflicts:
                confirmed = backup_and_confirm(conflicts)
                if not confirmed:
                    print(f"  {GRY}Cancelled.{R}")
                    time.sleep(0.6); continue
                for a in conflicts:
                    kill_agent(a, statuses[a["id"]])
                time.sleep(0.4)

            launch_agent(target, reg)
            input(f"\n  {DIM}Press Enter to continue...{R}")

        else:
            time.sleep(0.3)

if __name__ == "__main__":
    main()
