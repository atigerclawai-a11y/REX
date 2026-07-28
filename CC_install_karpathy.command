#!/bin/bash
# CC_install_karpathy.command
# Clone Karpathy's microgpt and autoresearch to ~/Desktop

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_install_karpathy_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  CC_install_karpathy — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

cd ~/Desktop

# ── microgpt ──────────────────────────────────────────────
echo "── microgpt ─────────────────────────────────────────"
if [ -d "microgpt" ]; then
  echo "  Already exists — pulling latest..."
  cd microgpt && git pull && cd ..
else
  git clone https://github.com/karpathy/microgpt.git
  [ $? -eq 0 ] && echo "  ✅ microgpt cloned" || echo "  ❌ microgpt clone failed"
fi
echo ""

# ── autoresearch ──────────────────────────────────────────
echo "── autoresearch ─────────────────────────────────────"
if [ -d "autoresearch" ]; then
  echo "  Already exists — pulling latest..."
  cd autoresearch && git pull && cd ..
else
  git clone https://github.com/karpathy/autoresearch.git
  [ $? -eq 0 ] && echo "  ✅ autoresearch cloned" || echo "  ❌ autoresearch clone failed"
fi
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  ~/Desktop/microgpt"
echo "  ~/Desktop/autoresearch"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
