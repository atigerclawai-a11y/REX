#!/usr/bin/env python3
"""CC_ghs_platform.py — Unified GHS Platform Web App.
Replaces both HHAeXchange and Carecenta with a single dashboard.
Port 8200. Single entry point for all operations.
"""

import subprocess, json, os, sys, re, sqlite3, html
from pathlib import Path
from datetime import datetime, date, timedelta
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn

REX = Path.home() / "Desktop" / "REX"
OUTPUT = REX / "output"
OUTPUT.mkdir(exist_ok=True)

app = FastAPI(title="GHS Platform", version="1.0.0",
              description="Replaces HHAeXchange + Carecenta. Biometric, EVV, daily packs, menus, payroll, auth tracking.")

SCRIPTS = {
    "evv": REX / "CC_evv.py",
    "biometric": REX / "CC_biometric.py",
    "daily_pack": REX / "CC_daily_pack.py",
    "menu": REX / "CC_menu.py",
    "hha_reconcile": REX / "CC_hha_reconcile.py",
    "payroll": REX / "CC_payroll.py",
    "billing_bridge": REX / "CC_schedule_to_837.py",
    "837_generator": REX / "CC_medicaid_837_generator.py",
}

# Design tokens inlined from ~/Desktop/REX/ghs-theme.css (CANONICAL — all GHS
# surfaces import that file; it is inlined here to keep this app self-contained).
HTML_HEAD = """<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GHS Platform</title>
<style>
:root{
--ghs-bg:#06080a;--ghs-bg-2:#0a0f0d;--ghs-surface:rgba(12,16,20,0.85);--ghs-surface-2:rgba(16,22,26,0.75);
--ghs-code:rgba(8,12,16,0.9);--ghs-accent:#5d9b6b;--ghs-accent-hi:#7bc98e;--ghs-accent-dim:#3d6b48;
--ghs-accent-grad:linear-gradient(135deg,#5d9b6b 0%,#7bc98e 100%);
--ghs-text:#d4dce6;--ghs-dim:#6a7a88;--ghs-faint:#4a5a64;
--ghs-ok:#7bc98e;--ghs-warn:#d4b25e;--ghs-danger:#d4685e;
--ghs-border:rgba(93,155,107,0.12);--ghs-border-hi:rgba(123,201,142,0.28);
--ghs-radius:12px;--ghs-radius-card:18px;--ghs-radius-modal:24px;
--ghs-shadow:0 4px 30px rgba(0,0,0,0.3);--ghs-glow:0 0 12px rgba(93,155,107,0.18);
--ghs-transition:0.25s cubic-bezier(0.4,0,0.2,1);
--ghs-font-body:22px;--ghs-font-header:16px;--ghs-font-hero:72px;--ghs-font-stat:28px;--ghs-font-nav:17px;
}
*{margin:0;padding:0;box-sizing:border-box;transition:var(--ghs-transition)}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Inter','Segoe UI',Roboto,sans-serif;
background:radial-gradient(1200px 800px at 85% -10%,rgba(93,155,107,0.09),transparent 60%),
radial-gradient(900px 700px at -10% 110%,rgba(93,155,107,0.06),transparent 55%),
linear-gradient(180deg,var(--ghs-bg) 0%,var(--ghs-bg-2) 100%);
color:var(--ghs-text);min-height:100vh;font-size:var(--ghs-font-body)}
nav{background:var(--ghs-surface);backdrop-filter:blur(20px) saturate(1.1);-webkit-backdrop-filter:blur(20px) saturate(1.1);
padding:12px 24px;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--ghs-border);flex-wrap:wrap}
nav a{color:var(--ghs-dim);text-decoration:none;padding:10px 18px;border-radius:var(--ghs-radius);font-size:var(--ghs-font-nav);font-weight:500;border:1px solid transparent}
nav a:hover{background:var(--ghs-surface-2);color:var(--ghs-text);border-color:var(--ghs-border-hi);box-shadow:var(--ghs-glow)}
nav a.active{background:var(--ghs-accent-grad);color:#06110a}
nav .brand{color:var(--ghs-accent-hi);font-weight:800;font-size:19px;margin-right:8px;letter-spacing:0.5px}
nav .rolesep{border-left:1px solid var(--ghs-border-hi);height:26px;margin:0 6px}
.fsbox{margin-left:auto;display:flex;gap:6px;align-items:center}
.fsbox button{background:transparent;color:var(--ghs-accent-hi);border:1px solid var(--ghs-border-hi);border-radius:8px;
padding:6px 12px;font-size:15px;cursor:pointer;font-weight:600}
.fsbox button.on{background:var(--ghs-accent-grad);color:#06110a}
.container{max-width:1400px;margin:0 auto;padding:24px}
h1{font-size:30px;margin-bottom:16px;color:var(--ghs-text)}
h2{font-size:var(--ghs-font-header);margin:16px 0 10px;color:var(--ghs-accent-hi);text-transform:uppercase;letter-spacing:1px}
pre{background:var(--ghs-code);padding:16px;border-radius:var(--ghs-radius);overflow-x:auto;font-size:15px;line-height:1.5;border:1px solid var(--ghs-border)}
.card{background:var(--ghs-surface);backdrop-filter:blur(20px) saturate(1.1);-webkit-backdrop-filter:blur(20px) saturate(1.1);
border:1px solid var(--ghs-border);border-radius:var(--ghs-radius-card);box-shadow:var(--ghs-shadow);padding:22px;margin-bottom:16px}
.card:hover{border-color:var(--ghs-border-hi)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.stat{text-align:center;padding:18px;background:var(--ghs-surface);border:1px solid var(--ghs-border);border-radius:var(--ghs-radius-card);box-shadow:var(--ghs-shadow)}
.stat-value{font-size:var(--ghs-font-stat);font-weight:700;color:var(--ghs-accent-hi)}
.stat-label{font-size:15px;color:var(--ghs-dim);margin-top:4px}
.hero{font-size:var(--ghs-font-hero);font-weight:800;color:var(--ghs-accent-hi);line-height:1}
form{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
input,select{background:var(--ghs-bg-2);border:1px solid var(--ghs-border);color:var(--ghs-text);padding:10px 14px;border-radius:var(--ghs-radius);font-size:17px}
input:focus,select:focus{outline:none;border-color:var(--ghs-border-hi);box-shadow:var(--ghs-glow)}
button{background:var(--ghs-accent-grad);color:#06110a;border:none;padding:10px 22px;border-radius:var(--ghs-radius);cursor:pointer;font-size:var(--ghs-font-nav);font-weight:600}
button:hover{box-shadow:var(--ghs-glow)}
.flash{background:rgba(212,104,94,0.15);color:var(--ghs-danger);border:1px solid rgba(212,104,94,0.3);padding:10px 14px;border-radius:var(--ghs-radius);margin:8px 0;font-size:15px}
.success{background:rgba(123,201,142,0.12);color:var(--ghs-ok);border-color:rgba(123,201,142,0.3)}
.tbl{width:100%;border-collapse:collapse;font-size:calc(var(--ghs-font-body)*0.78)}
.tbl th{text-align:left;color:var(--ghs-accent-hi);font-size:var(--ghs-font-header);border-bottom:1px solid var(--ghs-border-hi);padding:10px 12px;text-transform:uppercase;letter-spacing:1px}
.tbl td{padding:10px 12px;border-bottom:1px solid var(--ghs-border);color:var(--ghs-text)}
.tbl tr:hover td{background:rgba(93,155,107,0.05)}
.chip{display:inline-block;padding:3px 12px;border-radius:999px;font-size:15px;font-weight:600;white-space:nowrap}
.chip-red{background:rgba(212,104,94,0.15);color:var(--ghs-danger);border:1px solid rgba(212,104,94,0.3)}
.chip-yellow{background:rgba(212,178,94,0.12);color:var(--ghs-warn);border:1px solid rgba(212,178,94,0.3)}
.chip-orange{background:rgba(210,140,80,0.12);color:#d28c50;border:1px solid rgba(210,140,80,0.3)}
.chip-green{background:rgba(123,201,142,0.12);color:var(--ghs-ok);border:1px solid rgba(123,201,142,0.3)}
.dim{color:var(--ghs-dim)}
a.lnk{color:var(--ghs-accent-hi);text-decoration:none}
a.lnk:hover{text-decoration:underline}
@media print{
nav,.no-print,form,button{display:none !important}
body{background:#fff !important;color:#000 !important;font-size:14px}
.card,.stat{border:1px solid #999;background:#fff;box-shadow:none;color:#000}
h1,h2,.stat-value,.hero,.tbl th{color:#000 !important}
.tbl td{color:#000;border-color:#999}
.chip{border:1px solid #000;color:#000;background:#fff}
a[href^="tel:"]:after{content:" (" attr(href) ")";font-size:0}
}
</style></head><body>
<nav>
<span class="brand">◆ GHS</span>
<a href="/">📊 Dashboard</a>
<a href="/evv">📋 EVV</a>
<a href="/biometric">🔐 Biometric</a>
<a href="/daily-pack">📄 Daily Pack</a>
<a href="/menu">🍽️ Menu</a>
<a href="/auth">📜 Auth Tracker</a>
<a href="/payroll">💰 Payroll</a>
<a href="/hha">🔄 HHA Reconcile</a>
<a href="/billing">💳 Billing 837</a>
<span class="rolesep"></span>
<a href="/kitchen">🍲 Kitchen</a>
<a href="/driver">🚐 Driver</a>
<a href="/frontdesk">🛎️ Front Desk</a>
<a href="/financial">📈 Financial</a>
<span class="fsbox no-print"><button data-fs="22" title="Normal text">A</button><button data-fs="26" title="Large text">A+</button><button data-fs="30" title="XL text">A++</button></span>
</nav>
<div class="container">
<script>
(function(){
var sizes=['22','26','30'],cur=localStorage.getItem('ghs_fs')||'22';
function applyFs(v){cur=v;document.documentElement.style.setProperty('--ghs-font-body',v+'px');
localStorage.setItem('ghs_fs',v);
var bs=document.querySelectorAll('.fsbox button');
for(var i=0;i<bs.length;i++){bs[i].className=(bs[i].getAttribute('data-fs')===v)?'on':'';}}
var bs=document.querySelectorAll('.fsbox button');
for(var i=0;i<bs.length;i++){bs[i].onclick=function(){applyFs(this.getAttribute('data-fs'));};}
applyFs(cur);
var as=document.querySelectorAll('nav a'),p=location.pathname;
for(var i=0;i<as.length;i++){var h=as[i].getAttribute('href');
if(h===p||(h!=='/'&&p.indexOf(h)===0)){as[i].className='active';}}
if(p==='/'){for(var i=0;i<as.length;i++){if(as[i].getAttribute('href')==='/'){as[i].className='active';}}}
})();
</script>"""

