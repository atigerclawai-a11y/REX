#!/usr/bin/env bash
# CC_dump_hermes_brain.command
# Dumps Hermes memory + config + all profiles to ~/Desktop/REX/
# so Claude (Cowork) can read it and fill in the BRAIN vault
LOG="$HOME/Desktop/REX/logs/cc_dump_hermes_brain.log"
OUT="$HOME/Desktop/REX/hermes_brain_dump.txt"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════"
echo "  Hermes Brain Dump"
echo "  $(date)"
echo "══════════════════════════════════════════════" > "$OUT"
echo "" >> "$OUT"

# ── All Hermes profiles ────────────────────────────────────────────────
echo "━━ PROFILES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$OUT"
ls -la "$HOME/.hermes/profiles/" 2>/dev/null >> "$OUT" || echo "  No profiles dir" >> "$OUT"
echo "" >> "$OUT"

# ── Cloud profile memory ───────────────────────────────────────────────
echo "━━ CLOUD MEMORY (~/.hermes/profiles/cloud/memories/MEMORY.md) ━━━" >> "$OUT"
MEM="$HOME/.hermes/profiles/cloud/memories/MEMORY.md"
if [ -f "$MEM" ]; then
  wc -c "$MEM" >> "$OUT"
  echo "" >> "$OUT"
  cat "$MEM" >> "$OUT"
else
  echo "  NOT FOUND" >> "$OUT"
fi
echo "" >> "$OUT"

# ── Cloud config ───────────────────────────────────────────────────────
echo "━━ CLOUD CONFIG ━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$OUT"
YAML="$HOME/.hermes/profiles/cloud/config.yaml"
if [ -f "$YAML" ]; then
  cat "$YAML" >> "$OUT"
else
  echo "  NOT FOUND" >> "$OUT"
fi
echo "" >> "$OUT"

# ── All other profiles (BBG, social, etc.) ────────────────────────────
echo "━━ ALL PROFILE DIRECTORIES ━━━━━━━━━━━━━━━━━" >> "$OUT"
for PROFILE_DIR in "$HOME/.hermes/profiles/"/*/; do
  PROFILE=$(basename "$PROFILE_DIR")
  echo "  Profile: $PROFILE" >> "$OUT"
  # List files
  ls "$PROFILE_DIR" 2>/dev/null | sed 's/^/    /' >> "$OUT"
  # Read memory if exists
  MEM_FILE="$PROFILE_DIR/memories/MEMORY.md"
  if [ -f "$MEM_FILE" ]; then
    echo "" >> "$OUT"
    echo "    --- MEMORY ($PROFILE) ---" >> "$OUT"
    wc -c "$MEM_FILE" >> "$OUT"
    cat "$MEM_FILE" >> "$OUT"
    echo "" >> "$OUT"
  fi
  # Read config if exists
  CFG_FILE="$PROFILE_DIR/config.yaml"
  if [ -f "$CFG_FILE" ]; then
    echo "" >> "$OUT"
    echo "    --- CONFIG ($PROFILE) ---" >> "$OUT"
    cat "$CFG_FILE" >> "$OUT"
    echo "" >> "$OUT"
  fi
  echo "" >> "$OUT"
done

# ── Search for BBG / social media / instagram files ───────────────────
echo "━━ BBG / SOCIAL MEDIA FILES ━━━━━━━━━━━━━━━━" >> "$OUT"
find "$HOME/.hermes" -type f \( -name "*bbg*" -o -name "*social*" -o -name "*instagram*" -o -name "*boardwalk*" \) 2>/dev/null >> "$OUT"
find "$HOME/Desktop/REX" -maxdepth 3 -type f \( -name "*bbg*" -o -name "*social*" -o -name "*instagram*" -o -name "*boardwalk*" \) 2>/dev/null >> "$OUT"
echo "" >> "$OUT"

# ── Search for Jarvis / screensaver ───────────────────────────────────
echo "━━ JARVIS / SCREENSAVER FILES ━━━━━━━━━━━━━━" >> "$OUT"
find "$HOME/.hermes" "$HOME/Desktop/REX" -maxdepth 5 -type f \( -name "*jarvis*" -o -name "*screensaver*" \) 2>/dev/null >> "$OUT"
echo "" >> "$OUT"

# ── ChatGPT / Grok export hints ───────────────────────────────────────
echo "━━ CHATGPT / GROK EXPORTS IN DOWNLOADS ━━━━━" >> "$OUT"
find "$HOME/Downloads" -maxdepth 2 -type f \( -name "*.json" -o -name "*.md" -o -name "*.txt" \) 2>/dev/null | head -30 >> "$OUT"
echo "" >> "$OUT"

# ── Hermes agent source (check for BBG agent code) ────────────────────
echo "━━ HERMES AGENT SOURCE FILES ━━━━━━━━━━━━━━━" >> "$OUT"
find "$HOME/.hermes/hermes-agent" -name "*.py" -o -name "*.yaml" -o -name "*.json" 2>/dev/null | grep -iv "__pycache__\|\.pyc" | head -40 >> "$OUT"
echo "" >> "$OUT"

echo "══════════════════════════════════════════════" >> "$OUT"
echo "  Dump complete: $OUT" >> "$OUT"
echo "══════════════════════════════════════════════" >> "$OUT"

echo ""
echo "✅ Done. Output: $OUT"
echo "   Claude can now read hermes_brain_dump.txt"
sleep 5
