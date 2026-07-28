#!/bin/bash
# ====================================================================
#  REX COMMAND CENTER
#  Two UI modes — same backend data:
#
#  Mode A (default): Claude UI — clean terminal, fast, operational
#  Mode B: Executive — rich HTML dashboard, opens in browser
#
#  Usage:
#    Double-click               → Claude UI (terminal)
#    ./COMMAND_CENTER.command --executive   → Executive HTML mode
#    ./COMMAND_CENTER.command --watch       → Auto-refresh every 30s
# ====================================================================

REX="$HOME/Desktop/REX"
MODE="claude"
WATCH=false

for arg in "$@"; do
  case $arg in
    --executive|-e) MODE="executive" ;;
    --watch|-w)     WATCH=true ;;
  esac
done

PY=""
for C in "$REX/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
  [ -f "$C" ] && PY="$C" && break
done
[ -z "$PY" ] && echo "❌ No Python." && exit 1

_SCRIPT="/tmp/cc_runner_$$.py"
cat > "$_SCRIPT" << 'PYEOF'
import sys, os, json, time, subprocess, webbrowser, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / "Desktop" / "REX"))

MODE  = sys.argv[1] if len(sys.argv) > 1 else "claude"
WATCH = sys.argv[2] == "watch" if len(sys.argv) > 2 else False

try:
    from backend.rex_command_center_status import get_status
except ImportError:
    # Minimal fallback if import fails
    def get_status():
        return {"error": "Could not import status module — check backend/ directory"}

# ── ANSI colors ────────────────────────────────────────────────────────────────
R="\033[0;31m"; Y="\033[1;33m"; G="\033[0;32m"; B="\033[0;34m"
C="\033[0;36m"; W="\033[1m"; D="\033[2m"; N="\033[0m"; BG="\033[1;32m"

def clr(text, color): return f"{color}{text}{N}"
def ok(t): return clr(t, G)
def warn(t): return clr(t, Y)
def err(t): return clr(t, R)
def bold(t): return clr(t, W)
def dim(t): return clr(t, D)
def cyan(t): return clr(t, C)

# ── Claude UI (terminal) ───────────────────────────────────────────────────────
def render_claude(d):
    if "error" in d:
        print(err(f"\n❌ Status error: {d['error']}"))
        return

    W_LINE = "═" * 62
    w_line = "─" * 62
    health = d.get("system_health","?")
    health_icon = ok("✅ OK") if health=="ok" else (warn("⚡ WARNING") if health=="warning" else err("🚨 CRITICAL"))

    print(f"\n{bold(W_LINE)}")
    print(f"{bold('  REX COMMAND CENTER')}  {dim(d.get('timestamp','')[:19])}")
    print(f"  Garden of Joy Adult Day Care              {health_icon}")
    print(f"{bold(W_LINE)}")

    # Database
    db = d.get("database", {})
    st = ok("●") if db.get("accessible") else err("✗")
    print(f"\n{cyan('  DATABASE')}")
    print(f"  {st} {dim(str(db.get('path','?'))[-55:])}")
    if db.get("accessible"):
        print(f"  Clients: {bold(str(db.get('active_clients','?')))} active  │  "
              f"Staff: {bold(str(db.get('staff_count','?')))}  │  "
              f"Auths: {bold(str(db.get('auth_count','?')))}")
        print(f"  Attendance: {bold(str(db.get('attendance_count','?')))}  │  "
              f"Menus: {bold(str(db.get('menu_count','?')))}  │  "
              f"Rexxie ideas: {bold(str(db.get('rexxie_ideas','?')))}")
    else:
        print(f"  {err('NOT ACCESSIBLE — ')} {db.get('error','')}")

    # Services
    svc = d.get("services", {})
    print(f"\n{cyan('  SERVICES')}")
    for name, key in [("Rex Backend","rex_backend"),("Rexxie Bot","rexxie_bot"),
                      ("Scheduler","scheduler"),("Flask Dashboard","flask_dashboard")]:
        s = svc.get(key, {})
        status = s.get("status","?")
        icon = ok("●") if status=="running" else (warn("○") if status=="unknown" else err("✗"))
        url = f"  {dim(s.get('url',''))}" if s.get("url") else ""
        print(f"  {icon} {name:<18} {bold(status.upper())}{url}")

    # OCR
    ocr = d.get("ocr", {})
    print(f"\n{cyan('  OCR PIPELINE')}")
    unres = ocr.get("flag_queue_unresolved",0)
    stale = ocr.get("flag_queue_stale_path",0)
    flag_color = ok if unres == 0 else (warn if unres < 10 else err)
    print(f"  Flag queue:  {flag_color(str(unres))} unresolved  ({stale} stale-path)")
    snap = ok("✅ exists") if ocr.get("snapshot_exists") else err("✗ missing")
    schema = ok("✅ ok") if ocr.get("core_schema_ok") else err("✗ missing")
    print(f"  Snapshot:    {snap}  │  Schema:  {schema}")
    pending = ocr.get("drop_zone_pending",0)
    if pending:
        print(f"  {warn(f'⚡ {pending} PDF(s) pending in Scanned docs/')}")
    if ocr.get("last_ocr_log"):
        print(f"  Last run:    {dim(ocr['last_ocr_log'].get('file','?')[:40])}")

    # Dashboard
    print(f"\n{cyan('  DASHBOARD')}")
    dash = d.get("dashboard", {})
    print(f"  {ok('●')} Local Flask     {dim('http://localhost:8080')}  reads local DB ✓")
    print(f"  {err('✗')} Railway GOJ     {warn('DISCONNECTED')}  — uses separate cloud DB")
    print(f"  {warn('○')} FastAPI bridge  {warn('NOT YET CONFIGURED')}  — see START_API_SERVER.command")

    # Quarantine + Ledger
    quar = d.get("quarantine", {})
    led  = d.get("ledger", {})
    print(f"\n{cyan('  CONTROL + VISIBILITY')}")
    print(f"  Quarantine:   {bold(str(quar.get('item_count',0)))} items isolated  "
          f"│  Intake pending:  {bold(str(led.get('intake_pending',0)))}")
    all_p = ok("all 4 present") if led.get("all_present") else warn("some missing")
    print(f"  Ledgers:      {all_p}")
    bk = d.get("backup",{})
    last_bk = bk.get("last_backup") or "none"
    print(f"  Last backup:  {bold(last_bk)}")

    # Security alerts
    alerts = d.get("security_alerts",[])
    if alerts:
        print(f"\n{err('  🚨 SECURITY ALERTS')}")
        for a in alerts:
            icon = err("CRITICAL") if a["level"]=="CRITICAL" else warn(a["level"])
            print(f"  [{icon}] {a['message']}")

    # Manual review
    review = d.get("manual_review",[])
    if review:
        print(f"\n{warn('  📥 MANUAL REVIEW INBOX')}")
        for item in review[:5]:
            print(f"  • {item['file']}")

    print(f"\n{bold(w_line)}")
    print(f"  {dim('ACTIVE_SYSTEM_MANIFEST.json defines authoritative paths')}")
    print(f"  {dim('Run with --executive for browser dashboard')}")
    print(f"{bold(W_LINE)}\n")