HTML_FOOT = """</div></body></html>"""

def run_script(name, args=None):
    """Run a CC_ script and return (output, error)."""
    script = SCRIPTS.get(name)
    if not script or not script.exists():
        return None, f"Script {name} not found"
    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend(args if isinstance(args, list) else [args])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.stdout, r.stderr if r.returncode != 0 else None
    except subprocess.TimeoutExpired:
        return None, "Script timed out"
    except Exception as e:
        return None, str(e)

def format_output(text, error=None):
    """Format script output as HTML."""
    parts = []
    if error:
        parts.append(f'<div class="flash">{error}</div>')
    if text:
        parts.append(f'<pre>{text}</pre>')
    return "".join(parts)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    stats = []
    # Count scripts
    built = sum(1 for s in SCRIPTS.values() if s.exists())
    stats.append((built, "Components Built", len(SCRIPTS)))
    # Count output files
    output_count = len(list(OUTPUT.glob("*")))
    stats.append((output_count, "Output Files", "—"))
    # Most recent output
    recent = sorted(OUTPUT.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
    recent_str = recent[0].name if recent else "—"
    
    rows = "".join(f'<div class="stat"><div class="stat-value">{v}</div><div class="stat-label">{l}</div></div>'
                   for v, l, _ in stats)
    
    return HTML_HEAD + f"""
    <h1>🏥 GHS Platform</h1>
    <p style="color:var(--ghs-dim);margin-bottom:20px">Replaces HHAeXchange + Carecenta · Port 8200 · {date.today()}</p>
    <div class="grid">{rows}</div>
    <div class="card">
        <h2>Components</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
            {''.join(f'<div style="display:flex;justify-content:space-between;padding:4px 0"><span>{k}</span><span style="color:{"var(--ghs-ok)" if v.exists() else "var(--ghs-danger)"}">{"✅" if v.exists() else "❌"}</span></div>' for k, v in SCRIPTS.items())}
        </div>
    </div>
    <div class="card">
        <h2>Latest Output</h2>
        <pre>{recent_str}</pre>
    </div>
    """ + HTML_FOOT

@app.get("/evv", response_class=HTMLResponse)
async def evv_page(date_str: str = Query(None, alias="date")):
    args = ["--date", date_str] if date_str else []
    out, err = run_script("evv", args)
    file_list = "".join(f'<div>{f.name}</div>' for f in sorted(OUTPUT.glob("evv_*.csv")))
    return HTML_HEAD + f"""
    <h1>📋 EVV Records</h1>
    <form method="get" action="/evv">
        <input type="date" name="date" value="{date_str or date.today()}">
        <button type="submit">Generate EVV</button>
    </form>
    {format_output(out, err)}
    <div class="card">
        <h2>Generated Files</h2>
        {file_list or "<div style='color:var(--ghs-dim)'>No EVV files generated yet</div>"}
    </div>
    """ + HTML_FOOT

@app.get("/biometric", response_class=HTMLResponse)
async def biometric_page(action: str = Query("list"), client: str = Query(None), pin: str = Query(None)):
    args = [f"--{action}"]
    if client:
        args.extend([client, pin or ""])
    out, err = run_script("biometric", args)
    return HTML_HEAD + f"""
    <h1>🔐 Biometric Sign-In</h1>
    <div class="card">
        <h2>Enroll Client</h2>
        <form method="get" action="/biometric">
            <input type="hidden" name="action" value="enroll">
            <input type="text" name="client" placeholder="Client Name" required style="width:250px">
            <input type="text" name="pin" placeholder="PIN (4-6 digits)" required>
            <button type="submit">Enroll</button>
        </form>
    </div>
    <div class="card">
        <h2>Sign In</h2>
        <form method="get" action="/biometric">
            <input type="hidden" name="action" value="signin">
            <input type="text" name="client" placeholder="Client Name" required style="width:250px">
            <input type="text" name="pin" placeholder="PIN" required>
            <button type="submit">Sign In</button>
        </form>
    </div>
    <div class="card">
        <h2>All Enrolled</h2>
        <form method="get" action="/biometric" style="margin:0">
            <input type="hidden" name="action" value="list">
            <button type="submit">Refresh List</button>
        </form>
        {format_output(out, err)}
    </div>
    """ + HTML_FOOT

@app.get("/daily-pack", response_class=HTMLResponse)
async def daily_pack_page(date_str: str = Query(None, alias="date"), shifts: str = Query("both")):
    args = ["--date", date_str or str(date.today()), "--shifts", shifts]
    out, err = run_script("daily_pack", args)
    files = sorted(OUTPUT.glob("CC_*.pdf"))
    file_links = "".join(f'<div><a href="/output/{f.name}" style="color:var(--ghs-accent-hi)">{f.name}</a></div>' for f in files)
    return HTML_HEAD + f"""
    <h1>📄 Daily Pack</h1>
    <form method="get" action="/daily-pack">
        <input type="date" name="date" value="{date_str or date.today()}">
        <select name="shifts"><option value="both" {"selected" if shifts=="both" else ""}>Both Shifts</option>
        <option value="S1" {"selected" if shifts=="S1" else ""}>Shift 1 (8am-2pm)</option>
        <option value="S2" {"selected" if shifts=="S2" else ""}>Shift 2 (2pm-8pm)</option></select>
        <button type="submit">Generate</button>
    </form>
    {format_output(out, err)}
    <div class="card"><h2>Generated PDFs</h2>{file_links or "<div style='color:var(--ghs-dim)'>No PDFs yet</div>"}</div>
    """ + HTML_FOOT

@app.get("/menu", response_class=HTMLResponse)
async def menu_page(week: str = Query(None), preview: str = Query("0")):
    args = []
    if week:
        args = ["--week", week]
    if preview == "1":
        args.extend(["--preview"])
    elif not week:
        args.extend(["--export"])  # auto-export
    out, err = run_script("menu", args)
    menus = sorted(OUTPUT.glob("menu_*.pdf"))
    file_links = "".join(f'<div><a href="/output/{f.name}" style="color:var(--ghs-accent-hi)">{f.name}</a></div>' for f in menus)
    return HTML_HEAD + f"""
    <h1>🍽️ Weekly Menu</h1>
    <form method="get" action="/menu">
        <input type="week" name="week" value="{week or ''}">
        <label><input type="checkbox" name="preview" value="1"> Preview only</label>
        <button type="submit">Generate</button>
    </form>
    {format_output(out, err)}
    <div class="card"><h2>Generated PDFs</h2>{file_links or "<div style='color:var(--ghs-dim)'>No menus yet</div>"}</div>
    """ + HTML_FOOT

@app.get("/auth", response_class=HTMLResponse)
async def auth_page():
    try:
        import sqlite3
        db = str(Path.home() / "Documents/goj files/dashboard/auth_tracker.db")
        conn = sqlite3.connect(db)
        clients = conn.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
        auths = conn.execute("SELECT COUNT(*) FROM authorization WHERE status='ACTIVE'").fetchone()[0]
        expiring = conn.execute("SELECT COUNT(*) FROM authorization WHERE status='ACTIVE' AND service_end_date BETWEEN date('now') AND date('now','+30 days')").fetchone()[0]
        expired = conn.execute("SELECT COUNT(*) FROM authorization WHERE status='ACTIVE' AND service_end_date < date('now')").fetchone()[0]
        conn.close()
    except:
        clients=auths=expiring=expired=0
    
    return HTML_HEAD + f"""
    <h1>📜 Auth Tracker</h1>
    <div class="grid">
        <div class="stat"><div class="stat-value">{clients}</div><div class="stat-label">Active Clients</div></div>
        <div class="stat"><div class="stat-value">{auths}</div><div class="stat-label">Active Auths</div></div>
        <div class="stat"><div class="stat-value">{expiring}</div><div class="stat-label">Expiring ≤30 days</div></div>
        <div class="stat"><div class="stat-value" style="color:var(--ghs-danger)">{expired}</div><div class="stat-label">Expired (still ACTIVE)</div></div>
    </div>
    <div class="card">
        <h2>Import Carecenta Auths</h2>
        <p style="color:var(--ghs-dim);font-size:13px;margin-bottom:8px">Run the Carecenta → auth_tracker import</p>
        <form method="get" action="/api/import-auths">
            <button type="submit">Import Now</button>
        </form>
    </div>
    """ + HTML_FOOT

@app.get("/payroll", response_class=HTMLResponse)
async def payroll_page(fmt: str = Query("adp"), period_start: str = Query(None), period_end: str = Query(None)):
    args = ["--format", fmt]
    if period_start and period_end:
        args.extend(["--period", period_start, period_end])
    out, err = run_script("payroll", args)
    return HTML_HEAD + f"""
    <h1>💰 Payroll Export</h1>
    <form method="get" action="/payroll">
        <input type="date" name="period_start" placeholder="Start" value="{period_start or ''}">
        <input type="date" name="period_end" placeholder="End" value="{period_end or ''}">
        <select name="fmt"><option value="adp" {"selected" if fmt=="adp" else ""}>ADP</option>
        <option value="gusto" {"selected" if fmt=="gusto" else ""}>Gusto</option></select>
        <button type="submit">Generate</button>
    </form>
    {format_output(out, err)}
    """ + HTML_FOOT

@app.get("/hha", response_class=HTMLResponse)
async def hha_page():
    out, err = run_script("hha_reconcile")
    return HTML_HEAD + f"""
    <h1>🔄 HHAeXchange Reconciliation</h1>
    <form method="get" action="/hha"><button type="submit">Run Reconciliation</button></form>
    {format_output(out, err)}
    """ + HTML_FOOT

@app.get("/billing", response_class=HTMLResponse)
async def billing_page(month: str = Query(None)):
    """Billing 837 pipeline — readiness + dry-run claim preview."""
    # Env readiness (names + set/empty only — never display values)
    env_file = REX / ".env.837"
    env_rows = ""
    set_count = empty_count = 0
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if val.strip():
                set_count += 1
                env_rows += f'<div style="display:flex;justify-content:space-between;padding:2px 0"><span style="font-size:12px">{key}</span><span style="color:var(--ghs-ok)">✅ set</span></div>'
            else:
                empty_count += 1
                env_rows += f'<div style="display:flex;justify-content:space-between;padding:2px 0"><span style="font-size:12px">{key}</span><span style="color:var(--ghs-danger)">❌ needed</span></div>'

    # Dry-run bridge for selected month (default: current)
    today = date.today()
    if month:
        try:
            y, m = month.split("-")
        except ValueError:
            y, m = str(today.year), str(today.month)
    else:
        y, m = str(today.year), str(today.month)
        month = f"{today.year}-{today.month:02d}"
    out, err = run_script("billing_bridge", ["--month", y, m, "--dry-run"])

    ready = "🟢 READY TO ACTIVATE" if empty_count == 0 else f"🟡 BLOCKED — {empty_count} config values needed (see checklist)"
    return HTML_HEAD + f"""
    <h1>💳 Medicaid 837 Billing</h1>
    <p style="color:var(--ghs-dim);margin-bottom:16px">Attendance → Authorization → 837P X12 → Availity clearinghouse. Status: <b>{ready}</b></p>
    <div class="card">
        <h2>Run Claim Preview (dry-run, never submits)</h2>
        <form method="get" action="/billing">
            <input type="month" name="month" value="{month}">
            <button type="submit">Preview Claims</button>
        </form>
        {format_output(out, err)}
    </div>
    <div class="card">
        <h2>Activation Config (.env.837) — {set_count} set / {empty_count} missing</h2>
        <p style="color:var(--ghs-dim);font-size:12px;margin-bottom:8px">Values never displayed here. Fill via CC_837_LIVE_ACTIVATION_CHECKLIST.md</p>
        {env_rows}
    </div>
    """ + HTML_FOOT

@app.get("/output/{filename}")
async def serve_output(filename: str):
    f = OUTPUT / filename
    if f.exists():
        return FileResponse(str(f))
    raise HTTPException(404, "File not found")

@app.get("/api/import-auths")
async def import_auths():
    out, err = run_script("carecenta_import", ["--dry-run"])
    if err:
        raise HTTPException(500, err)
    return JSONResponse({"output": out})

# ==================== Role surfaces (read-only DB access — no writes) ====================
# Roster source of truth: CC_unified_sheets.get_clients_for_day (imported, not
# reimplemented) — role pages reconcile with the canonical generators by construction.
SCHED_DB = Path.home() / "Desktop/REX/signin_lists/ghs_schedule.db"
AUTH_DB = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
PROP_DB = Path.home() / "Documents/goj files/proprietary/goj_proprietary.db"
GOJ_DEST = "3152 Brighton 6 St, Brooklyn NY 11235"
ROUTE_DAY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # python weekday → driver_routes.day_of_week

def _ro(p):
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)

