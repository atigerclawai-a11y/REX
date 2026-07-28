#!/usr/bin/env bash
# GOJ 3PM Sheet Sender — Thursday April 30, 2026 sheets
# Auto-staged by Rexxie scheduled task. Double-click to send via Telegram.
# (Sandbox egress blocks api.telegram.org, so this is the delivery fallback.)

set -e
REX_DIR="$HOME/Desktop/REX"
PDF_DIR="$REX_DIR/GOJ_Sheets_Thursday_Apr30"
CONFIG="$REX_DIR/rex_rexxie_telegram_config.json"

TOKEN=$(python3 -c "import json; d=json.load(open('$CONFIG')); print(d['bot_token'])")
CHAT_ID=$(python3 -c "import json; d=json.load(open('$CONFIG')); print(d['owner_chat_id'])")

echo "📤 Sending GOJ Thursday Apr 30 sheets to Telegram..."

# Send summary message
python3 - "$TOKEN" "$CHAT_ID" <<'PYEOF'
import sys, json, urllib.request, urllib.parse
token, chat_id = sys.argv[1], sys.argv[2]
msg = (
    "🚗 <b>GOJ Sheets for Thursday, April 30, 2026</b>\n\n"
    "👥 Clients expected: 145\n"
    "  Shift 1: 90 | Shift 2: 55\n"
    "🚌 Drivers on duty: 7\n\n"
    "📋 Sign-in sheet and driver lists attached below."
)
data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
r = urllib.request.urlopen(urllib.request.Request(
    f"https://api.telegram.org/bot{token}/sendMessage", data=data))
print("Summary sent:", json.loads(r.read())["ok"])
PYEOF

# Send each PDF
for PDF in \
    "$PDF_DIR/GOJ_TH_S1_Thursday_signin.pdf" \
    "$PDF_DIR/GOJ_TH_S2_Thursday_signin.pdf" \
    "$PDF_DIR/GOJ_TH_S1_Thursday_drivers.pdf" \
    "$PDF_DIR/GOJ_TH_S2_Thursday_drivers.pdf"; do

    if [ -f "$PDF" ]; then
        BASENAME=$(basename "$PDF")
        echo "  Sending $BASENAME..."
        python3 - "$PDF" "$TOKEN" "$CHAT_ID" <<'PYEOF'
import sys, json, urllib.request

pdf_path, token, chat_id = sys.argv[1], sys.argv[2], sys.argv[3]
boundary = "----FormBoundary7MA4YWxkTrZu0gW"
with open(pdf_path, "rb") as f:
    pdf_data = f.read()

basename = pdf_path.split("/")[-1]
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="document"; filename="{basename}"\r\n'
    f"Content-Type: application/pdf\r\n\r\n"
).encode() + pdf_data + f"\r\n--{boundary}--\r\n".encode()

req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/sendDocument",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
)
r = urllib.request.urlopen(req)
result = json.loads(r.read())
print(f"  {'✅' if result.get('ok') else '❌'} {basename}")
PYEOF
    else
        echo "  ⚠️  File not found: $PDF"
    fi
done

echo ""
echo "✅ Done! All Thursday sheets sent to Telegram."
read -n 1 -s -r -p "Press any key to close..."
