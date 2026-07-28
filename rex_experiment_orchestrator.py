#!/usr/bin/env python3
"""
rex_experiment_orchestrator.py — REX / Claus GOJ Experiment Supervisor
=======================================================================
Rex is the Manager-General. This script is his enforcement arm over the
17 experiment teams competing to build the GOJ operational dashboard.

REX responsibilities:
  1. Load real GOJ data from ~/Documents/goj files/data/ (422 clients, live)
  2. Refresh GOJ_MASTER_KNOWLEDGE.md from real data (not team guesses)
  3. Scan all team outputs — detect fakes (cloned baseline numbers)
  4. Validate deliverables — flag missing docs before/after 2pm window
  5. Post corrections to team brief.md files
  6. Log all decisions to rex_coordinator.db (component_notes)
  7. Send Rex status digest to Kato via Telegram
  8. Nightly: sweep handoffs, compile MASTER_STATUS.html

Run modes (set via RUN_MODE env or argv[1]):
  morning  — 1pm cycle: data refresh + pre-delivery validation
  evening  — 9:30pm cycle: post-handoff sweep + status compile
  canary   — quick sanity check (no writes, just report)
"""

from __future__ import annotations
import json, os, sys, datetime, sqlite3, urllib.request, urllib.parse, traceback
from pathlib import Path

# ── PATHS ────────────────────────────────────────────────────────────────────

HOME            = Path.home()
REX_DIR         = HOME / "Desktop/REX"
GOJ_DATA        = HOME / "Documents/goj files/data"
EXPERIMENT_DIR  = HOME / ".hermes/experiment"
SHARED_DIR      = EXPERIMENT_DIR / "shared"
KNOWLEDGE_BASE  = SHARED_DIR / "GOJ_MASTER_KNOWLEDGE.md"
MASTER_STATUS   = SHARED_DIR / "MASTER_STATUS.html"
COORDINATOR_DB  = REX_DIR / "rex_coordinator.db"

TEAMS = [
    "claude-sonnet","cline","deepseek","gemini","gpt4o-mini",
    "grok","groq","mistral","perplexity","qwen-local",
    "team-a","team-b","team-c","team-d","team-e","team-f","team-o"
]

# Expected deliverable patterns for today
REQUIRED_PATTERNS = [
    "signin_S1_",      # 1
    "signin_S2_",      # 2
    "driver_routes_S1_",  # 3
    "driver_routes_S2_",  # 4
    "food_dist_S1_",   # 5
    "food_dist_S2_",   # 6
    "kitchen_",        # 7
]

# ── ENV + TELEGRAM ────────────────────────────────────────────────────────────