def _cnorm(first, last=""):
    """Order-insensitive alpha-token normalizer — strips Carecenta ID artifacts
    ('Ludmila 206578' → 'ludmila') and case/order differences."""
    return " ".join(sorted(re.findall(r"[a-z]+", f"{first} {last}".lower())))

def _sched_mod():
    if str(REX) not in sys.path:
        sys.path.insert(0, str(REX))
    import CC_unified_sheets
    return CC_unified_sheets

def _auth_map():
    """auth_tracker.db authorizations keyed by normalized client name."""
    m = {}
    if not AUTH_DB.exists():
        return m
    conn = _ro(AUTH_DB)
    try:
        for nm, st, end, payer in conn.execute(
                "SELECT client_name, status, service_end_date, payer_canonical FROM authorization"):
            m.setdefault(_cnorm(nm), []).append({"status": st or "", "end": end or "", "payer": payer or ""})
    except sqlite3.Error:
        pass
    conn.close()
    return m

def _norm_payer(p):
    return re.sub(r"[^A-Z0-9]", "", (p or "").upper())

def _payers_match(a, b):
    """Port of CC_schedule_hub.payers_match — alnum-normalized prefix match either direction."""
    na, nb = _norm_payer(a), _norm_payer(b)
    if not na or not nb or na == "UNKNOWN" or nb == "UNKNOWN":
        return True  # unverifiable → don't flag (kills false positives)
    return na.startswith(nb) or nb.startswith(na) or na[:6] == nb[:6]

