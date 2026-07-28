#!/usr/bin/env bash
# Scheduled rescan — re-pulls the SIGN IN master log, diffs against the baseline
# captured at 3:35 PM today, and notifies Kato via Rexxie if anything changed.
# Triggered by ~/Library/LaunchAgents/com.kato.goj-rescan-tue-2026-05-11.plist.
set -u

LOG="$HOME/Desktop/REX/logs/goj_master_log_rescan.log"
mkdir -p "$HOME/Desktop/REX/logs"

cd "$HOME/Desktop/REX"
source .venv/bin/activate 2>/dev/null || true

echo "── Rescan — $(date '+%Y-%m-%d %H:%M:%S') ──" >> "$LOG"

python3 - >> "$LOG" 2>&1 <<'PYEOF'
import json, os, sys, csv, io, uuid, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

REX = Path.home() / "Desktop" / "REX"
DASH = Path.home() / "Documents" / "goj files" / "dashboard"
BASELINE = REX / "goj_master_log_rescan_baseline_2026-05-11.json"
TOKEN_PATH = Path.home() / ".rex_google_token.json"
CFG = json.loads((REX / "rex_rexxie_telegram_config.json").read_text())
TG_TOKEN = CFG["bot_token"]
TG_CHAT  = str(CFG["owner_chat_id"])
FILE_ID = "1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8"  # SIGN IN

# 1) Pull fresh CSV via Drive API
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
drive = build("drive", "v3", credentials=creds)
req = drive.files().export_media(fileId=FILE_ID, mimeType="text/csv")
buf = io.BytesIO()
dl = MediaIoBaseDownload(buf, req)
done = False
while not done:
    _, done = dl.next_chunk()
csv_text = buf.getvalue().decode("utf-8", errors="replace")
fresh_csv = REX / "SIGN_IN_master_rescan.csv"
fresh_csv.write_text(csv_text)
print(f"Pulled CSV: {len(csv_text)} chars")

# 2) Build current T-map
current_T = {}
rdr = csv.reader(csv_text.splitlines())
header = next(rdr)
t_idx = header.index("T")
for row in rdr:
    if not row or not row[0].strip(): continue
    name = row[0].strip()
    if len(name) >= 4 and name == name[0]*len(name): continue
    if len(row) <= t_idx: continue
    current_T[name] = row[t_idx].strip()

# 3) Load baseline
baseline = json.loads(BASELINE.read_text())
prev_T = baseline["master_log_T_column"]
prev_t1 = set(baseline["routes_T1"])
prev_t2 = set(baseline["routes_T2"])

# 4) Diff master log
changed, added, removed = [], [], []
for n, v in current_T.items():
    if n not in prev_T:
        added.append((n, v))
    elif prev_T[n] != v:
        changed.append((n, prev_T[n], v))
for n in prev_T:
    if n not in current_T:
        removed.append(n)

# 5) Diff vs current routes
ROUTES_PATH = DASH / "data" / "GOJ_Master_Routes.json"
routes = json.loads(ROUTES_PATH.read_text())
r_t1 = {r["name"] for r in routes.get("T1", []) if r.get("status","active") == "active"}
r_t2 = {r["name"] for r in routes.get("T2", []) if r.get("status","active") == "active"}

cur_master_t1 = {n for n,v in current_T.items() if v == "1"}
cur_master_t2 = {n for n,v in current_T.items() if v == "2"}
cur_master_off = {n: v for n,v in current_T.items() if v.startswith("0(")}

shift_mismatches = []
for n in r_t1:
    if n in cur_master_t2: shift_mismatches.append((n, "S2", "S1"))
for n in r_t2:
    if n in cur_master_t1: shift_mismatches.append((n, "S1", "S2"))

missing_from_routes_s1 = sorted(cur_master_t1 - r_t1 - r_t2)
missing_from_routes_s2 = sorted(cur_master_t2 - r_t1 - r_t2)
phantom_s1 = sorted(n for n in r_t1 if n not in cur_master_t1 and n not in cur_master_t2)
phantom_s2 = sorted(n for n in r_t2 if n not in cur_master_t1 and n not in cur_master_t2)

# 6) Decide whether to alert
any_master_change = changed or added or removed
# Also alert if routes drifted from this afternoon (someone else edited routes)
routes_changed = (r_t1 != prev_t1) or (r_t2 != prev_t2)

print(f"Master changes since baseline: changed={len(changed)} added={len(added)} removed={len(removed)}")
print(f"Routes drift since baseline: {routes_changed}")
print(f"Current mismatches: shift={len(shift_mismatches)} miss_s1={len(missing_from_routes_s1)} miss_s2={len(missing_from_routes_s2)} phantom_s1={len(phantom_s1)} phantom_s2={len(phantom_s2)}")

