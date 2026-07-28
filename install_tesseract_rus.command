#!/bin/bash
# ── install_tesseract_rus.command ─────────────────────────────────────────────
# Installs the Russian Tesseract language pack on the Mac mini.
# Run once. Double-click from Finder or run from Terminal.
# Required for correct OCR of Russian/Cyrillic text in GOJ documents.
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

pass() { echo "  ✅  $1"; }
fail() { echo "  ❌  $1"; }
info() { echo "  ℹ️   $1"; }

echo ""
echo "══════════════════════════════════════════════════"
echo "  Tesseract Russian Language Pack — Setup"
echo "══════════════════════════════════════════════════"
echo ""

# ── Step 1: Check Tesseract is installed ─────────────────────────────────────
if ! command -v tesseract &>/dev/null; then
    fail "Tesseract not found. Installing..."
    brew install tesseract
fi
pass "Tesseract found: $(tesseract --version 2>&1 | head -1)"

# ── Step 2: Check if rus is already installed ─────────────────────────────────
if tesseract --list-langs 2>/dev/null | grep -q "^rus$"; then
    pass "Russian language pack (rus) already installed — nothing to do."
    echo ""
    echo "  Run tesseract --list-langs to confirm."
    echo ""
    read -n 1 -s -r -p "  Press any key to close..."
    exit 0
fi

# ── Step 3: Install tesseract-lang (includes rus + all other language packs) ──
info "Installing tesseract-lang via Homebrew..."
info "This may take a moment — downloading language data files."
echo ""
brew install tesseract-lang

# ── Step 4: Verify ────────────────────────────────────────────────────────────
echo ""
if tesseract --list-langs 2>/dev/null | grep -q "^rus$"; then
    pass "Russian language pack (rus) installed successfully."
    pass "English (eng) also available: $(tesseract --list-langs 2>/dev/null | grep -c '^' ) total languages installed."
else
    fail "rus pack not found after install. Try: brew reinstall tesseract-lang"
    exit 1
fi

# ── Step 5: Quick OCR test ─────────────────────────────────────────────────────
info "Running quick language detection test..."
python3 -c "
import pytesseract
langs = pytesseract.get_languages()
if 'rus' in langs:
    print('  ✅  pytesseract sees: rus + eng available')
else:
    print('  ⚠️   pytesseract does not see rus — may need TESSDATA_PREFIX set')
    print('      Try: export TESSDATA_PREFIX=\$(brew --prefix)/share/tessdata')
" 2>/dev/null || info "pytesseract check skipped (not in current venv — that is fine)"

echo ""
echo "══════════════════════════════════════════════════"
echo "  DONE. Rexxie OCR will now handle Russian text."
echo "  Restart goj_signin_intake.py to take effect."
echo "══════════════════════════════════════════════════"
echo ""
read -n 1 -s -r -p "  Press any key to close..."