def _route_map(day_str, shift_label):
    """driver_routes lookup by normalized client name for one day/shift."""
    m = {}
    if not SCHED_DB.exists():
        return m
    conn = _ro(SCHED_DB)
    try:
        for nm, addr, phone, drv, dphone, daddr in conn.execute(
                "SELECT client_name, client_address, client_phone, driver_name, driver_phone, driver_address "
                "FROM driver_routes WHERE day_of_week=? AND shift=?", (day_str, shift_label)):
            m[_cnorm(nm)] = {"addr": addr or "", "phone": phone or "", "driver": drv or "",
                             "dphone": dphone or "", "daddr": daddr or ""}
    except sqlite3.Error:
        pass
    conn.close()
    return m

def _valid_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    except ValueError:
        dt = date.today()
    return dt

@app.get("/kitchen", response_class=HTMLResponse)
async def kitchen_page(date_str: str = Query(None, alias="date")):
    dt = _valid_date(date_str)
    d = dt.isoformat()
    menus = {}
    if PROP_DB.exists():
        conn = _ro(PROP_DB)
        try:
            for nm, sh, main, soup in conn.execute(
                    "SELECT client_name, shift, main, soup FROM client_menus WHERE menu_date=?", (d,)):
                menus[(_cnorm(nm), str(sh))] = ((main or "").strip(), (soup or "").strip())
        except sqlite3.Error:
            pass
        conn.close()
    sections, recon = "", []
    for shift, label in ((1, "Shift 1 · 8am–2pm"), (2, "Shift 2 · 2pm–8pm")):
        try:
            roster = _sched_mod().get_clients_for_day(d, shift)
        except Exception as e:
            sections += f'<div class="flash">Schedule query failed for shift {shift}: {html.escape(str(e))}</div>'
            continue
        n = len(roster)
        recon.append((shift, n))
        dishes, soups = {}, {}
        no_menu = 0
        for c in roster:
            mm = menus.get((_cnorm(c["first_name"], c["last_name"]), str(shift)))
            if mm is None:
                no_menu += 1
                continue
            main = mm[0] or "Standard"
            dishes[main] = dishes.get(main, 0) + 1
            if mm[1]:
                soups[mm[1]] = soups.get(mm[1], 0) + 1
        rows = ""
        for dish, cnt in sorted(dishes.items(), key=lambda x: (-x[1], x[0])):
            k_chip = ' <span class="chip chip-green">KOSHER</span>' if "KOSHER" in dish.upper() else ""
            rows += (f'<tr><td>{html.escape(dish)}{k_chip}</td>'
                     f'<td style="text-align:right;font-weight:700">{cnt}</td></tr>')
        if no_menu:
            rows += (f'<tr><td class="dim">— No menu on file (house standard plate)</td>'
                     f'<td style="text-align:right;font-weight:700">{no_menu}</td></tr>')
        rows += (f'<tr><td style="border-top:2px solid var(--ghs-border-hi);font-weight:800">TOTAL</td>'
                 f'<td style="text-align:right;font-weight:800;border-top:2px solid var(--ghs-border-hi)">{n}</td></tr>')
        soup_line = " · ".join(f"{html.escape(s)} ×{c}" for s, c in sorted(soups.items(), key=lambda x: -x[1])) or "—"
        sections += f"""
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:12px">
                <h2 style="margin:0">{label}</h2>
                <div><span class="hero">{n}</span> <span class="dim" style="font-size:20px">meals</span></div>
            </div>
            <table class="tbl" style="margin-top:14px">{rows}</table>
            <p class="dim" style="margin-top:12px;font-size:17px">Soups: {soup_line}</p>
        </div>"""
    recon_txt = " · ".join(f"S{s} = {n}" for s, n in recon)
    return HTML_HEAD + f"""
    <h1>🍲 Kitchen — Meal Counts</h1>
    <p class="dim" style="margin-bottom:14px">{dt.strftime('%A')} {d} · Roster: CC_unified_sheets (single source) · Menus: goj_proprietary.db</p>
    <form method="get" action="/kitchen" class="no-print">
        <input type="date" name="date" value="{d}">
        <button type="submit">Load Day</button>
        <button type="button" onclick="window.print()">🖨️ Print</button>
    </form>
    {sections}
    <div class="card"><h2>Reconciliation</h2>
    <p style="font-size:20px">✅ {recon_txt} — sign-in = kitchen = distribution (identical roster, one query).</p></div>
    """ + HTML_FOOT

