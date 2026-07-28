#!/usr/bin/env python3
"""
GOJ Kitchen & Distribution Handoff — Send to Kato via Telegram
Run: python3 ~/Desktop/REX/send_goj_handoff_monday.py
"""
import json, urllib.request, urllib.parse
from pathlib import Path

HERE = Path(__file__).parent  # ~/Desktop/REX/
cfg = json.load(open(HERE / "rex_rexxie_telegram_config.json"))
TOKEN = cfg["bot_token"]
CHAT_ID = cfg["owner_chat_id"]

def tg_send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as r:
        return json.loads(r.read())

def tg_send_document(path, caption=""):
    boundary = "----GOJBoundary"
    body = b""
    def part(name, value, ctype=None, fname=None):
        h = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if fname: h += f'; filename="{fname}"'
        h += "\r\n"
        if ctype: h += f"Content-Type: {ctype}\r\n"
        h += "\r\n"
        return h.encode() + (value if isinstance(value, bytes) else value.encode()) + b"\r\n"
    body += part("chat_id", str(CHAT_ID))
    body += part("caption", caption)
    body += part("parse_mode", "HTML")
    with open(path, "rb") as f:
        body += part("document", f.read(), "application/pdf", path.name)
    body += f"--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

kitchen_pdf = HERE / "kitchen_2026-04-13.pdf"
dist_s1     = HERE / "distribution_shift1_2026-04-13.pdf"
dist_s2     = HERE / "distribution_shift2_2026-04-13.pdf"

msg = (
    "🍽 <b>GOJ Kitchen &amp; Distribution Sheets — Monday, April 13, 2026</b>\n\n"
    "Clients expected: 151 (Shift 1: 82 | Shift 2: 69)\n"
    "✅ Menu data on file: 0 | ❌ Missing: 151\n\n"
    "⚠️ No menu orders found in DB for week of Apr 13. "
    "Sheets show scheduled clients — food columns are blank. "
    "Check Gmail for menu PDFs submitted approx Mar 30–Apr 6.\n\n"
    "📎 Kitchen sheet and distribution sheets (2 shifts) attached below.\n"
    "ℹ️ Sign-in + driver sheets will follow at 3 PM."
)

print("Sending summary message...")
r = tg_send_message(msg)
print(f"  → message_id: {r.get('result', {}).get('message_id', '?')}")

for label, path in [
    ("Kitchen Sheet — Monday Apr 13", kitchen_pdf),
    ("Distribution Shift 1 — Monday Apr 13", dist_s1),
    ("Distribution Shift 2 — Monday Apr 13", dist_s2),
]:
    if path.exists():
        print(f"Sending: {path.name}")
        r = tg_send_document(path, f"📄 {label}")
        print(f"  → {'✓ OK' if r.get('ok') else '✗ FAILED: ' + str(r)}")
    else:
        print(f"⚠️ Not found: {path}")

print("\n✅ Done.")
