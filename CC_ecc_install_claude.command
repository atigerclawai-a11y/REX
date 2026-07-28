#!/bin/bash
# CC_ecc_install_claude.command
# Deploy ECC skills/rules to ~/.claude/ using --target claude --profile full
# Companion to CC_install_ecc.command (which cloned the repo and verified tests)

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_ecc_install_claude_${TIMESTAMP}.log
ECC_DIR=~/Desktop/REX/ecc

exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_ecc_install_claude — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# Verify ECC repo exists
if [ ! -d "$ECC_DIR" ]; then
  echo "[ERROR] ECC dir not found at $ECC_DIR"
  echo "Run CC_install_ecc.command first."
  read -p "Press any key to close..."
  exit 1
fi

echo "── ECC dir: $ECC_DIR ────────────────────────────────"
echo "── Branch: $(git -C "$ECC_DIR" branch --show-current 2>/dev/null || echo 'unknown')"
echo ""

# Run install targeting ~/.claude/ with full profile
echo "── Installing to ~/.claude/ (--target claude --profile full) ──"
cd "$ECC_DIR" || exit 1
bash install.sh --target claude --profile full

INSTALL_EXIT=$?

echo ""
echo "── Install exit code: $INSTALL_EXIT ────────────────"

if [ $INSTALL_EXIT -eq 0 ]; then
  echo "[OK] ECC install completed successfully"
else
  echo "[WARN] install.sh exited with code $INSTALL_EXIT — check output above"
fi

# Check what landed in ~/.claude/
echo ""
echo "── ~/.claude/ contents after install ───────────────"
ls -la ~/.claude/ 2>/dev/null || echo "(~/.claude not found)"

echo ""
echo "── ~/.claude/rules/ (ECC rules) ────────────────────"
ls ~/.claude/rules/ecc/ 2>/dev/null && echo "" || echo "(no ecc rules dir)"

echo ""
echo "── ~/.claude/skills/ (ECC skills) ──────────────────"
ls ~/.claude/skills/ 2>/dev/null | head -20 || echo "(no skills dir)"

echo ""
echo "── Summary ──────────────────────────────────────────"
echo "ECC dir:   $ECC_DIR"
echo "Target:    ~/.claude/"
echo "Profile:   full"
echo "Log:       $LOG"
echo ""
echo "══════════════════════════════════════════════════════"
echo "  ECC Claude install done — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
