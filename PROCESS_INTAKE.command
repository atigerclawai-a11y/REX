#!/bin/bash
#
# PROCESS_INTAKE.command
# Interactive file intake processor for ledger system
# Routes incoming files for review or quarantine
#
# Usage: Run from ~/Desktop/REX/
# Processes files in: ~/Desktop/REX/LEDGER_REVIEW_INBOX/
#

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

REX_ROOT="$HOME/Desktop/REX"
INBOX="$REX_ROOT/LEDGER_REVIEW_INBOX"
QUARANTINE="$REX_ROOT/QUARANTINE"
REVIEW_LATER="$REX_ROOT/LEDGER_REVIEW_LATER"
LEDGER_DB="$REX_ROOT/data/ledger.db"

# Ensure directories exist
mkdir -p "$INBOX" "$QUARANTINE" "$REVIEW_LATER"

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}[PROCESS_INTAKE]${NC} File intake processor"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

# Check if inbox is empty
FILE_COUNT=$(find "$INBOX" -maxdepth 1 -type f 2>/dev/null | wc -l)

if [ "$FILE_COUNT" -eq 0 ]; then
    echo -e "${GREEN}[OK]${NC} LEDGER_REVIEW_INBOX is empty"
    exit 0
fi

echo -e "${YELLOW}[INBOX]${NC} Found $FILE_COUNT file(s) to review"
echo ""

# Process each file in inbox
FILE_INDEX=1
find "$INBOX" -maxdepth 1 -type f -print0 | while IFS= read -r -d '' FILE; do
    FILE_NAME=$(basename "$FILE")
    FILE_TYPE=$(file -b "$FILE" | cut -d, -f1)
    FILE_SIZE=$(stat -f%z "$FILE" 2>/dev/null || echo "unknown")

    echo -e "${BLUE}─────────────────────────────────────${NC}"
    echo -e "File $FILE_INDEX: ${YELLOW}$FILE_NAME${NC}"
    echo "Type: $FILE_TYPE"
    echo "Size: $FILE_SIZE bytes"
    echo ""

    # Show file preview (first 10 lines or 500 chars)
    if [ -f "$FILE" ]; then
        if file -b "$FILE" | grep -q "text"; then
            echo -e "${BLUE}[PREVIEW]${NC}"
            head -n 10 "$FILE" | sed 's/^/  /'
            echo ""
        else
            echo -e "${BLUE}[FILE]${NC} Binary file (not previewed)"
            echo ""
        fi
    fi

    # Prompt for decision
    echo -e "${YELLOW}Decision:${NC}"
    echo "  (k) Keep — keep in inbox for review later"
    echo "  (q) Quarantine — move to QUARANTINE/ (suspicious/broken)"
    echo "  (r) Review Later — move to REVIEW_LATER/ (low priority)"
    echo "  (x) Examine — print full contents (text files only)"
    echo ""

    read -p "Enter decision [k/q/r/x]: " DECISION

    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    case "$DECISION" in
        k|K)
            echo -e "${GREEN}✓${NC} Keeping in inbox"
            ;;
        q|Q)
            echo -e "${YELLOW}[QUARANTINE]${NC} Moving to quarantine..."
            mv "$FILE" "$QUARANTINE/$FILE_NAME"

            # Log to ledger
            if [ -f "$LEDGER_DB" ]; then
                sqlite3 "$LEDGER_DB" << EOFSQL
INSERT INTO intake_log (
    intake_at, file_path, file_type, subsystem,
    probable_purpose, contradicts_framework,
    status, triggered_build_ledger_update,
    triggered_decision_history_update, notes
) VALUES (
    '$TIMESTAMP',
    '$FILE',
    '$FILE_TYPE',
    'intake',
    'unknown',
    1,
    'quarantined',
    0,
    1,
    'Quarantined via PROCESS_INTAKE: possibly corrupt or contradicts framework'
);
EOFSQL
                echo -e "${GREEN}✓${NC} Logged to ledger.db"
            fi

            # Append to quarantine log
            echo "$TIMESTAMP | $FILE_NAME | $FILE_TYPE | Quarantined via PROCESS_INTAKE" >> "$QUARANTINE/MANIFEST.log"
            echo -e "${GREEN}✓${NC} Appended to QUARANTINE/MANIFEST.log"
            ;;
        r|R)
            echo -e "${YELLOW}[REVIEW_LATER]${NC} Moving to review later..."
            mv "$FILE" "$REVIEW_LATER/$FILE_NAME"

            # Log to ledger
            if [ -f "$LEDGER_DB" ]; then
                sqlite3 "$LEDGER_DB" << EOFSQL
INSERT INTO intake_log (
    intake_at, file_path, file_type, subsystem,
    probable_purpose, contradicts_framework,
    status, triggered_build_ledger_update,
    triggered_decision_history_update, notes
) VALUES (
    '$TIMESTAMP',
    '$FILE',
    '$FILE_TYPE',
    'intake',
    'unknown',
    0,
    'review_later',
    0,
    0,
    'Low priority: defer to later review'
);
EOFSQL
                echo -e "${GREEN}✓${NC} Logged to ledger.db"
            fi

            # Append to review later log
            echo "$TIMESTAMP | $FILE_NAME | Low priority" >> "$REVIEW_LATER/MANIFEST.log"
            echo -e "${GREEN}✓${NC} Appended to REVIEW_LATER/MANIFEST.log"
            ;;
        x|X)
            echo -e "${BLUE}[CONTENTS]${NC}"
            if file -b "$FILE" | grep -q "text"; then
                cat "$FILE" | sed 's/^/  /'
            else
                echo "  (Binary file — cannot display)"
            fi
            echo ""
            echo "Re-prompt for decision..."
            ;;
        *)
            echo -e "${RED}[SKIP]${NC} Invalid decision (skipping)"
            ;;
    esac

    echo ""
    FILE_INDEX=$((FILE_INDEX + 1))
done

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${GREEN}[COMPLETE]${NC} Intake processing finished"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""
echo "Summary:"
echo "  Inbox:        $INBOX"
echo "  Quarantine:   $QUARANTINE"
echo "  Review Later: $REVIEW_LATER"
echo "  Ledger DB:    $LEDGER_DB"
echo ""

# Show updated file counts
REMAINING=$(find "$INBOX" -maxdepth 1 -type f 2>/dev/null | wc -l)
QUARANTINED=$(find "$QUARANTINE" -maxdepth 1 -type f 2>/dev/null | wc -l)
DEFERRED=$(find "$REVIEW_LATER" -maxdepth 1 -type f 2>/dev/null | wc -l)

echo "Files:"
echo "  In inbox:        $REMAINING"
echo "  Quarantined:     $QUARANTINED"
echo "  Deferred review: $DEFERRED"
echo ""
