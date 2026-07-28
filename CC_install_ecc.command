#!/bin/bash
# CC_install_ecc.command — Install ECC 2.0 into ~/.claude/
LOG_DIR="$HOME/Desktop/REX/logs"
LOG="$LOG_DIR/ecc_install.log"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Installing ECC 2.0 (--profile minimal, --target claude)  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

cd "$HOME/Desktop/ECC" || { echo "❌ ~/Desktop/ECC not found"; read -n 1 -p "Press any key..."; exit 1; }

./install.sh --profile minimal --target claude

echo ""
echo "✅ ECC install complete — log at ~/Desktop/REX/logs/ecc_install.log"
echo ""
read -n 1 -p "Press any key to close..."
