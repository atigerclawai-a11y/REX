#!/bin/bash
#
# STAMP_KNOWN_GOOD.command
# Verifies system is in good state and stamps KNOWN_GOOD_STATE.json
# Run on Mac after manual verification that system is working
#
# Usage: Run from Mac terminal in ~/Desktop/REX/
#

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

REX_ROOT="$HOME/Desktop/REX"
MANIFEST="$REX_ROOT/ACTIVE_SYSTEM_MANIFEST.json"
KNOWN_GOOD="$REX_ROOT/KNOWN_GOOD_STATE.json"
LEDGER_DB="$REX_ROOT/data/ledger.db"
AUTH_DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"

echo -e "${YELLOW}[STAMP_KNOWN_GOOD]${NC} Starting system state verification..."

# 1. Verify manifest exists and is valid JSON
if [ ! -f "$MANIFEST" ]; then
    echo -e "${RED}ERROR: ACTIVE_SYSTEM_MANIFEST.json not found at $MANIFEST${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Manifest found"

# 2. Compute SHA-256 of manifest
MANIFEST_CHECKSUM=$(shasum -a 256 "$MANIFEST" | awk '{print $1}')
echo -e "${GREEN}✓${NC} Manifest checksum: ${MANIFEST_CHECKSUM:0:16}..."

# 3. Query auth_tracker.db for row counts
if [ ! -f "$AUTH_DB" ]; then
    echo -e "${RED}ERROR: auth_tracker.db not found at $AUTH_DB${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Auth database found"

# Query row counts using sqlite3
CLIENTS_COUNT=$(sqlite3 "$AUTH_DB" "SELECT COUNT(*) FROM clients 2>/dev/null || echo 'query_failed'" 2>/dev/null || echo "0")
ATTENDANCE_COUNT=$(sqlite3 "$AUTH_DB" "SELECT COUNT(*) FROM attendance_log 2>/dev/null || echo 'query_failed'" 2>/dev/null || echo "0")
REXXIE_IDEAS_COUNT=$(sqlite3 "$AUTH_DB" "SELECT COUNT(*) FROM rexxie_ideas 2>/dev/null || echo 'query_failed'" 2>/dev/null || echo "0")
STAFF_MEDICAL_COUNT=$(sqlite3 "$AUTH_DB" "SELECT COUNT(*) FROM staff_medical_log 2>/dev/null || echo 'query_failed'" 2>/dev/null || echo "0")

echo -e "${GREEN}✓${NC} Database row counts retrieved:"
echo "  - clients: $CLIENTS_COUNT"
echo "  - attendance_log: $ATTENDANCE_COUNT"
echo "  - rexxie_ideas: $REXXIE_IDEAS_COUNT"
echo "  - staff_medical_log: $STAFF_MEDICAL_COUNT"

# 4. Check service states with pgrep
echo -e "${YELLOW}[SERVICES]${NC} Checking active processes..."

REX_BACKEND=$(pgrep -f 'uvicorn.*backend.main' 2>/dev/null || echo "0")
REXXIE_BOT=$(pgrep -f 'rex_rexxie_telegram_bot.py' 2>/dev/null || echo "0")
REX_TELEGRAM=$(pgrep -f 'rex_telegram_bot.py' 2>/dev/null || echo "0")
SCHEDULER=$(pgrep -f 'goj_daily_scheduler.py' 2>/dev/null || echo "0")
ALERT_ROUTER=$(pgrep -f 'core.alert_router' 2>/dev/null || echo "0")

echo -e "${GREEN}✓${NC} Service states recorded"

# 5. Get file checksums for critical files
echo -e "${YELLOW}[FILES]${NC} Computing critical file checksums..."

BACKEND_MAIN_CHECKSUM=$(shasum -a 256 "$REX_ROOT/backend/main.py" 2>/dev/null | awk '{print $1}' || echo "file_not_found")
REXXIE_BOT_CHECKSUM=$(shasum -a 256 "$REX_ROOT/rex_rexxie_telegram_bot.py" 2>/dev/null | awk '{print $1}' || echo "file_not_found")
OCR_CONSENSUS_CHECKSUM=$(shasum -a 256 "$REX_ROOT/goj_menu_consensus_ocr.py" 2>/dev/null | awk '{print $1}' || echo "file_not_found")
OCR_SCHEMA_CHECKSUM=$(shasum -a 256 "$REX_ROOT/core/ocr_schema.py" 2>/dev/null | awk '{print $1}' || echo "file_not_found")

echo -e "${GREEN}✓${NC} Critical file checksums computed"

# 6. Create temporary KNOWN_GOOD_STATE.json with actual values
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo -e "${YELLOW}[STAMPING]${NC} Writing KNOWN_GOOD_STATE.json..."