# 7) Save full report
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
report_path = REX / f"GOJ_Tue_Drivers_vs_MasterLog_Rescan_{ts}.md"
lines = [f"# Master-log rescan — {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
lines.append(f"Baseline: `{BASELINE.name}` ({baseline['captured_at_label']})")
lines.append("")
lines.append(f"## Master-log changes since baseline ({datetime.fromisoformat(baseline['captured_at']):%H:%M})")
lines.append("")
if not any_master_change:
    lines.append("_No changes._")
else:
    if changed:
        lines.append("**T-value changes**:")
        for n, a, b in sorted(changed):
            lines.append(f"  - {n}: `{a or '(blank)'}` → `{b or '(blank)'}`")
    if added:
        lines.append(f"\n**Added to master log ({len(added)})**:")
        for n, v in sorted(added):
            lines.append(f"  - {n} — T=`{v or '(blank)'}`")
    if removed:
        lines.append(f"\n**Removed from master log ({len(removed)})**:")
        for n in sorted(removed):
            lines.append(f"  - {n}")
lines.append("")
lines.append(f"## Routes drift since baseline: {'YES' if routes_changed else 'no'}")
if routes_changed:
    added_r1 = sorted(r_t1 - prev_t1); removed_r1 = sorted(prev_t1 - r_t1)
    added_r2 = sorted(r_t2 - prev_t2); removed_r2 = sorted(prev_t2 - r_t2)
    if added_r1: lines.append(f"  - Routes T1 added: {', '.join(added_r1)}")
    if removed_r1: lines.append(f"  - Routes T1 removed: {', '.join(removed_r1)}")
    if added_r2: lines.append(f"  - Routes T2 added: {', '.join(added_r2)}")
    if removed_r2: lines.append(f"  - Routes T2 removed: {', '.join(removed_r2)}")
lines.append("")
lines.append("## Current mismatches (routes vs. master, right now)")
lines.append("")
if shift_mismatches:
    lines.append(f"**Shift mismatches ({len(shift_mismatches)})**:")
    for n, m, r in sorted(shift_mismatches):
        lines.append(f"  - {n}: master={m}, routes={r}")
else:
    lines.append("_No shift mismatches._")
lines.append("")
if missing_from_routes_s1 or missing_from_routes_s2:
    lines.append(f"**On master but missing from routes** — S1: {len(missing_from_routes_s1)}, S2: {len(missing_from_routes_s2)}")
    for n in missing_from_routes_s1: lines.append(f"  - {n} (S1)")
    for n in missing_from_routes_s2: lines.append(f"  - {n} (S2)")
if phantom_s1 or phantom_s2:
    lines.append(f"\n**On routes but not active on master** — S1: {len(phantom_s1)}, S2: {len(phantom_s2)}")
    for n in phantom_s1:
        flag = cur_master_off.get(n, "not in master")
        lines.append(f"  - {n} (S1) — {flag}")
    for n in phantom_s2:
        flag = cur_master_off.get(n, "not in master")
        lines.append(f"  - {n} (S2) — {flag}")
report_path.write_text("\n".join(lines))
print(f"Report: {report_path}")

# 8) Send Telegram only if anything is different
if not any_master_change and not routes_changed:
    print("No changes — skipping Telegram.")
else:
    pieces = ["🌙 <b>10 PM master-log rescan — changes detected</b>", ""]
    if changed:
        pieces.append(f"<b>T-value changes ({len(changed)}):</b>")
        for n,a,b in sorted(changed)[:15]:
            pieces.append(f"  • {n}: {a or '∅'} → {b or '∅'}")
        if len(changed)>15: pieces.append(f"  …and {len(changed)-15} more")
        pieces.append("")
    if added:
        pieces.append(f"<b>Added to master ({len(added)}):</b>")
        for n,v in sorted(added)[:10]: pieces.append(f"  • {n} (T={v or '∅'})")
        if len(added)>10: pieces.append(f"  …and {len(added)-10} more")
        pieces.append("")
    if removed:
        pieces.append(f"<b>Removed from master ({len(removed)}):</b>")
        for n in sorted(removed)[:10]: pieces.append(f"  • {n}")
        if len(removed)>10: pieces.append(f"  …and {len(removed)-10} more")
        pieces.append("")
    if routes_changed:
        pieces.append("<b>Routes file also changed since 3:35 PM.</b>")
        pieces.append("")
    pieces.append(f"📋 Full report: <code>{report_path.name}</code>")
    text = "\n".join(pieces)[:3800]
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}).encode()
    r = urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data), timeout=20)
    print("Telegram:", r.status)

PYEOF

# Self-unload the LaunchAgent so this is truly one-shot
PLIST="$HOME/Library/LaunchAgents/com.kato.goj-rescan-tue-2026-05-11.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Unloaded LaunchAgent" >> "$LOG"
fi
