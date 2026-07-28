#!/bin/bash
# ====================================================================
#  GOJ Vision OCR Runner
#  Processes the flag queue using Claude Vision (Engine 4)
#  Clears items that Tesseract could not confidently read.
#
#  Double-click to run.
#  Requires: Tailscale connected (for Paperless), internet (for Claude API)
# ====================================================================

set -uo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

REX="$HOME/Desktop/REX"
LOG_DIR="$REX/logs"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/vision_ocr_${TS}.log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║     GOJ Vision OCR Runner — $(date +%Y-%m-%d\ %H:%M)        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Python detection ──────────────────────────────────────────────────────────
PY=""
for CANDIDATE in \
    "$HOME/debate-chamber/.venv/bin/python3" \
    "$REX/.venv/bin/python3" \
    "$(command -v python3 2>/dev/null)"; do
    [ -f "$CANDIDATE" ] && PY="$CANDIDATE" && break
done
[ -z "$PY" ] && echo "❌  No Python found." && read -n 1 && exit 1
echo "  Python: $PY"
echo ""

# ── Dependency check ──────────────────────────────────────────────────────────
echo "─── Dependency check ───────────────────────────────────"
MISSING=0
for MOD in anthropic pdf2image pdfplumber; do
    if "$PY" -c "import $MOD" 2>/dev/null; then
        echo "  ✅  $MOD"
    else
        echo "  ❌  $MOD NOT installed"
        MISSING=$((MISSING+1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "  ⚠️  Missing $MISSING package(s)."
    echo "  Run install_ocr_deps.command first, then retry."
    echo ""
    read -n 1 -p "Press any key to close..."
    exit 1
fi
echo ""

# ── API key check ─────────────────────────────────────────────────────────────
echo "─── API key ────────────────────────────────────────────"
if grep -q "^ANTHROPIC_API_KEY=sk-ant-" "$REX/.env" 2>/dev/null; then
    echo "  ✅  ANTHROPIC_API_KEY found in .env"
else
    echo "  ❌  ANTHROPIC_API_KEY missing from $REX/.env"
    echo "  Add it and retry."
    read -n 1 -p "Press any key to close..."
    exit 1
fi
echo ""

# ── Flag queue status ─────────────────────────────────────────────────────────
echo "─── Flag queue ─────────────────────────────────────────"
"$PY" - <<'PYEOF'
import json
from pathlib import Path
flags_path = Path.home() / "Desktop" / "REX" / "goj_menu_flags_queue.json"
if not flags_path.exists():
    print("  ⚠️  Flag queue not found")
else:
    flags = json.loads(flags_path.read_text())
    total    = len(flags)
    resolved = sum(1 for f in flags if f.get('resolved'))
    pending  = total - resolved
    print(f"  Total:    {total}")
    print(f"  Resolved: {resolved}")
    print(f"  Pending:  {pending}")
    if pending == 0:
        print("  ✅  Nothing to process — queue is clear!")
PYEOF
echo ""

# ── Tailscale / Paperless check ───────────────────────────────────────────────
echo "─── Paperless connection ───────────────────────────────"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Token 583e819be1146b96b935007c6ad7f584a3a1b1b7" \
    "http://100.99.86.60:8000/api/documents/?page_size=1" \
    --connect-timeout 5 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✅  Paperless reachable (HTTP $HTTP_CODE)"
else
    echo "  ❌  Paperless not reachable (HTTP $HTTP_CODE)"
    echo "  Make sure Tailscale is connected and the home server is on."
    echo "  Cannot process flags without Paperless to download PDFs."
    read -n 1 -p "Press any key to close..."
    exit 1
fi
echo ""

# ── Run the processor ─────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════"
echo "  Starting Vision OCR processor..."
echo "  (This may take a few minutes — Claude processes each form)"
echo "════════════════════════════════════════════════════════"
echo ""

cd "$REX"
"$PY" "$REX/rex_vision_flag_processor.py"
EXIT=$?

echo ""
if [ $EXIT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  ✅  Vision OCR processor completed successfully.${NC}"
else
    echo -e "${RED}${BOLD}  ❌  Processor exited with code $EXIT — check output above.${NC}"
fi

echo ""
echo "  Full log saved to: $LOG"
echo ""
read -n 1 -p "Press any key to close..."