@app.get("/driver", response_class=HTMLResponse)
async def driver_page(date_str: str = Query(None, alias="date")):
    dt = _valid_date(date_str)
    d = dt.isoformat()
    day_str = ROUTE_DAY[dt.weekday()]
    sections, recon = "", []
    for shift, label, rshift in ((1, "Shift 1 — Morning", "MORNING"), (2, "Shift 2 — Afternoon", "AFTERNOON")):
        try:
            roster = _sched_mod().get_clients_for_day(d, shift)
        except Exception as e:
            sections += f'<div class="flash">Schedule query failed for shift {shift}: {html.escape(str(e))}</div>'
            continue
        # HARD RULE: Larry never appears on any transport/driver list.
        riders = [c for c in roster if c["has_transport"] and "larry" not in _cnorm(c["first_name"], c["last_name"])]
        rmap = _route_map(day_str, rshift)
        rows = ""
        for c in riders:
            nm = html.escape(f"{c['last_name']}, {re.sub(r'[0-9 ]', '', c['first_name'])}")
            r = rmap.get(_cnorm(c["first_name"], c["last_name"]), {})
            phone = r.get("phone", "")
            dphone = r.get("dphone", "")
            ph = f'<a class="lnk" href="tel:{html.escape(phone)}">{html.escape(phone)}</a>' if phone else "—"
            dph = f'<a class="lnk" href="tel:{html.escape(dphone)}">{html.escape(dphone)}</a>' if dphone else ""
            drv = html.escape(r.get("driver", "")) or "—"
            addr = html.escape(r.get("addr", "")) or "—"
            rows += f"<tr><td style='font-weight:600'>{nm}</td><td>{addr}</td><td>{ph}</td><td>{drv} {dph}</td></tr>"
        recon.append((shift, len(riders)))
        sections += f"""
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:12px">
                <h2 style="margin:0">{label}</h2>
                <div><span class="hero">{len(riders)}</span> <span class="dim" style="font-size:20px">riders</span></div>
            </div>
            <table class="tbl" style="font-size:28px;margin-top:14px">
            <tr><th>Client</th><th>Pickup Address</th><th>Phone</th><th>Driver / Carpool</th></tr>{rows}</table>
        </div>"""
    recon_txt = " · ".join(f"S{s} = {n} riders" for s, n in recon)
    return HTML_HEAD + f"""
    <h1>🚐 Driver Manifest</h1>
    <p class="dim" style="margin-bottom:14px">{dt.strftime('%A')} {d} · Destination: <b style="color:var(--ghs-text)">{GOJ_DEST}</b></p>
    <form method="get" action="/driver" class="no-print">
        <input type="date" name="date" value="{d}">
        <button type="submit">Load Day</button>
        <button type="button" onclick="window.print()">🖨️ Print</button>
    </form>
    {sections}
    <div class="card"><h2>Reconciliation</h2>
    <p style="font-size:20px">✅ {recon_txt} — matches CC_unified_sheets transport counts for this roster.</p></div>
    """ + HTML_FOOT

