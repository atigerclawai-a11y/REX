#!/bin/bash
# CC_lock_memories.command
# Lock SOUL.md and MEMORY.md with macOS immutable flag (chflags uchg)
# Requires PIN to have been set via CC_set_memory_pin.command first

SOUL=~/.hermes/profiles/cloud/memories/SOUL.md
MEMORY=~/.hermes/profiles/cloud/memories/MEMORY.md

echo "══════════════════════════════════════════════════════"
echo "  CC_lock_memories — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# Verify PIN is configured
STORED=$(security find-generic-password -a mainsobhelper -s hermes-memory-pin -w 2>/dev/null)
if [ -z "$STORED" ]; then
  echo "  ❌ No PIN found in Keychain."
  echo "  Run CC_set_memory_pin.command first."
  read -p "Press any key to close..."
  exit 1
fi

# Lock files
LOCKED=0
for FILE in "$SOUL" "$MEMORY"; do
  if [ -f "$FILE" ]; then
    chflags uchg "$FILE"
    echo "  🔒 Locked: $FILE"
    LOCKED=$((LOCKED + 1))
  else
    echo "  ⚠️  Not found: $FILE (skipped)"
  fi
done

echo ""
if [ $LOCKED -gt 0 ]; then
  echo "  ✅ $LOCKED file(s) locked. PIN required to modify."
else
  echo "  ⚠️  No files were locked (files may not exist yet)."
fi

echo ""
echo "══════════════════════════════════════════════════════"
read -p "Press any key to close..."