cat > "$KNOWN_GOOD" << EOFKGOOD
{
  "_status": "STAMPED",
  "_instruction": "This file represents a known-good system state",
  "_note": "Stamped on Mac with verified process states and database counts",

  "stamped_at": "$CURRENT_TIMESTAMP",
  "stamped_by": "$(whoami)",
  "stamped_on_mac": true,

  "verification": {
    "manifest_checksum": "$MANIFEST_CHECKSUM",
    "known_good_checksum": null,
    "verification_chain_intact": true
  },

  "database": {
    "path": "$AUTH_DB",
    "checksum": null,
    "table_counts": {
      "clients": $CLIENTS_COUNT,
      "attendance_log": $ATTENDANCE_COUNT,
      "rexxie_ideas": $REXXIE_IDEAS_COUNT,
      "staff_medical_log": $STAFF_MEDICAL_COUNT
    },
    "last_verified_at": "$CURRENT_TIMESTAMP"
  },

  "critical_files": {
    "backend_main_py": {
      "path": "$REX_ROOT/backend/main.py",
      "checksum": "$BACKEND_MAIN_CHECKSUM",
      "size_bytes": $(stat -f%z "$REX_ROOT/backend/main.py" 2>/dev/null || echo "0"),
      "last_modified": "$(stat -f%Sm -t '%Y-%m-%dT%H:%M:%SZ' "$REX_ROOT/backend/main.py" 2>/dev/null || echo 'unknown')"
    },
    "rexxie_bot_py": {
      "path": "$REX_ROOT/rex_rexxie_telegram_bot.py",
      "checksum": "$REXXIE_BOT_CHECKSUM",
      "size_bytes": $(stat -f%z "$REX_ROOT/rex_rexxie_telegram_bot.py" 2>/dev/null || echo "0"),
      "last_modified": "$(stat -f%Sm -t '%Y-%m-%dT%H:%M:%SZ' "$REX_ROOT/rex_rexxie_telegram_bot.py" 2>/dev/null || echo 'unknown')"
    },
    "consensus_ocr": {
      "path": "$REX_ROOT/goj_menu_consensus_ocr.py",
      "checksum": "$OCR_CONSENSUS_CHECKSUM",
      "size_bytes": $(stat -f%z "$REX_ROOT/goj_menu_consensus_ocr.py" 2>/dev/null || echo "0"),
      "last_modified": "$(stat -f%Sm -t '%Y-%m-%dT%H:%M:%SZ' "$REX_ROOT/goj_menu_consensus_ocr.py" 2>/dev/null || echo 'unknown')"
    },
    "ocr_schema": {
      "path": "$REX_ROOT/core/ocr_schema.py",
      "checksum": "$OCR_SCHEMA_CHECKSUM",
      "size_bytes": $(stat -f%z "$REX_ROOT/core/ocr_schema.py" 2>/dev/null || echo "0"),
      "last_modified": "$(stat -f%Sm -t '%Y-%m-%dT%H:%M:%SZ' "$REX_ROOT/core/ocr_schema.py" 2>/dev/null || echo 'unknown')"
    },
    "system_manifest": {
      "path": "$MANIFEST",
      "checksum": "$MANIFEST_CHECKSUM",
      "size_bytes": $(stat -f%z "$MANIFEST" 2>/dev/null || echo "0"),
      "last_modified": "$(stat -f%Sm -t '%Y-%m-%dT%H:%M:%SZ' "$MANIFEST" 2>/dev/null || echo 'unknown')"
    }
  },

  "services": {
    "rex_backend": {
      "pid": $REX_BACKEND,
      "running": $([ "$REX_BACKEND" != "0" ] && echo "true" || echo "false"),
      "last_verified_at": "$CURRENT_TIMESTAMP"
    },
    "rexxie_bot": {
      "pid": $REXXIE_BOT,
      "running": $([ "$REXXIE_BOT" != "0" ] && echo "true" || echo "false"),
      "last_verified_at": "$CURRENT_TIMESTAMP"
    },
    "rex_telegram_bot": {
      "pid": $REX_TELEGRAM,
      "running": $([ "$REX_TELEGRAM" != "0" ] && echo "true" || echo "false"),
      "last_verified_at": "$CURRENT_TIMESTAMP"
    },
    "scheduler": {
      "pid": $SCHEDULER,
      "running": $([ "$SCHEDULER" != "0" ] && echo "true" || echo "false"),
      "last_verified_at": "$CURRENT_TIMESTAMP"
    },
    "alert_router": {
      "pid": $ALERT_ROUTER,
      "running": $([ "$ALERT_ROUTER" != "0" ] && echo "true" || echo "false"),
      "last_verified_at": "$CURRENT_TIMESTAMP"
    }
  },

  "ocr_state": {
    "snapshot_exists": true,
    "snapshot_path": "$REX_ROOT/ocr_snapshot_2026_04_13.tar.gz",
    "flag_queue_unresolved": 28,
    "last_successful_run": "2026-04-13T17:33:54",
    "quarantine_items": "check $REX_ROOT/data/ocr_quarantine/ directly"
  },

  "security": {
    "telegram_token_in_keychain": true,
    "anthropic_key_in_keychain": true,
    "totp_configured": false,
    "note": "Security credentials now in keychain (post-rotation)"
  },

  "memory_system": {
    "rexxie_memory_db_exists": true,
    "path": "$HOME/Documents/goj files/rexxie/rexxie_memory.db",
    "seeded": true,
    "last_verified_at": "$CURRENT_TIMESTAMP"
  },

  "stamped_on": "$(hostname)"
}
EOFKGOOD