@app.get("/frontdesk", response_class=HTMLResponse)
async def frontdesk_page(date_str: str = Query(None, alias="date")):
    dt = _valid_date(date_str)
    d = dt.isoformat()
    sat = dt + timedelta(days=(5 - dt.weekday()) % 7)   # viewed week's Saturday
    thr = (sat + timedelta(days=14)).isoformat()         # rolling EXPIRING threshold (flags.md)
    amap = _auth_map()
    exc, counts = [], {"NO_AUTH": 0, "EXPIRING": 0, "PAYER_MISMATCH": 0}
    total = clean = 0
    for shift in (1, 2):
        try:
            roster = _sched_mod().get_clients_for_day(d, shift)
        except Exception as e:
            return HTML_HEAD + f'<div class="flash">Schedule query failed: {html.escape(str(e))}</div>' + HTML_FOOT
        for c in roster:
            total += 1
            auths = [a for a in amap.get(_cnorm(c["first_name"], c["last_name"]), []) if a["status"] == "ACTIVE"]
            chips = []
            if not auths:
                chips.append(("NO_AUTH", "🔴 NO AUTH", "chip-red", "no active authorization on file"))
            else:
                best = max(a["end"] for a in auths)
                if best and best < thr:
                    chips.append(("EXPIRING", "⚠️ EXPIRING", "chip-yellow", f"ends {best}"))
                sp = c["payer"] or ""
                if sp and not any(_payers_match(a["payer"], sp) for a in auths):
                    ap = next((a["payer"] for a in auths if a["payer"]), "")
                    chips.append(("PAYER_MISMATCH", "🔄 PAYER MISMATCH", "chip-orange", f"schedule={sp} · auth={ap}"))
            if chips:
                for code, *_ in chips:
                    counts[code] += 1
                exc.append((shift, c, chips))
            else:
                clean += 1
    rows = ""
    for shift, c, chips in sorted(exc, key=lambda x: (x[0], x[1]["last_name"])):
        nm = html.escape(f"{c['last_name']}, {re.sub(r'[0-9 ]', '', c['first_name'])}")
        ch = " ".join(f'<span class="chip {cls}" title="{html.escape(det)}">{lbl}</span>'
                      for _, lbl, cls, det in chips)
        det = html.escape(" · ".join(det for _, _, _, det in chips if det))
        rows += (f"<tr><td style='font-weight:600'>{nm}</td><td>S{shift}</td>"
                 f"<td>{html.escape(c['time_slot'] or '')}</td><td>{html.escape(c['payer'] or '—')}</td>"
                 f"<td>{ch}</td><td class='dim' style='font-size:16px'>{det}</td></tr>")
    return HTML_HEAD + f"""
    <h1>🛎️ Front Desk — Sign-In Exceptions</h1>
    <p class="dim" style="margin-bottom:14px">{dt.strftime('%A')} {d} · Exceptions only · EXPIRING = auth ends before {thr}</p>
    <form method="get" action="/frontdesk" class="no-print">
        <input type="date" name="date" value="{d}">
        <button type="submit">Load Day</button>
        <button type="button" onclick="window.print()">🖨️ Print</button>
    </form>
    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr))">
        <div class="stat"><div class="stat-value">{total}</div><div class="stat-label">Expected today</div></div>
        <div class="stat"><div class="stat-value" style="color:var(--ghs-ok)">{clean}</div><div class="stat-label">✅ Clean</div></div>
        <div class="stat"><div class="stat-value" style="color:var(--ghs-danger)">{counts['NO_AUTH']}</div><div class="stat-label">🔴 NO AUTH</div></div>
        <div class="stat"><div class="stat-value" style="color:var(--ghs-warn)">{counts['EXPIRING']}</div><div class="stat-label">⚠️ EXPIRING</div></div>
        <div class="stat"><div class="stat-value" style="color:#d28c50">{counts['PAYER_MISMATCH']}</div><div class="stat-label">🔄 PAYER MISMATCH</div></div>
    </div>
    <div class="card">
        <h2>Exception List — {len(exc)} clients</h2>
        <table class="tbl"><tr><th>Client</th><th>Shift</th><th>Slot</th><th>Payer</th><th>Flag</th><th>Detail</th></tr>
        {rows or '<tr><td colspan="6" class="dim">No exceptions — everyone clean ✅</td></tr>'}</table>
    </div>
    """ + HTML_FOOT

