#!/bin/bash
# CC_install_russian_tessdata.command
# Installs Russian language data for Tesseract OCR.
# Required for full accuracy on GOJ Russian menu forms.
set -euo pipefail

LOG="$HOME/Desktop/REX/logs/install_russian_tessdata_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "=== Install Russian Tesseract Data ==="
echo "Date: $(date)"
echo ""

# Check if already installed
if tesseract --list-langs 2>/dev/null | grep -q "^rus$"; then
    echo "✓ Russian already installed:"
    tesseract --list-langs 2>/dev/null
    echo ""
    echo "Nothing to do."
    exit 0
fi

echo "Russian not found. Installing..."
echo ""

# Find tessdata directory
TESSDATA_DIR=""
for d in \
    /opt/homebrew/share/tessdata \
    /usr/local/share/tessdata \
    /usr/share/tessdata; do
    if [ -d "$d" ]; then
        TESSDATA_DIR="$d"
        break
    fi
done

if [ -z "$TESSDATA_DIR" ]; then
    echo "ERROR: Could not find tessdata directory."
    echo "Try: brew install tesseract  then re-run this script."
    exit 1
fi

echo "Tessdata directory: $TESSDATA_DIR"
echo "Downloading rus.traineddata (~4MB)..."
curl -L --progress-bar \
    "https://github.com/tesseract-ocr/tessdata_fast/raw/main/rus.traineddata" \
    -o "$TESSDATA_DIR/rus.traineddata"

echo ""
echo "Verifying..."
if tesseract --list-langs 2>/dev/null | grep -q "^rus$"; then
    echo "✓ Russian installed successfully"
    echo ""
    echo "Available languages:"
    tesseract --list-langs 2>/dev/null
else
    echo "✗ Install may have failed — rus not in lang list"
    echo "Try: brew install tesseract-lang"
    exit 1
fi

echo ""
echo "=== Done. You can now run CC_ocr_test.command ==="
echo "Log: $LOG"
