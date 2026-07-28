#!/bin/bash
# CC_unlock_memories.command
# Verify PIN against Keychain, then unlock SOUL.md and MEMORY.md for editing
# Run CC_lock_memories.command when done editing

SOUL=~/.hermes/profiles/cloud/memories/SOUL.md
MEMORY=~/.hermes/profiles/cloud/memories/MEMORY.md

echo "══════════════════════════════════════════════════════"
echo "  CC_unlock_memories — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# Retrieve stored PIN
STORED=$(security find-generic-password -a mainsobhelper -s hermes-memory-pin -w 2>/dev/null)
if [ -z "$STORED" ]; then
  echo "  ❌ No PIN found in Keychain."
  echo "  Run CC_set_memory_pin.command to configure one."
  read -p "Press any key to close..."
  exit 1
fi

# Prompt for PIN
read -s -p "  Enter Hermes memory PIN: " INPUT_PIN
echo ""

if [ "$INPUT_PIN" != "$STORED" ]; then
  echo "  ❌ Incorrect PIN."
  read -p "Press any key to close..."
  exit 1
fi

echo "  ✅ PIN verified."
echo ""

# Unlock files
UNLOCKED=0
for FILE in "$SOUL" "$MEMORY"; do
  if [ -f "$FILE" ]; then
    chflags nouchg "$FILE"
    echo "  🔓 Unlocked: $FILE"
    UNLOCKED=$((UNLOCKED + 1))
  else
    echo "  ⚠️  Not found: $FILE (skipped)"
  fi
done

echo ""
if [ $UNLOCKED -gt 0 ]; then
  echo "  ✅ $UNLOCKED file(s) unlocked and editable."
  echo "  ⚠️  Run CC_lock_memories.command when you are done."
else
  echo "  ⚠️  No files found to unlock."
fi

echo ""
echo "══════════════════════════════════════════════════════"
read -p "Press any key to close..."
