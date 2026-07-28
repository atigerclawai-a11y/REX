#!/usr/bin/env bash
# ============================================================
# SAVE_KEY_TO_KEYCHAIN.command
# Reads keys from .env → saves each one to macOS Keychain
# via the same keyring library that RESTORE_ENV.command reads.
# Run once after adding/updating keys in .env.
# ============================================================

REX="$HOME/Desktop/REX"
ENV_FILE="$REX/.env"
APP="REX"

echo "============================================"
echo "  REX — Save .env keys to macOS Keychain"
echo "  $(date)"
echo "============================================"
echo ""

if [ ! -f "$ENV_FILE" ]; then
    echo "❌  .env not found at $ENV_FILE"
    exit 1
fi

# Python detection
PY=""
for CANDIDATE in "$REX/.venv/bin/python3" "$HOME/debate-chamber/.venv/bin/python3" "$(command -v python3)"; do
    if [ -f "$CANDIDATE" ]; then PY="$CANDIDATE"; break; fi
done
[ -z "$PY" ] && PY="python3"

"$PY" - <<'PYEOF'
import keyring
from pathlib import Path

APP = "REX"
ENV_FILE = Path.home() / "Desktop/REX/.env"

KEY_MAP = {
    "ANTHROPIC_API_KEY":  "rex_anthropic_api_key",
    "OPENAI_API_KEY":     "rex_openai_api_key",
    "GEMINI_API_KEY":     "rex_gemini_api_key",
    "XAI_API_KEY":        "rex_xai_api_key",
    "PERPLEXITY_API_KEY": "rex_perplexity_api_key",
}

saved = 0
skipped = 0

for line in ENV_FILE.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"): continue
    if "=" not in line: continue
    var, _, val = line.partition("=")
    var = var.strip(); val = val.strip()
    if not val: continue
    kc_name = KEY_MAP.get(var)
    if not kc_name: continue
    try:
        keyring.set_password(APP, kc_name, val)
        masked = val[:8] + "..." + val[-4:]
        print(f"  ✅  {var} saved ({masked})")
        saved += 1
    except Exception as e:
        print(f"  ❌  {var} failed: {e}")
        skipped += 1

print(f"\n  Saved: {saved}  |  Failed: {skipped}")
print(f"\n  Run RESTORE_ENV.command any time to recreate .env from Keychain.")
PYEOF

echo ""
echo "Press Enter to close..."
read
