#!/bin/bash
# CC_set_memory_pin.command
# One-time setup: store Hermes memory protection PIN in macOS Keychain
# PIN will be required to install or edit SOUL.md and MEMORY.md

echo "══════════════════════════════════════════════════════"
echo "  CC_set_memory_pin — Hermes Memory PIN Setup"
echo "  $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# Check if PIN already exists
EXISTING=$(security find-generic-password -a mainsobhelper -s hermes-memory-pin -w 2>/dev/null)
if [ -n "$EXISTING" ]; then
  echo "  ⚠️  A PIN is already set in Keychain (hermes-memory-pin)."
  read -p "  Overwrite it? [y/N]: " CONFIRM
  if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "  Cancelled."
    read -p "Press any key to close..."
    exit 0
  fi
fi

echo ""
read -s -p "  New PIN: " PIN1
echo ""
read -s -p "  Confirm PIN: " PIN2
echo ""

if [ -z "$PIN1" ]; then
  echo "  ❌ PIN cannot be empty."
  read -p "Press any key to close..."
  exit 1
fi

if [ "$PIN1" != "$PIN2" ]; then
  echo "  ❌ PINs do not match. Aborting."
  read -p "Press any key to close..."
  exit 1
fi

# Store in Keychain (-U = update if exists)
security add-generic-password -U -a mainsobhelper -s hermes-memory-pin -w "$PIN1"
if [ $? -eq 0 ]; then
  echo "  ✅ PIN stored in Keychain as 'hermes-memory-pin'"
  echo ""
  echo "  Now run CC_lock_memories.command to protect the files."
else
  echo "  ❌ Failed to store PIN in Keychain."
fi

echo ""
echo "══════════════════════════════════════════════════════"
read -p "Press any key to close..."