# ── Executive HTML mode ────────────────────────────────────────────────────────
def render_executive(d):
    """Generate and open a rich HTML executive dashboard."""
    health = d.get("system_health","?")
    hcolor = {"ok":"#27ae60","warning":"#f39c12","critical":"#e74c3c"}.get(health,"#7f8c8d")
    db = d.get("database",{})
    svc = d.get("services",{})
    ocr = d.get("ocr",{})
    alerts = d.get("security_alerts",[])
    led = d.get("ledger",{})
    quar = d.get("quarantine",{})

    def svc_dot(key):
        s = svc.get(key,{}).get("status","?")
        c = {"running":"#27ae60","stopped":"#e74c3c"}.get(s,"#f39c12")
        return f'<span style="color:{c};font-size:18px">●</span> {s.upper()}'

    alert_html = "".join(f'<div class="alert alert-{a["level"].lower()}">'
                         f'<span class="al-icon">⚠</span> '
                         f'<strong>{a["level"]}</strong> — {a["message"]}</div>' for a in alerts)

    led_rows = "".join(f'<tr><td>{n}</td><td>{i.get("lines",0)} lines</td><td>{i.get("modified","—")}</td></tr>'
                       for n,i in led.get("files",{}).items())

    review_html = "".join(f'<li>{r["file"]}</li>' for r in d.get("manual_review",[])[:10]) or "<li>None pending</li>"

    ts = d.get("timestamp","")[:19].replace("T"," ")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>REX Command Center</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
