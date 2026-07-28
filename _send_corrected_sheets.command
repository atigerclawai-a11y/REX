#!/usr/bin/env bash
# Send the post-sync Tuesday sign-in + driver PDFs and a delta summary to Kato.
set -u
LOG="$HOME/Desktop/REX/logs/_send_corrected_sheets.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

CFG="$HOME/Desktop/REX/rex_rexxie_telegram_config.json"
OUT="$HOME/Documents/goj files/output_docs"
DASH="$HOME/Documents/goj files/dashboard"

# Step 1 — Regenerate PDFs on host from the corrected routes file and DB
{
  echo "── Regenerating PDFs on host ──"
  cd "$DASH" && python3 generate_tomorrow.py --day tomorrow --mode signin   2>&1 | tail -8
  cd "$DASH" && python3 generate_tomorrow.py --day tomorrow --mode drivers  2>&1 | tail -8
} | tee -a "$LOG"

# Step 2 — Send delta summary + the four PDFs
python3 - <<'PYEOF' 2>&1 | tee -a "$LOG"
import json, os, sys, urllib.request, urllib.parse, mimetypes, uuid

cfg = json.load(open(os.path.expanduser("~/Desktop/REX/rex_rexxie_telegram_config.json")))
TOKEN = cfg["bot_token"]
CHAT  = str(cfg["owner_chat_id"])
OUT   = os.path.expanduser("~/Documents/goj files/output_docs")

summary = (
    "🔄 <b>UPDATED — Tuesday, May 12 sheets re-issued after master-log sync</b>\n\n"
    "Cross-checked routes vs. SIGN IN master log. Changes applied:\n"
    "  • 11 shift swaps fixed\n"
    "  • 13 clients marked off (master log flagged 0(N) — vacation/hospital)\n"
    "  • 19 clients added to drivers list (from master log, marked <i>(unassigned)</i> — please assign drivers)\n\n"
    "👥 New Tuesday counts: <b>143</b> active (S1=84, S2=59).\n\n"
    "<i>Re-issued PDFs below — please discard the 3 PM ones.</i>"
)
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = urllib.parse.urlencode({"chat_id": CHAT, "text": summary, "parse_mode": "HTML"}).encode()
resp = urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20)
print("sendMessage:", resp.status, json.loads(resp.read())["ok"])

# Send each PDF
def send_doc(path, caption):
    boundary = "----" + uuid.uuid4().hex
    body = []
    def field(name, value):
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    def file_field(name, filename, content):
        body.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/pdf\r\n\r\n".encode() + content + b"\r\n"
        )
    field("chat_id", CHAT)
    field("caption", caption)
    field("parse_mode", "HTML")
    with open(path, "rb") as fp:
        file_field("document", os.path.basename(path), fp.read())
    body.append(f"--{boundary}--\r\n".encode())
    data = b"".join(body)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendDocument",
        data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    r = urllib.request.urlopen(req, timeout=60)
    print(f"sendDocument {os.path.basename(path)}:", r.status, json.loads(r.read())["ok"])

for fname, label in [
    ("GOJ_T_S1_Tuesday_signin.pdf",   "📋 Tuesday S1 sign-in (corrected)"),
    ("GOJ_T_S2_Tuesday_signin.pdf",   "📋 Tuesday S2 sign-in (corrected)"),
    ("GOJ_T_S1_Tuesday_drivers.pdf",  "🚗 Tuesday S1 drivers (corrected)"),
    ("GOJ_T_S2_Tuesday_drivers.pdf",  "🚗 Tuesday S2 drivers (corrected)"),
]:
    p = os.path.join(OUT, fname)
    if os.path.exists(p):
        send_doc(p, label)
    else:
        print(f"MISSING: {p}")
PYEOF

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_send_corrected_sheets")' >/dev/null 2>&1 || true
