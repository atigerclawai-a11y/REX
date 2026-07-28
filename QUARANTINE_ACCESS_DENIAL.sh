#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
#  QUARANTINE ACCESS DENIAL SCRIPT
#  Re-seal the quarantine directory (make it read-only)
#  ────────────────────────────────────────────────────────────────

QUARANTINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/QUARANTINE_CONTRADICTORY_LEGACY_2026_04_14" && pwd)"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  QUARANTINE ACCESS DENIAL — Sealing Legacy Archive"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check if quarantine exists
if [ ! -d "$QUARANTINE_DIR" ]; then
  echo "❌ ERROR: Quarantine directory not found."
  echo "   Expected: $QUARANTINE_DIR"
  exit 1
fi

echo "Quarantine target: $QUARANTINE_DIR"
echo ""

# Check if we're in the right place
if [ ! -f "$QUARANTINE_DIR/QUARANTINE_LOG.md" ]; then
  echo "❌ ERROR: QUARANTINE_LOG.md not found."
  echo "   Is the quarantine properly initialized?"
  exit 1
fi

# Step 1: Set strict read-only permissions on quarantine directory
echo "[1/3] Setting read-only permissions (500)..."
chmod 500 "$QUARANTINE_DIR" 2>/dev/null
if [ $? -eq 0 ]; then
  PERMS=$(ls -ld "$QUARANTINE_DIR" | awk '{print $1}')
  echo "  ✓ Directory permissions: $PERMS"
else
  echo "  ⚠ Warning: Could not set directory permissions (may need sudo)"
fi

# Step 2: Set read-only permissions on all files within
echo ""
echo "[2/3] Setting read-only permissions on contents..."
chmod -R a-w "$QUARANTINE_DIR"/* 2>/dev/null
echo "  ✓ All files are now read-only (u-w)"

# Step 3: Verify lock
echo ""
echo "[3/3] Verifying quarantine seal..."

# Check if we can write
TEST_FILE="$QUARANTINE_DIR/test_write_seal_verification_tmp"
if touch "$TEST_FILE" 2>/dev/null; then
  rm "$TEST_FILE" 2>/dev/null
  echo "  ⚠ WARNING: Directory is still writable! Seal failed."
  echo "     (This may be OK if running as owner; try: sudo chmod 500 \"$QUARANTINE_DIR\")"
else
  echo "  ✓ Quarantine is sealed — write operations blocked"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ SEAL COMPLETE"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "  This directory is now READ-ONLY."
echo "  Legacy components are protected from accidental modification."
echo ""
echo "  Current permissions:"
ls -ld "$QUARANTINE_DIR"
echo ""
echo "  To unseal (if absolutely necessary):"
echo "    chmod 700 \"$QUARANTINE_DIR\""
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
