#!/bin/bash
# GOJ OCR Engine Fix Script — Engines 1, 2, 3
# Run with: bash ~/Desktop/REX/fix_ocr_engines.sh
# April 2026

set -e
VENV="$HOME/debate-chamber/.venv"
REX="$HOME/Desktop/REX"
LOG="$REX/logs/ocr_fix_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$REX/logs"
exec > >(tee -a "$LOG") 2>&1

echo "======================================"
echo " GOJ OCR Engine Fix — $(date)"
echo "======================================"

# ── ENGINE 1: Tesseract + Pillow ──────────────────────────────────────────────
echo ""
echo "▶ ENGINE 1 — Pillow / pdf2image / pytesseract"
echo "  Activating venv: $VENV"
source "$VENV/bin/activate"

echo "  Installing Python packages..."
pip install --upgrade --quiet Pillow pdf2image pytesseract
echo "  ✅ Python packages installed"

echo "  Checking tesseract CLI..."
if ! command -v tesseract &>/dev/null; then
    echo "  tesseract not found — installing via Homebrew..."
    brew install tesseract tesseract-lang
    echo "  ✅ tesseract installed"
else
    echo "  ✅ tesseract already present: $(tesseract --version 2>&1 | head -1)"
fi

echo "  Checking Russian language pack..."
if tesseract --list-langs 2>/dev/null | grep -q "rus"; then
    echo "  ✅ Russian language pack found"
else
    echo "  ⚠️  Russian not found — installing tesseract-lang..."
    brew install tesseract-lang || true
    # Try downloading rus.traineddata manually if still missing
    TESSDATA=$(tesseract --print-parameters 2>/dev/null | grep tessdata_dir | awk '{print $2}' || true)
    if [ -n "$TESSDATA" ] && [ ! -f "$TESSDATA/rus.traineddata" ]; then
        echo "  Downloading rus.traineddata..."
        curl -sL "https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata" -o "$TESSDATA/rus.traineddata"
    fi
    if tesseract --list-langs 2>/dev/null | grep -q "rus"; then
        echo "  ✅ Russian language pack installed"
    else
        echo "  ⚠️  Could not install Russian — Engine 1 will fall back to English OCR"
    fi
fi

# ── ENGINE 2: Google Drive credentials ───────────────────────────────────────
echo ""
echo "▶ ENGINE 2 — Google Drive OCR credentials"
SRC="$REX/google_credentials.json"
DEST="$HOME/.rex_google_credentials.json"

if [ -f "$SRC" ]; then
    cp "$SRC" "$DEST"
    echo "  ✅ Credentials copied: $DEST ($(wc -c < "$DEST") bytes)"
else
    echo "  ❌ Source not found: $SRC"
    echo "     Google Drive OCR will be unavailable"
fi

# ── ENGINE 3: Paperless / Tailscale ──────────────────────────────────────────
echo ""
echo "▶ ENGINE 3 — Paperless-ngx via Tailscale (100.99.86.60:8000)"
if command -v tailscale &>/dev/null; then
    STATUS=$(tailscale status 2>&1 | head -3)
    echo "  Tailscale status: $STATUS"
    if echo "$STATUS" | grep -qi "logged in\|100\."; then
        echo "  Testing Paperless connection..."
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: Token 583e819be1146b96b935007c6ad7f584a3a1b1b7" \
            http://100.99.86.60:8000/api/documents/ --max-time 5 2>/dev/null || echo "000")
        if [ "$HTTP" = "200" ]; then
            echo "  ✅ Paperless reachable (HTTP $HTTP)"
        else
            echo "  ⚠️  Paperless returned HTTP $HTTP — may be down on remote machine"
        fi
    else
        echo "  ⚠️  Tailscale not connected — connect it manually, then re-run this script for Engine 3"
    fi
else
    echo "  ⚠️  tailscale CLI not found — connect Tailscale app manually for Engine 3"
fi

# ── SMOKE TEST ────────────────────────────────────────────────────────────────
echo ""
echo "▶ SMOKE TEST — running OCR on first available menu PDF"
MENU_DIR="$HOME/Documents/goj files/dashboard/documents/menus"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
SCRIPT="$REX/goj_menu_consensus_ocr.py"

if [ -f "$SCRIPT" ] && [ -d "$MENU_DIR" ]; then
    source "$VENV/bin/activate"
    echo "  Running consensus OCR (first 60 lines of output)..."
    python3 "$SCRIPT" \
        --menu-dir "$MENU_DIR" \
        --db "$DB" \
        --learning "$REX/goj_menu_learning.json" \
        --flags "$REX/goj_menu_flags_queue.json" \
        2>&1 | head -60
else
    echo "  ⚠️  OCR script or menu directory not found — skipping smoke test"
fi

echo ""
echo "======================================"
echo " Fix complete — log saved to:"
echo " $LOG"
echo "======================================"
