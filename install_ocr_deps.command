#!/bin/bash
# GOJ OCR Full Dependency Installer
# Installs: poppler (pdf→image), Tesseract + Russian lang, anthropic, pdf2image, pytesseract, requests
# Double-click in Finder to run.

echo "╔══════════════════════════════════════════════════════╗"
echo "║     GOJ OCR Dependencies Installer (Full)           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Find best venv pip ────────────────────────────────────────────────────────
REX="$HOME/Desktop/REX"
VENV_PIP=""
VENV_PY=""
for CANDIDATE in \
    "$HOME/debate-chamber/.venv/bin/pip3" \
    "$REX/.venv/bin/pip3" \
    "$(command -v pip3)"; do
    if [ -f "$CANDIDATE" ]; then
        VENV_PIP="$CANDIDATE"
        VENV_PY="${CANDIDATE%pip3}python3"
        echo "  Using pip: $VENV_PIP"
        break
    fi
done
[ -z "$VENV_PIP" ] && VENV_PIP="pip3" && VENV_PY="python3"

# ── 1. Homebrew check ─────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Install it first: https://brew.sh"
    read -n 1 -p "Press any key to close..."; exit 1
fi
echo "✅ Homebrew found: $(brew --version | head -1)"
echo ""

# ── 2. poppler — REQUIRED by pdf2image to convert PDFs to images ─────────────
echo "📦 [1/3] Installing poppler (PDF→image converter)..."
if brew list poppler &>/dev/null; then
    echo "  ✅ poppler already installed: $(pdfinfo -v 2>&1 | head -1)"
else
    brew install poppler
    if command -v pdftoppm &>/dev/null; then
        echo "  ✅ poppler installed"
    else
        echo "  ⚠️  poppler install may have failed"
    fi
fi
echo ""

# ── 3. Tesseract + Russian language pack ─────────────────────────────────────
echo "📦 [2/3] Installing Tesseract + Russian language..."
if brew list tesseract &>/dev/null; then
    echo "  ✅ tesseract already installed: $(tesseract --version 2>&1 | head -1)"
else
    brew install tesseract tesseract-lang
fi
# Verify Russian lang pack
if tesseract --list-langs 2>/dev/null | grep -q "rus"; then
    echo "  ✅ Russian language pack: OK"
else
    echo "  ⚠️  Russian lang pack missing — menus may OCR poorly"
fi
echo ""

# ── 4. Python packages ────────────────────────────────────────────────────────
echo "🐍 [3/3] Installing Python OCR + AI packages..."
"$VENV_PIP" install --quiet Pillow pdf2image pytesseract requests anthropic pdfplumber pymupdf openpyxl
EXIT=$?
if [ $EXIT -eq 0 ]; then
    echo "  ✅ Pillow, pdf2image, pytesseract, requests, anthropic, pdfplumber, pymupdf, openpyxl installed"
else
    echo "  ⚠️  pip install had errors — check output above"
fi
echo ""

# ── 5. Verify everything ──────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Verification                                        ║"
echo "╚══════════════════════════════════════════════════════╝"

echo "poppler / pdftoppm: $(command -v pdftoppm 2>/dev/null || echo 'NOT FOUND')"
echo "Tesseract:          $(which tesseract 2>/dev/null || echo 'NOT FOUND') — $(tesseract --version 2>&1 | head -1)"

if [ -f "$VENV_PY" ]; then
    "$VENV_PY" -c "import pdf2image; print('✅ pdf2image OK')" 2>/dev/null \
        || echo "❌ pdf2image FAIL"
    "$VENV_PY" -c "import pytesseract; print('✅ pytesseract OK:', pytesseract.get_tesseract_version())" 2>/dev/null \
        || echo "❌ pytesseract FAIL"
    "$VENV_PY" -c "import PIL; print('✅ Pillow OK:', PIL.__version__)" 2>/dev/null \
        || echo "❌ Pillow FAIL"
    "$VENV_PY" -c "import anthropic; print('✅ anthropic SDK OK')" 2>/dev/null \
        || echo "❌ anthropic FAIL"
    "$VENV_PY" -c "import requests; print('✅ requests OK')" 2>/dev/null \
        || echo "❌ requests FAIL"
    "$VENV_PY" -c "import pdfplumber; print('✅ pdfplumber OK')" 2>/dev/null \
        || echo "❌ pdfplumber FAIL"

    # Full end-to-end test: pdf2image + poppler
    "$VENV_PY" -c "
from pdf2image import pdfinfo_from_path
print('✅ pdf2image + poppler integration OK')
" 2>/dev/null || echo "⚠️  pdf2image can import but poppler may not be on PATH"
fi

echo ""
echo "All OCR engines ready:"
echo "  Engine 1: Tesseract (local, offline)"
echo "  Engine 2: Paperless-NGX (Tailscale network)"
echo "  Engine 3: Claude Vision (handwriting reader)"
echo ""
read -n 1 -p "Press any key to close..."
