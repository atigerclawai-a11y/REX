#!/bin/bash
# CC_wire_ecc_claude.command
# Install ECC v2.0 developer profile into ~/.claude/ ONLY
# Hermes is NOT touched. Memory files are NOT touched.

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_wire_ecc_claude_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

ECC_DIR=~/Desktop/REX/ecc
CLAUDE_DIR=~/.claude

echo "══════════════════════════════════════════════════════"
echo "  CC_wire_ecc_claude — $(date)"
echo "  Scope: ~/.claude/ only. Hermes untouched."
echo "══════════════════════════════════════════════════════"
echo ""

# ── 0: Verify ECC ─────────────────────────────────────────
echo "── 0: Verify ECC source ─────────────────────────────"
[ -f "$ECC_DIR/scripts/ecc.js" ] || { echo "  ❌ ECC not found at $ECC_DIR"; read -p "Press any key..."; exit 1; }
ECC_VERSION=$(node -e "const p=require('$ECC_DIR/package.json'); console.log(p.version)" 2>/dev/null || echo "unknown")
echo "  ✅ ECC v$ECC_VERSION at $ECC_DIR"
echo ""

# ── 1: Backup existing ECC files in ~/.claude ─────────────
echo "── 1: Backup ────────────────────────────────────────"
[ -d "$CLAUDE_DIR/rules/ecc" ] && cp -r "$CLAUDE_DIR/rules/ecc" "$CLAUDE_DIR/rules/ecc.bak_${TIMESTAMP}" && echo "  Backed up: rules/ecc.bak_${TIMESTAMP}" || echo "  (no existing rules/ecc)"
echo ""

# ── 2: Install ECC developer profile → ~/.claude ──────────
echo "── 2: Install ECC developer profile ────────────────"
node "$ECC_DIR/scripts/ecc.js" install --profile developer --target claude 2>&1
RC=$?
echo ""
if [ $RC -eq 0 ]; then
  echo "  ✅ ECC installed into ~/.claude/"
else
  echo "  ❌ Install failed (exit $RC)"
  read -p "Press any key to close..."; exit 1
fi
echo ""

# ── 3: Verify ─────────────────────────────────────────────
echo "── 3: Verify ────────────────────────────────────────"
echo "  Rules installed:"
ls "$CLAUDE_DIR/rules/ecc/" 2>/dev/null | head -10 | sed 's/^/    /'
echo ""
echo "  Files total in ~/.claude/rules/ecc:"
find "$CLAUDE_DIR/rules/ecc" -type f 2>/dev/null | wc -l | sed 's/^/    /'
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  ECC v$ECC_VERSION installed into ~/.claude/"
echo "  Hermes: UNTOUCHED ✅"
echo "  SOUL.md + MEMORY.md: UNTOUCHED ✅"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
