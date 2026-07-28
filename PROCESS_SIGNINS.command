#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  PROCESS SIGNINS — Runs goj_signin_intake.py on all PDFs in
#  ~/Desktop/REX/signins/ and routes them to the right folders.
#  Double-click to run.
# ═══════════════════════════════════════════════════════════════════

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

REX_DIR="$HOME/Desktop/REX"
SIGNINS="$REX_DIR/signins"

VENV_PYTHON=""
for CANDIDATE in \
    "$HOME/debate-chamber/.venv/bin/python3" \
    "$REX_DIR/.venv/bin/python3" \
    "$(command -v python3)"; do
    [ -f "$CANDIDATE" ] && VENV_PYTHON="$CANDIDATE" && break
done

echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  📂 GOJ Document Intake${NC}"
echo -e "${BOLD}  $(date '+%b %d %Y %I:%M %p')${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Count waiting PDFs
PDF_COUNT=$(ls "$SIGNINS"/*.pdf 2>/dev/null | wc -l | tr -d ' ')

if [ "$PDF_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ No PDFs waiting in signins/ — nothing to process.${NC}"
    echo ""
    echo "Drop PDFs into ~/Desktop/REX/signins/ to queue them."
    echo ""
    echo "Press Enter to close..."; read; exit 0
fi

echo -e "  Found ${BOLD}$PDF_COUNT PDF(s)${NC} to process:"
ls "$SIGNINS"/*.pdf 2>/dev/null | while read f; do
    echo -e "    📄 $(basename "$f")"
done
echo ""

# Run intake
echo -e "${CYAN}Running goj_signin_intake.py...${NC}"
echo "────────────────────────────────────────"
cd "$REX_DIR" && "$VENV_PYTHON" goj_signin_intake.py
EXIT_CODE=$?
echo "────────────────────────────────────────"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    REMAINING=$(ls "$SIGNINS"/*.pdf 2>/dev/null | wc -l | tr -d ' ')
    if [ "$REMAINING" -eq 0 ]; then
        echo -e "${GREEN}${BOLD}✅ All PDFs processed and filed.${NC}"
    else
        echo -e "${YELLOW}⚠️  $REMAINING PDF(s) still in signins/ — may need manual review.${NC}"
        ls "$SIGNINS"/*.pdf 2>/dev/null | while read f; do
            echo -e "    📄 $(basename "$f")"
        done
    fi
else
    echo -e "${RED}❌ Intake exited with code $EXIT_CODE — check output above.${NC}"
    echo -e "${YELLOW}   If fitz errors appear, run fix_fitz.command first.${NC}"
fi

echo ""
echo "Press Enter to close..."
read