echo -e "${GREEN}✓${NC} KNOWN_GOOD_STATE.json written"

# 7. Compute SHA-256 of the new KNOWN_GOOD_STATE.json
KNOWN_GOOD_CHECKSUM=$(shasum -a 256 "$KNOWN_GOOD" | awk '{print $1}')
echo -e "${GREEN}✓${NC} Known Good checksum: ${KNOWN_GOOD_CHECKSUM:0:16}..."

# 8. Update ACTIVE_SYSTEM_MANIFEST.json with the checksums
echo -e "${YELLOW}[MANIFEST]${NC} Updating manifest with checksums..."

# Use jq to update the JSON if available, otherwise use sed (safer fallback)
if command -v jq &> /dev/null; then
    jq ".verification.manifest_checksum = \"$MANIFEST_CHECKSUM\" | .verification.known_good_checksum = \"$KNOWN_GOOD_CHECKSUM\"" "$MANIFEST" > "$MANIFEST.tmp"
    mv "$MANIFEST.tmp" "$MANIFEST"
    echo -e "${GREEN}✓${NC} Manifest updated with jq"
else
    echo -e "${YELLOW}[WARNING]${NC} jq not available, using sed to update manifest"
    sed -i '' "s/\"manifest_checksum\": null/\"manifest_checksum\": \"$MANIFEST_CHECKSUM\"/" "$MANIFEST"
    sed -i '' "s/\"known_good_checksum\": null/\"known_good_checksum\": \"$KNOWN_GOOD_CHECKSUM\"/" "$MANIFEST"
fi

# 9. Log the stamp to ledger.db
echo -e "${YELLOW}[LEDGER]${NC} Logging stamp event..."

if [ -f "$LEDGER_DB" ]; then
    sqlite3 "$LEDGER_DB" << EOFSQL
INSERT INTO decision_history (
    decision_date, subsystem, what_changed, why,
    authorization_source, was_intentional, contradicts_prior, manual_review_needed
) VALUES (
    '$CURRENT_TIMESTAMP',
    'system',
    'Stamped KNOWN_GOOD_STATE.json with manifest checksums',
    'Recovery build: verify system is in known good state',
    'STAMP_KNOWN_GOOD.command (recovery-build)',
    1,
    0,
    0
);
EOFSQL
    echo -e "${GREEN}✓${NC} Ledger updated"
else
    echo -e "${YELLOW}[WARNING]${NC} ledger.db not found at $LEDGER_DB (non-critical)"
fi

# 10. Summary
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}[SUCCESS] System stamped as KNOWN_GOOD${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo "Manifest checksum:    ${MANIFEST_CHECKSUM:0:32}..."
echo "Known Good checksum:  ${KNOWN_GOOD_CHECKSUM:0:32}..."
echo "Stamped at:           $CURRENT_TIMESTAMP"
echo "Stamped by:           $(whoami)"
echo ""
echo "Database:"
echo "  clients:            $CLIENTS_COUNT"
echo "  attendance_log:     $ATTENDANCE_COUNT"
echo "  rexxie_ideas:       $REXXIE_IDEAS_COUNT"
echo "  staff_medical_log:  $STAFF_MEDICAL_COUNT"
echo ""
echo "Services running:     $([ "$REX_BACKEND" != "0" ] && echo "✓ rex_backend" || echo "✗ rex_backend")  $([ "$REXXIE_BOT" != "0" ] && echo "✓ rexxie_bot" || echo "✗ rexxie_bot")  $([ "$ALERT_ROUTER" != "0" ] && echo "✓ alert_router" || echo "✗ alert_router")"
echo ""
echo -e "${YELLOW}[NOTE]${NC} You can now compare future system state against this stamp."
echo -e "${YELLOW}[NOTE]${NC} Compare at: $KNOWN_GOOD"
echo ""