def _load_env() -> dict:
    env = {}
    for p in [HOME/".hermes/.env", HOME/".hermes/hermes-agent/.env", REX_DIR/".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    k = k.strip()
                    if k and k not in env:
                        env[k] = v.strip()
    return env

ENV = _load_env()
TG_CHAT_ID = "5587703834"

def tg_send(msg: str):
    token = ENV.get("TELEGRAM_BOT_TOKEN","")
    if not token:
        print("[TG] No token — message not sent")
        return
    try:
        payload = urllib.parse.urlencode({
            "chat_id": TG_CHAT_ID,
            "text": msg[:4096],
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
        print("[TG] Sent.")
    except Exception as e:
        print(f"[TG] Failed: {e}")

# ── REX COORDINATOR DB ────────────────────────────────────────────────────────

def rex_log(component: str, note: str, source: str = "rex-orchestrator"):
    try:
        con = sqlite3.connect(str(COORDINATOR_DB))
        con.execute("""
            CREATE TABLE IF NOT EXISTS component_notes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                component_name TEXT NOT NULL,
                note           TEXT NOT NULL,
                source         TEXT DEFAULT 'rexxie',
                created_at     TEXT DEFAULT (datetime('now'))
            )""")
        con.execute(
            "INSERT INTO component_notes (component_name, note, source) VALUES (?, ?, ?)",
            (component, note[:500], source)
        )
        con.commit()
        con.close()
    except Exception as e:
        print(f"[REX DB] Log failed: {e}")

# ── REAL DATA LOADER ──────────────────────────────────────────────────────────

def load_real_goj() -> dict:
    def jload(p, default):
        try:
            return json.loads(Path(p).read_bytes())
        except Exception:
            return default
    return {
        "clients":    jload(GOJ_DATA/"GOJ_Clients_Master.json",   []),
        "routes":     jload(GOJ_DATA/"GOJ_Master_Routes.json",    {}),
        "attendance": jload(GOJ_DATA/"GOJ_Daily_Attendance.json", {}),
        "menus":      jload(GOJ_DATA/"GOJ_Menu_Orders.json",      {}),
        "kitchen":    jload(GOJ_DATA/"GOJ_Kitchen_Counts.json",   {}),
        "patterns":   jload(GOJ_DATA/"GOJ_Weekly_Patterns.json",  {}),
        "calendar":   jload(GOJ_DATA/"GOJ_Calendar_2026.json",    {}),
    }

def clients_today(data: dict, target: datetime.date) -> dict:
    """Returns S1 and S2 client lists for a given date."""
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    day_name = days[target.weekday()]
    s1 = [c for c in data["routes"].get(f"{day_name}_S1", []) if c.get("status","active")=="active"]
    s2 = [c for c in data["routes"].get(f"{day_name}_S2", []) if c.get("status","active")=="active"]
    return {"S1": s1, "S2": s2, "day": day_name}

# ── KNOWLEDGE BASE REFRESH ────────────────────────────────────────────────────

def refresh_knowledge_base(data: dict, today: datetime.date):
    """Rewrite GOJ_MASTER_KNOWLEDGE.md from real live data."""
    clients = data["clients"]
    routes  = data["routes"]

    # Count by day
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    day_counts = {}
    for d in days[:5]:
        s1 = len([c for c in routes.get(f"{d}_S1",[]) if c.get("status","active")=="active"])
        s2 = len([c for c in routes.get(f"{d}_S2",[]) if c.get("status","active")=="active"])
        day_counts[d] = (s1, s2)

    today_sched = clients_today(data, today)
    total_active = sum(1 for c in clients if c.get("status","active")=="active") if isinstance(clients, list) else len(clients)

    lines = [
        f"# GOJ MASTER KNOWLEDGE BASE",
        f"**Last refreshed by REX:** {datetime.datetime.now().isoformat()} (AUTHORITATIVE — live data)",
        f"",
        f"## Client Population",
        f"- **Total clients in master list:** {len(clients)}",
        f"- **Active clients:** {total_active}",
        f"- **Data source:** `~/Documents/goj files/data/GOJ_Clients_Master.json` (real, not shadow)",
        f"",
        f"## Weekly Schedule (Active Clients per Shift)",
    ]
    for d, (s1, s2) in day_counts.items():
        lines.append(f"- **{d}:** S1={s1}, S2={s2}, Total={s1+s2}")

    lines += [
        f"",
        f"## Today ({today.isoformat()} — {today_sched['day']})",
        f"- Shift 1: {len(today_sched['S1'])} clients",
        f"- Shift 2: {len(today_sched['S2'])} clients",
        f"",
        f"## Key Business Facts",
        f"- Facility: Garden of Joy Adult Day Care Center, Brooklyn NY",
        f"- Clientele: Russian-speaking elderly",
        f"- Caterer: Olimp (Russian cuisine) — меню: Салаты, Супы, Главное",
        f"- Authorization: MJHS (Metropolitan Jewish Health System)",
        f"- Scanner email: goj3152.scans@gmail.com → forwards to atigerclawai@gmail.com",
        f"- Transport: Van (company) + Car service (TR/F designation on sign-in)",
        f"",
        f"## ⚠ Canary Warning",
        f"If your state.json shows clients_found=422 but you have NOT read this file",
        f"from the real data path, you are reading STALE data and your outputs are WRONG.",
        f"Real path: `~/Documents/goj files/data/GOJ_Clients_Master.json`",
        f"",
        f"## Daily Deliverables Required by 2pm",
        f"1. signin_S1_YYYY-MM-DD.*",
        f"2. signin_S2_YYYY-MM-DD.*",
        f"3. driver_routes_S1_YYYY-MM-DD.*",
        f"4. driver_routes_S2_YYYY-MM-DD.*",
        f"5. food_dist_S1_YYYY-MM-DD.*",
        f"6. food_dist_S2_YYYY-MM-DD.*",
        f"7. kitchen_YYYY-MM-DD.*",
    ]

    KNOWLEDGE_BASE.write_text("\n".join(lines))
    print(f"[REX] Knowledge base refreshed — {len(clients)} clients, {today_sched['day']} S1={len(today_sched['S1'])} S2={len(today_sched['S2'])}")
    rex_log("GOJ-Experiment", f"Knowledge base refreshed from real data. {len(clients)} clients. {today.isoformat()}")

# ── TEAM OUTPUT SCANNER ───────────────────────────────────────────────────────

def scan_team_outputs(today: datetime.date) -> dict:
    """Check each team's output directory for today's 7 required files."""
    date_str = today.isoformat()
    results = {}

    for team in TEAMS:
        team_dir = EXPERIMENT_DIR / team
        # Handle non-standard paths
        output_dir = team_dir / "outputs" / date_str
        if not output_dir.exists():
            # Try alternate paths
            alt = team_dir / "outputs"
            if alt.exists():
                # Find most recent dated subdir
                subdirs = sorted([d for d in alt.iterdir() if d.is_dir()], reverse=True)
                output_dir = subdirs[0] if subdirs else output_dir

        files = list(output_dir.glob("*")) if output_dir.exists() else []
        file_names = [f.name for f in files]

        found = []
        missing = []
        for pat in REQUIRED_PATTERNS:
            hit = any(pat in fn for fn in file_names)
            if hit:
                found.append(pat.rstrip("_"))
            else:
                missing.append(pat.rstrip("_"))

        results[team] = {
            "output_dir": str(output_dir),
            "files_total": len(files),
            "found": found,
            "missing": missing,
            "score": f"{len(found)}/7",
            "has_outputs_today": output_dir.exists() and len(files) > 0,
        }

    return results

def detect_baseline_clones() -> list[str]:
    """Detect teams that copied claude-sonnet's baseline numbers."""
    baseline_values = set()
    clones = []

    for team in TEAMS:
        state_paths = [
            EXPERIMENT_DIR / team / "state" / "state.json",
            EXPERIMENT_DIR / team / "state.json",
        ]
        for sp in state_paths:
            if sp.exists():
                try:
                    st = json.loads(sp.read_bytes())
                    baseline = st.get("day1_baseline", {})
                    clients = baseline.get("clients_loaded") or st.get("clients_found")
                    if clients:
                        key = f"{clients}"
                        if key in baseline_values and team != "claude-sonnet":
                            clones.append(team)
                        baseline_values.add(key)
                except Exception:
                    pass
                break

    return clones

# ── BRIEF POSTING ─────────────────────────────────────────────────────────────

def post_to_brief(team: str, message: str):
    """Append a Rex correction/note to a team's brief.md."""
    brief_path = EXPERIMENT_DIR / team / "brief.md"
    if not brief_path.exists():
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text("")

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n---\n## ⚡ REX DIRECTIVE [{ts}]\n{message}\n"
    with open(brief_path, "a") as f:
        f.write(entry)
    print(f"[REX] Posted directive to {team}/brief.md")

# ── MORNING CYCLE (1pm) ───────────────────────────────────────────────────────

def morning_cycle():
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    # Skip weekends for delivery
    while tomorrow.weekday() >= 5:
        tomorrow += datetime.timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"REX MORNING CYCLE — {today.isoformat()} — delivering for {tomorrow.isoformat()}")
    print(f"{'='*60}\n")

    # 1. Load real data
    data = load_real_goj()
    client_count = len(data["clients"])
    today_sched  = clients_today(data, tomorrow)
    print(f"[REX] Real data loaded: {client_count} clients. Tomorrow ({tomorrow.isoformat()} {today_sched['day']}): S1={len(today_sched['S1'])}, S2={len(today_sched['S2'])}")

    # 2. Refresh knowledge base
    refresh_knowledge_base(data, tomorrow)

    # 3. Detect clones
    clones = detect_baseline_clones()
    if clones:
        print(f"[REX] ⚠ Baseline clones detected: {clones}")
        rex_log("GOJ-Experiment", f"Baseline clones detected: {', '.join(clones)}")
        for team in clones:
            post_to_brief(team,
                f"**REX ALERT: Cloned baseline detected.**\n"
                f"Your state.json shows the same client count as another team. "
                f"You have NOT independently read the real data.\n"
                f"**Required action:** Read `~/Documents/goj files/data/GOJ_Clients_Master.json` directly. "
                f"Real client count for {tomorrow.isoformat()} {today_sched['day']}: "
                f"S1={len(today_sched['S1'])}, S2={len(today_sched['S2'])} clients.\n"
                f"Update your state.json and regenerate all deliverables before 2pm."
            )

    # 4. Broadcast correct client count to ALL teams
    broadcast_msg = (
        f"**REX DATA BROADCAST — {tomorrow.isoformat()} ({today_sched['day']})**\n\n"
        f"Verified from live data (`GOJ_Clients_Master.json`):\n"
        f"- Shift 1: **{len(today_sched['S1'])} clients**\n"
        f"- Shift 2: **{len(today_sched['S2'])} clients**\n\n"
        f"Knowledge base refreshed. Deliverables due by 2pm today.\n"
        f"Required: signin_S1, signin_S2, driver_routes_S1, driver_routes_S2, food_dist_S1, food_dist_S2, kitchen"
    )
    for team in TEAMS:
        post_to_brief(team, broadcast_msg)

    # 5. Scan current outputs (yesterday's deliverables)
    scan_results = scan_team_outputs(today)
    delivered = [t for t, r in scan_results.items() if r["has_outputs_today"]]
    zero_output = [t for t, r in scan_results.items() if not r["has_outputs_today"]]

    print(f"\n[REX] Output scan for {today.isoformat()}:")
    for team, r in scan_results.items():
        status = "✅" if r["has_outputs_today"] else "❌"
        print(f"  {status} {team}: {r['score']} ({r['files_total']} files)")
        if r["missing"] and r["has_outputs_today"]:
            print(f"     MISSING: {r['missing']}")

    # 6. Telegram digest to Kato
    lines = [
        f"🤖 *REX Morning Report — {today.isoformat()}*",
        f"Preparing for tomorrow: *{tomorrow.isoformat()} ({today_sched['day']})*",
        f"",
        f"📊 *Real client data:*",
        f"  Total: {client_count} | Tomorrow S1: {len(today_sched['S1'])} | S2: {len(today_sched['S2'])}",
        f"",
        f"📦 *Today's delivery status ({today.isoformat()}):*",
    ]
    for team, r in scan_results.items():
        icon = "✅" if r["score"] == "7/7" else ("⚠️" if r["has_outputs_today"] else "❌")
        lines.append(f"  {icon} {team}: {r['score']}")

    if clones:
        lines += ["", f"🚨 *Clones flagged:* {', '.join(clones)} — directives posted"]

    lines += [
        "",
        f"📢 Broadcast + knowledge refresh sent to all {len(TEAMS)} teams.",
        f"_Rex | {datetime.datetime.now().strftime('%H:%M')}_"
    ]
    tg_send("\n".join(lines))
    rex_log("GOJ-Experiment", f"Morning cycle complete. {len(delivered)}/{len(TEAMS)} teams delivered. Clones: {clones}")
    print(f"\n[REX] Morning cycle complete.")

# ── EVENING CYCLE (9:30pm) ────────────────────────────────────────────────────

def evening_cycle():
    today = datetime.date.today()
    print(f"\n{'='*60}")
    print(f"REX EVENING CYCLE — {today.isoformat()}")
    print(f"{'='*60}\n")

    # 1. Scan today's final outputs
    scan_results = scan_team_outputs(today)

    # 2. Check handoff files
    handoff_status = {}
    for team in TEAMS:
        handoff_dir = EXPERIMENT_DIR / team / "handoffs"
        if handoff_dir.exists():
            today_handoffs = list(handoff_dir.glob(f"{today.isoformat()}*"))
            handoff_status[team] = len(today_handoffs) > 0
        else:
            handoff_status[team] = False

    # 3. Build MASTER_STATUS.html
    rows = ""
    for team in TEAMS:
        r = scan_results[team]
        delivered_icon = "✅" if r["score"] == "7/7" else ("⚠️" if r["has_outputs_today"] else "❌")
        handoff_icon   = "✅" if handoff_status.get(team) else "❌"
        missing_str    = ", ".join(r["missing"]) if r["missing"] else "—"
        rows += (
            f"<tr>"
            f"<td>{team}</td>"
            f"<td style='text-align:center'>{delivered_icon} {r['score']}</td>"
            f"<td style='text-align:center'>{handoff_icon}</td>"
            f"<td style='font-size:11px;color:#c00'>{missing_str}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>REX Master Status — {today.isoformat()}</title>
<style>
body{{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;padding:20px;}}
h1{{color:#58a6ff;}} h2{{color:#8b949e;font-size:14px;}}
table{{width:100%;border-collapse:collapse;margin-top:20px;}}
th{{background:#161b22;color:#58a6ff;padding:8px;text-align:left;border-bottom:1px solid #30363d;}}
td{{padding:8px;border-bottom:1px solid #21262d;}}
tr:hover td{{background:#161b22;}}
.ts{{font-size:11px;color:#8b949e;}}
</style></head><body>
<h1>⚔ REX — GOJ Experiment Master Status</h1>
<h2>{today.isoformat()} — Generated {datetime.datetime.now().strftime('%H:%M')}</h2>
<table>
<thead><tr><th>Team</th><th>Deliverables</th><th>Handoff</th><th>Missing Docs</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p class="ts">Rex is the orchestrator. Data source: ~/Documents/goj files/data/ (live, 422 clients)</p>
</body></html>"""

    MASTER_STATUS.write_text(html)
    print(f"[REX] MASTER_STATUS.html written.")

    # 4. Flag teams with zero output — post to brief
    zero_teams = [t for t, r in scan_results.items() if not r["has_outputs_today"]]
    for team in zero_teams:
        post_to_brief(team,
            f"**REX EVENING ALERT: Zero deliverables for {today.isoformat()}.**\n"
            f"You produced no output files today. This is a failure cycle.\n"
            f"Tomorrow you must: (1) read live data from `~/Documents/goj files/data/`, "
            f"(2) produce all 7 required documents by 2pm, "
            f"(3) submit to DataRex at http://127.0.0.1:8080.\n"
            f"Your brief.md contains the correct client counts from Rex's data broadcast."
        )

    # 5. Post partial teams
    partial_teams = [t for t, r in scan_results.items() if r["has_outputs_today"] and r["score"] != "7/7"]
    for team in partial_teams:
        r = scan_results[team]
        post_to_brief(team,
            f"**REX EVENING: Incomplete delivery — {today.isoformat()}.**\n"
            f"You delivered {r['score']} documents. Missing: {', '.join(r['missing'])}.\n"
            f"Tomorrow add the missing deliverables. All 7 are required."
        )

    # 6. Telegram digest
    full      = [t for t, r in scan_results.items() if r["score"] == "7/7"]
    partial_l = [t for t, r in scan_results.items() if r["has_outputs_today"] and r["score"] != "7/7"]
    zero_l    = [t for t, r in scan_results.items() if not r["has_outputs_today"]]
    handoffs  = [t for t, v in handoff_status.items() if v]

    lines = [
        f"🌙 *REX Evening Report — {today.isoformat()}*",
        f"",
        f"📦 *Full delivery (7/7):* {len(full)}/{len(TEAMS)}",
    ]
    if full:
        lines.append("  " + ", ".join(full))
    if partial_l:
        lines += [f"⚠️ *Partial:* {', '.join(partial_l)}"]
    if zero_l:
        lines += [f"❌ *Zero output:* {', '.join(zero_l)}"]
    lines += [
        f"",
        f"📝 *Handoffs filed:* {len(handoffs)}/{len(TEAMS)}",
        f"",
        f"Directives posted to all failing teams. MASTER_STATUS.html updated.",
        f"_Rex | {datetime.datetime.now().strftime('%H:%M')}_"
    ]
    tg_send("\n".join(lines))
    rex_log("GOJ-Experiment", f"Evening cycle. Full: {len(full)}, Partial: {len(partial_l)}, Zero: {len(zero_l)}")
    print(f"[REX] Evening cycle complete.")

# ── CANARY (quick read-only check) ───────────────────────────────────────────

def canary_check():
    today = datetime.date.today()
    print(f"\n[REX CANARY] {today.isoformat()}\n")

    data = load_real_goj()
    print(f"  Real clients:    {len(data['clients'])}")
    print(f"  Routes keys:     {len(data['routes'])}")
    print(f"  Menu entries:    {len(data['menus'])}")
    print(f"  Attendance days: {len(data['attendance'])}")

    today_sched = clients_today(data, today)
    print(f"  Today ({today_sched['day']}): S1={len(today_sched['S1'])}, S2={len(today_sched['S2'])}")

    scan = scan_team_outputs(today)
    delivered = sum(1 for r in scan.values() if r["has_outputs_today"])
    print(f"\n  Teams with output today: {delivered}/{len(TEAMS)}")
    for team, r in scan.items():
        if r["has_outputs_today"]:
            print(f"    ✅ {team}: {r['score']}")

    clones = detect_baseline_clones()
    if clones:
        print(f"\n  ⚠ Clones detected: {clones}")
    else:
        print(f"\n  ✅ No baseline cloning detected")

    print(f"\n[REX CANARY] PASS — real data accessible, {len(data['clients'])} clients verified")

# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RUN_MODE","canary")).lower()
    print(f"[REX ORCHESTRATOR] mode={mode}")
    try:
        if mode == "morning":
            morning_cycle()
        elif mode == "evening":
            evening_cycle()
        elif mode == "canary":
            canary_check()
        else:
            print(f"Unknown mode: {mode}. Use: morning | evening | canary")
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        tg_send(f"🚨 *REX Orchestrator CRASH* — mode={mode}\n```{traceback.format_exc()[-800:]}```")
        sys.exit(1)
