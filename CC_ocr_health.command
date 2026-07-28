#!/bin/bash
# CC_ocr_health.command — OCR Engine Health Check
# Probes all 4 engines and reports to terminal + Telegram

set -e
LOG_DIR="$HOME/Desktop/REX/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ocr_health_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "=== OCR Engine Health Check — $(date) ==="
echo ""

source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX

python3 - <<'PYEOF'
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REX_DIR = Path.home() / "Desktop" / "REX"
TG_CFG  = REX_DIR / "rex_rexxie_telegram_config.json"

results = {}

# ── Engine 1: Tesseract ────────────────────────────────────────────────────────
print("Checking Engine 1: Tesseract...")
try:
    r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5)
    langs = r.stdout + r.stderr
    has_rus = "rus" in langs
    has_eng = "eng" in langs
    if has_rus and has_eng:
        results["tesseract"] = ("✅", "rus+eng ready")
    else:
        missing = []
        if not has_rus: missing.append("rus")
        if not has_eng: missing.append("eng")
        results["tesseract"] = ("⚠️", f"missing langs: {', '.join(missing)}")
except FileNotFoundError:
    results["tesseract"] = ("❌", "tesseract binary not found")
except Exception as e:
    results["tesseract"] = ("❌", str(e))

# ── Engine 2: Google Drive OCR ─────────────────────────────────────────────────
print("Checking Engine 2: Google Drive OCR...")
token_path = Path.home() / ".rex_google_token.json"
try:
    token_data = json.loads(token_path.read_text())
    scopes = token_data.get("scopes", token_data.get("scope", ""))
    if isinstance(scopes, list): scopes = " ".join(scopes)
    has_file = "drive.file" in scopes or "drive " in scopes or scopes == "https://www.googleapis.com/auth/drive"
    # Quick API probe — list files
    access_token = token_data.get("token") or token_data.get("access_token", "")
    if access_token:
        req = urllib.request.Request(
            "https://www.googleapis.com/drive/v3/files?pageSize=1",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    scope_note = "" if has_file else " (missing drive.file scope — upload will 403)"
                    results["gdrive"] = ("✅" if has_file else "⚠️", f"token valid{scope_note}")
                else:
                    results["gdrive"] = ("⚠️", f"API returned {resp.status}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                results["gdrive"] = ("❌", "token expired — run CC_google_oauth_fix.command")
            elif e.code == 403:
                results["gdrive"] = ("❌", "403 scope error — run CC_google_oauth_fix.command")
            else:
                results["gdrive"] = ("⚠️", f"HTTP {e.code}")
        except Exception as e:
            results["gdrive"] = ("⚠️", f"network error: {e}")
    else:
        results["gdrive"] = ("⚠️", "token file exists but no access_token")
except FileNotFoundError:
    results["gdrive"] = ("❌", "no token — run CC_google_oauth_fix.command")
except Exception as e:
    results["gdrive"] = ("❌", str(e))

# ── Engine 3: Paperless-NGX ────────────────────────────────────────────────────
print("Checking Engine 3: Paperless-NGX...")
PAPERLESS_URL   = "http://localhost:8010"
PAPERLESS_TOKEN = "204f4af0226532176058cd174abec7a73311728a"
try:
    req = urllib.request.Request(
        f"{PAPERLESS_URL}/api/",
        headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status == 200:
            results["paperless"] = ("✅", f"running at {PAPERLESS_URL}")
        else:
            results["paperless"] = ("⚠️", f"HTTP {resp.status}")
except urllib.error.HTTPError as e:
    if e.code == 403:
        results["paperless"] = ("❌", f"token rejected (403) — token may need reset")
    else:
        results["paperless"] = ("⚠️", f"HTTP {e.code}")
except Exception:
    # Check if Docker is even running
    try:
        dr = subprocess.run(["docker", "ps", "--filter", "name=paperless", "--format", "{{.Status}}"],
                            capture_output=True, text=True, timeout=5)
        container_status = dr.stdout.strip()
        if container_status:
            results["paperless"] = ("⚠️", f"container {container_status} but port not reachable")
        else:
            results["paperless"] = ("❌", "container not running — cd ~/Desktop/REX/paperless && docker compose up -d")
    except Exception:
        results["paperless"] = ("❌", "Docker not available or Paperless not installed")

# ── Engine 4: Claude Vision ────────────────────────────────────────────────────
print("Checking Engine 4: Claude Vision...")
try:
    import os
    # Look for Anthropic API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try reading from REX config
        config_path = Path.home() / ".rex" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
            api_key = cfg.get("anthropic_api_key", "")
    if not api_key:
        # Try hermes config
        hermes_env = Path.home() / ".hermes" / "profiles" / "cloud" / ".env"
        if hermes_env.exists():
            for line in hermes_env.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if api_key:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                results["claude_vision"] = ("✅", "API key valid")
            else:
                results["claude_vision"] = ("⚠️", f"HTTP {resp.status}")
    else:
        results["claude_vision"] = ("⚠️", "API key not found in env/config")
except urllib.error.HTTPError as e:
    if e.code == 401:
        results["claude_vision"] = ("❌", "API key invalid")
    elif e.code == 402:
        results["claude_vision"] = ("❌", "credits exhausted — top up at console.anthropic.com")
    else:
        results["claude_vision"] = ("⚠️", f"HTTP {e.code}")
except Exception as e:
    results["claude_vision"] = ("⚠️", str(e))

# ── Print table ────────────────────────────────────────────────────────────────
print("")
print("=" * 60)
labels = {
    "tesseract":    "Engine 1  Tesseract",
    "gdrive":       "Engine 2  Google Drive",
    "paperless":    "Engine 3  Paperless-NGX",
    "claude_vision":"Engine 4  Claude Vision",
}
all_ok = True
lines = []
for key, label in labels.items():
    icon, msg = results.get(key, ("❓", "not checked"))
    line = f"  {icon}  {label:25s}  {msg}"
    print(line)
    lines.append(line)
    if icon not in ("✅",):
        all_ok = False

print("=" * 60)
overall = "✅ All engines healthy" if all_ok else "⚠️ One or more engines need attention"
print(f"\n{overall}\n")

# ── Send to Telegram ───────────────────────────────────────────────────────────
if TG_CFG.exists():
    try:
        cfg = json.loads(TG_CFG.read_text())
        token = cfg.get("bot_token", "")
        chat_id = cfg.get("owner_chat_id", 0)
        if token and chat_id:
            report = "🔬 <b>OCR Engine Health Check</b>\n" + "\n".join(lines) + f"\n\n{overall}"
            payload = json.dumps({"chat_id": chat_id, "text": report, "parse_mode": "HTML"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
            print("📱 Report sent to Telegram.")
    except Exception as e:
        print(f"(Telegram send failed: {e})")

PYEOF

echo ""
echo "Log: $LOG"
