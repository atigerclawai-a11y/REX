#!/usr/bin/env bash
# CC_read_hermes_memory.command — read current Hermes cloud memory entries
LOG="$HOME/Desktop/REX/logs/cc_read_hermes_memory.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

MEMORIES="$HOME/.hermes/profiles/cloud/memories"
TOOL="$HOME/.hermes/hermes-agent/tools/memory_tool.py"

echo "══════════════════════════════════"
echo "  Hermes Cloud Memory — Contents"
echo "══════════════════════════════════"
echo ""

echo "── Memory directory listing ──"
ls -la "$MEMORIES/" 2>/dev/null || echo "Directory not found or empty: $MEMORIES"

echo ""
echo "── All memory files (full content) ──"
if [ -d "$MEMORIES" ]; then
  for f in "$MEMORIES"/*; do
    if [ -f "$f" ]; then
      echo ""
      echo "=== $(basename "$f") ==="
      cat "$f"
      echo ""
    fi
  done
  echo "Total files: $(ls "$MEMORIES" 2>/dev/null | wc -l | tr -d ' ')"
else
  echo "No memories directory found."
fi

echo ""
echo "── memory_tool.py key sections ──"
python3 - "$TOOL" <<'EOF'
import sys
try:
    src = open(sys.argv[1]).read()
    # Show class definition, key methods and constants
    lines = src.split('\n')
    in_section = False
    for i, line in enumerate(lines):
        if any(kw in line for kw in ['LIMIT', 'limit', 'char_limit', 'class Memory', 'def ', 'storage_path', 'memories_dir', 'memory_dir', 'base_dir']):
            print(f"L{i+1}: {line}")
except Exception as e:
    print(f"Error reading memory_tool: {e}")
EOF

echo ""
echo "── memory_tool.py — storage path logic ──"
grep -n "path\|dir\|file\|storage\|load\|save\|write\|read" "$TOOL" 2>/dev/null | head -40

echo ""
echo "Done."
sleep 8