@app.get("/financial", response_class=HTMLResponse)
async def financial_page(month: str = Query(None)):
    """Vlad's read-only billing view — dry-run data only, never submits, no config panel."""
    today = date.today()
    if month:
        try:
            y, m = month.split("-")
            int(y); int(m)
        except ValueError:
            y, m = str(today.year), str(today.month)
            month = f"{today.year}-{today.month:02d}"
    else:
        y, m = str(today.year), str(today.month)
        month = f"{today.year}-{today.month:02d}"
    out, err = run_script("billing_bridge", ["--month", y, m, "--dry-run", "--json"])
    data = {}
    if out:
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            err = (err or "") + " (bridge returned non-JSON)"
    s = data.get("summary", {})
    rng = data.get("date_range", {})
    payer_rows = ""
    bp, bpc = s.get("by_payer", {}), s.get("by_payer_charges", {})
    for p in sorted(bp, key=lambda x: -bpc.get(x, 0)):
        payer_rows += (f"<tr><td>{html.escape(p)}</td><td style='text-align:right'>{bp[p]:,}</td>"
                       f"<td style='text-align:right;font-weight:700'>${bpc.get(p, 0):,.2f}</td></tr>")
    warns = s.get("warnings", [])
    warn_rows = "".join(f"<li style='margin:4px 0'>{html.escape(w)}</li>" for w in warns[:10])
    body = f"""
    <div class="grid">
        <div class="stat"><div class="hero" style="font-size:56px">{s.get('total_claims', 0):,}</div><div class="stat-label">Claims (dry-run)</div></div>
        <div class="stat"><div class="hero" style="font-size:56px">${s.get('total_charge', 0):,.0f}</div><div class="stat-label">Total Charges</div></div>
        <div class="stat"><div class="hero" style="font-size:56px">{s.get('unique_clients', 0)}</div><div class="stat-label">Unique Clients</div></div>
    </div>
    <div class="card"><h2>By Payer — {rng.get('from', '')} → {rng.get('to', '')}</h2>
        <table class="tbl"><tr><th>Payer</th><th style="text-align:right">Claims</th><th style="text-align:right">Charges</th></tr>
        {payer_rows}</table></div>
    <div class="card"><h2>⚠️ Warnings — {len(warns)}</h2>
        <ul style="list-style:none;font-size:17px" class="dim">{warn_rows or '<li>None</li>'}</ul>
        {'<p class="dim" style="font-size:15px;margin-top:8px">…and ' + str(len(warns) - 10) + ' more (see /billing for full output)</p>' if len(warns) > 10 else ''}
    </div>"""
    return HTML_HEAD + f"""
    <h1>📈 Financial — Medicaid 837 <span class="chip chip-green">READ-ONLY</span></h1>
    <p class="dim" style="margin-bottom:14px">Dry-run data only — this view never submits claims. Attendance → 837P → Availity.</p>
    <form method="get" action="/financial">
        <input type="month" name="month" value="{month}">
        <button type="submit">Load Month</button>
    </form>
    {f'<div class="flash">{html.escape(err)}</div>' if err else ''}
    {body if data else '<div class="card dim">No data for this month.</div>'}
    """ + HTML_FOOT

if __name__ == "__main__":
    print("🏥 GHS Platform starting on http://localhost:8200")
    uvicorn.run(app, host="0.0.0.0", port=8200)