.hdr{{background:linear-gradient(135deg,#1b3a6b 0%,#0d2347 100%);padding:20px 32px;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #2e5fa3}}
.hdr h1{{font-size:22px;font-weight:700;letter-spacing:1px;color:#fff}}
.hdr .sub{{font-size:13px;color:#8b949e;margin-top:4px}}
.health-badge{{padding:6px 16px;border-radius:20px;font-weight:700;font-size:13px;background:{hcolor};color:#fff}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;padding:20px 32px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px}}
.card h3{{font-size:12px;font-weight:600;letter-spacing:1.5px;color:#8b949e;text-transform:uppercase;margin-bottom:14px}}
.stat-row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #21262d}}
.stat-row:last-child{{border-bottom:none}}
.stat-val{{font-size:20px;font-weight:700;color:#58a6ff}}
.stat-lbl{{font-size:12px;color:#8b949e}}
.big-stat{{text-align:center;padding:10px}}
.big-stat .num{{font-size:36px;font-weight:800;color:#58a6ff}}
.big-stat .lbl{{font-size:11px;color:#8b949e;margin-top:2px}}
.svc{{display:flex;align-items:center;gap:8px;padding:5px 0}}
.dot-ok{{width:8px;height:8px;border-radius:50%;background:#27ae60}}
.dot-warn{{width:8px;height:8px;border-radius:50%;background:#f39c12}}
.dot-err{{width:8px;height:8px;border-radius:50%;background:#e74c3c}}
.svc-name{{font-size:13px;flex:1}}
.svc-status{{font-size:11px;color:#8b949e}}
.alert{{padding:10px 14px;border-radius:6px;margin-bottom:8px;font-size:13px;border-left:4px solid}}
.alert-critical{{background:#2d1117;border-color:#e74c3c;color:#ffa0a0}}
.alert-high{{background:#2d1f0a;border-color:#f39c12;color:#ffd580}}
.al-icon{{margin-right:6px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;color:#8b949e;padding:4px 8px;border-bottom:1px solid #30363d}}
td{{padding:6px 8px;border-bottom:1px solid #21262d}}
.tag-ok{{background:#1f3a2a;color:#3fb950;padding:2px 8px;border-radius:10px;font-size:11px}}
.tag-warn{{background:#2d1f0a;color:#d29922;padding:2px 8px;border-radius:10px;font-size:11px}}
.tag-err{{background:#2d1117;color:#f85149;padding:2px 8px;border-radius:10px;font-size:11px}}
.ts{{font-size:11px;color:#8b949e}}
ul{{padding-left:16px;font-size:13px;color:#8b949e}}
li{{margin-bottom:4px}}
.footer{{text-align:center;padding:16px;font-size:11px;color:#30363d;border-top:1px solid #21262d;margin-top:8px}}
</style>
</head>
<body>
<div class="hdr">
  <div>
    <h1>REX COMMAND CENTER</h1>
    <div class="sub">Garden of Joy Adult Day Care · Gold Health Systems</div>
  </div>
  <div style="text-align:right">
    <div class="health-badge">{health.upper()}</div>
    <div class="ts" style="margin-top:6px">{ts} UTC · auto-refreshes every 30s</div>
  </div>
</div>

<div class="grid">

  <!-- Client Stats -->
  <div class="card">
    <h3>Client Overview</h3>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px">
      <div class="big-stat"><div class="num">{db.get("active_clients",0)}</div><div class="lbl">Active Clients</div></div>
      <div class="big-stat"><div class="num">{db.get("staff_count",0)}</div><div class="lbl">Staff</div></div>
      <div class="big-stat"><div class="num">{db.get("auth_count",0)}</div><div class="lbl">Auth Docs</div></div>
    </div>
    <div class="stat-row"><span class="stat-lbl">Attendance Records</span><span class="stat-val" style="font-size:14px">{db.get("attendance_count",0):,}</span></div>
    <div class="stat-row"><span class="stat-lbl">Menu Selections</span><span class="stat-val" style="font-size:14px">{db.get("menu_count",0)}</span></div>
    <div class="stat-row"><span class="stat-lbl">Rexxie Memory (ideas)</span><span class="stat-val" style="font-size:14px">{db.get("rexxie_ideas",0)}</span></div>
    <div class="stat-row"><span class="stat-lbl">DB</span><span style="font-size:10px;color:#8b949e">{("✓ accessible" if db.get("accessible") else "✗ NOT FOUND")}</span></div>
  </div>

  <!-- Services -->
  <div class="card">
    <h3>Services</h3>
    {"".join(f'''<div class="svc">
      <div class="{"dot-ok" if s.get("status")=="running" else ("dot-warn" if s.get("status")=="unknown" else "dot-err")}"></div>
      <span class="svc-name">{n}</span>
      <span class="svc-status">{s.get("status","?").upper()}</span>
    </div>''' for n,s in [("Rex Backend",svc.get("rex_backend",{})),("Rexxie Bot",svc.get("rexxie_bot",{})),("Scheduler",svc.get("scheduler",{})),("Flask Dashboard",svc.get("flask_dashboard",{}))])}
    <div style="margin-top:14px;padding:10px;background:#0d2347;border-radius:6px;font-size:11px;color:#8b949e">
      <strong style="color:#58a6ff">Recommended:</strong> FastAPI via Tailscale<br>
      Run START_API_SERVER.command for multi-user access
    </div>
  </div>

  <!-- OCR -->
  <div class="card">
    <h3>OCR Pipeline</h3>
    <div class="stat-row">
      <span class="stat-lbl">Unresolved Flags</span>
      <span class="{'tag-ok' if ocr.get('flag_queue_unresolved',0)==0 else ('tag-warn' if ocr.get('flag_queue_unresolved',0)<10 else 'tag-err')}">{ocr.get("flag_queue_unresolved",0)}</span>
    </div>
    <div class="stat-row"><span class="stat-lbl">Stale-path flags</span><span class="tag-warn">{ocr.get("flag_queue_stale_path",0)}</span></div>
    <div class="stat-row"><span class="stat-lbl">Snapshot</span><span class="{'tag-ok' if ocr.get('snapshot_exists') else 'tag-err'}">{"exists" if ocr.get("snapshot_exists") else "missing"}</span></div>
    <div class="stat-row"><span class="stat-lbl">Core Schema</span><span class="{'tag-ok' if ocr.get('core_schema_ok') else 'tag-err'}">{"ok" if ocr.get("core_schema_ok") else "missing"}</span></div>
    <div class="stat-row"><span class="stat-lbl">Pending in drop zone</span><span class="{'tag-warn' if ocr.get('drop_zone_pending',0) else 'tag-ok'}">{ocr.get("drop_zone_pending",0)} PDF(s)</span></div>
  </div>

  <!-- Security Alerts -->
  <div class="card">
    <h3>Security Alerts</h3>
    {alert_html if alert_html else '<div style="color:#3fb950;font-size:13px">✓ No critical alerts found</div>'}
  </div>

  <!-- Dashboard Connections -->
  <div class="card">
    <h3>Dashboard Connections</h3>
    <div class="svc"><div class="dot-ok"></div><span class="svc-name">Local Flask</span><span class="svc-status">localhost:8080 · local DB ✓</span></div>
    <div class="svc"><div class="dot-err"></div><span class="svc-name">Railway GOJ</span><span class="svc-status">DISCONNECTED · separate DB ✗</span></div>
    <div class="svc"><div class="dot-warn"></div><span class="svc-name">FastAPI Bridge</span><span class="svc-status">NOT CONFIGURED</span></div>
    <div class="svc"><div class="dot-ok"></div><span class="svc-name">GHS Marketing</span><span class="svc-status">goldhealthsys.com · no data needed</span></div>
  </div>

  <!-- Quarantine + Ledger -->
  <div class="card">
    <h3>Control System</h3>
    <div class="stat-row"><span class="stat-lbl">Quarantine items</span><span class="stat-val" style="font-size:14px">{quar.get("item_count",0)}</span></div>
    <div class="stat-row"><span class="stat-lbl">Ledgers</span><span class="{'tag-ok' if led.get('all_present') else 'tag-warn'}">{"all 4 present" if led.get("all_present") else "some missing"}</span></div>
    <div class="stat-row"><span class="stat-lbl">Intake pending</span><span class="{'tag-warn' if led.get('intake_pending',0) else 'tag-ok'}">{led.get("intake_pending",0)}</span></div>
    <h3 style="margin-top:14px">Ledger Files</h3>
    <table><tr><th>File</th><th>Lines</th><th>Updated</th></tr>{led_rows}</table>
  </div>

  <!-- Manual Review -->
  <div class="card">
    <h3>Manual Review Inbox</h3>
    <ul>{review_html}</ul>
    <div style="margin-top:10px;font-size:11px;color:#8b949e">Drop files in LEDGER_REVIEW_INBOX/ to queue for review</div>
  </div>

</div>
<div class="footer">REX Command Center · Garden of Joy Adult Day Care · Generated {ts} UTC · Refreshes every 30s</div>
</body></html>"""

    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
    tmp.write(html)
    tmp.close()
    webbrowser.open(f"file://{tmp.name}")
    print(f"✅ Executive dashboard opened in browser: {tmp.name}")


# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    while True:
        d = get_status()
        if MODE == "executive":
            render_executive(d)
            break
        else:
            if MODE == "claude":
                os.system("clear")
            render_claude(d)
            if not WATCH:
                break
            print("  Refreshing in 30s... (Ctrl+C to exit)\n")
            time.sleep(30)

try:
    run()
except KeyboardInterrupt:
    print("\n  Command Center closed.")
PYEOF

"$PY" "$_SCRIPT" "$MODE" "$([ "$WATCH" = true ] && echo watch || echo once)"
rm -f "$_SCRIPT"

[ "$MODE" != "executive" ] && read -n 1 -p "Press any key to close..."
