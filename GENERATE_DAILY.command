#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  GOJ DAILY FILE GENERATOR
#  Generates sign-in, food distribution, kitchen, and driver files
#  for today (or a date you specify). Double-click to run.
# ═══════════════════════════════════════════════════════════════════

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

REX_DIR="$HOME/Desktop/REX"
DAILY_DIR="$HOME/Documents/goj files/dashboard/daily"

VENV_PYTHON=""
for CANDIDATE in \
    "$HOME/debate-chamber/.venv/bin/python3" \
    "$REX_DIR/.venv/bin/python3" \
    "$(command -v python3)"; do
    [ -f "$CANDIDATE" ] && VENV_PYTHON="$CANDIDATE" && break
done

clear
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  📅 GOJ Daily File Generator${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Ask for date (default today)
TODAY=$(date '+%Y-%m-%d')
DAY_NAME=$(date '+%A')
echo -e "  Today is ${BOLD}$DAY_NAME, $TODAY${NC}"
echo -e "  Press Enter to generate for TODAY, or type a date (YYYY-MM-DD):"
echo -n "  > "
read USER_DATE
TARGET="${USER_DATE:-$TODAY}"

# Validate date format
if ! date -j -f "%Y-%m-%d" "$TARGET" +"%Y-%m-%d" >/dev/null 2>&1; then
    echo -e "${RED}❌ Invalid date: $TARGET${NC}"
    echo "Press Enter to close..."; read; exit 1
fi

echo ""
echo -e "  Generating files for: ${BOLD}$TARGET${NC}"
echo ""

# Step 1: Sync master menu from DB
echo -e "${CYAN}[1/2] Syncing master menu spreadsheet...${NC}"
cd "$REX_DIR" && "$VENV_PYTHON" goj_master_menu.py 2>&1
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Master menu sync had issues — continuing with daily generation${NC}"
fi
echo ""

# Step 2: Generate daily files
echo -e "${CYAN}[2/2] Generating daily operation files...${NC}"
cd "$REX_DIR" && "$VENV_PYTHON" goj_generate_daily.py "$TARGET" 2>&1
EXIT=$?
echo ""

if [ $EXIT -eq 0 ]; then
    OUT_DIR="$DAILY_DIR/$TARGET"
    echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}${BOLD}  ✅ Files ready in:${NC}"
    echo -e "  $OUT_DIR"
    echo ""
    echo -e "  Files generated:"
    ls "$OUT_DIR"/*.xlsx 2>/dev/null | while read f; do
        echo -e "    📊 $(basename "$f")"
    done
    echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    # Open the folder in Finder
    open "$OUT_DIR" 2>/dev/null || true
else
    echo -e "${RED}❌ Generation failed — check output above${NC}"
    echo -e "${YELLOW}Make sure install_ocr_deps.command was run (needs openpyxl).${NC}"
fi

echo ""
echo "Press Enter to close..."
read
