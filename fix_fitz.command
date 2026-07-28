#!/usr/bin/env bash
# Quick fix: installs pymupdf (fitz) into the debate-chamber venv
# Needed for OCR Engine 2 (Tesseract + fitz path)

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

VENV_PIP=""
for CANDIDATE in \
    "$HOME/debate-chamber/.venv/bin/pip3" \
    "$HOME/Desktop/REX/.venv/bin/pip3"; do
    [ -f "$CANDIDATE" ] && VENV_PIP="$CANDIDATE" && break
done
[ -z "$VENV_PIP" ] && VENV_PIP="pip3"

VENV_PYTHON="${VENV_PIP%pip3}python3"

echo -e "${BOLD}${CYAN}Installing pymupdf (fitz) into venv...${NC}"
echo -e "Using: $VENV_PIP"
echo ""

"$VENV_PIP" install pymupdf

echo ""
echo -e "${CYAN}Verifying...${NC}"
RESULT=$("$VENV_PYTHON" -c "import fitz; print('fitz', fitz.__version__)" 2>&1)
if echo "$RESULT" | grep -q "fitz"; then
    echo -e "${GREEN}${BOLD}✅ $RESULT — fitz is ready.${NC}"
    echo ""
    echo "OCR Engine 2 (Tesseract + fitz) is now fully operational."
    echo "Run TEST_OCR.command to confirm all engines pass."
else
    echo -e "${RED}❌ Still not importable: $RESULT${NC}"
fi

echo ""
echo "Press Enter to close..."
read
