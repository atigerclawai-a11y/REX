#!/usr/bin/env bash
# CC_show_hermes_memory.command — dump all current Hermes cloud memory entries
LOG="$HOME/Desktop/REX/logs/cc_show_hermes_memory.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

HERMES_HOME="$HOME/.hermes/profiles/cloud"
AGENT_DIR="$HOME/.hermes/hermes-agent"

echo "══════════════════════════════════"
echo "  Hermes Memory Inspector"
echo "══════════════════════════════════"
echo ""

echo "── 1. memory section in config.yaml ──"
python3 - "$HERMES_HOME/config.yaml" <<'EOF'
import sys, yaml, json
cfg = yaml.safe_load(open(sys.argv[1])) or {}
mem = cfg.get("memory", {})
print("memory config:")
print(yaml.dump({"memory": mem}, default_flow_style=False))
EOF

echo ""
echo "── 2. Looking for memory storage files ──"
for path in \
  "$HERMES_HOME/memory.json" \
  "$HERMES_HOME/memory.jsonl" \
  "$HERMES_HOME/memory.md" \
  "$HERMES_HOME/memories.json" \
  "$HERMES_HOME/memories.md" \
  "$HERMES_HOME/memory" \
  "$HOME/.hermes-cloud/memory.json" \
  "$HOME/.hermes-cloud/memories.json" \
  "$HOME/.hermes/memory.json" \
  "$HOME/.hermes/memories.json"; do
  if [ -e "$path" ]; then
    echo "✅ FOUND: $path"
    wc -c "$path"
    echo "--- content ---"
    cat "$path" 2>/dev/null | head -80
    echo "--- end ---"
  fi
done

echo ""
echo "── 3. Find all memory-related files in .hermes ──"
find "$HOME/.hermes" -name "*memor*" -o -name "*memories*" 2>/dev/null | grep -v ".bak" | grep -v "__pycache__"
find "$HOME/.hermes-cloud" -name "*memor*" -o -name "*memories*" 2>/dev/null | grep -v ".bak" 2>/dev/null

echo ""
echo "── 4. Check hermes-agent Python source for memory tool ──"
find "$AGENT_DIR" -name "*.py" 2>/dev/null | xargs grep -l "class.*[Mm]emory\|def.*memory\|MEMORY_LIMIT\|6000\|memory_tool" 2>/dev/null | head -10

echo ""
echo "── 5. Check gateway log for last memory read ──"
grep "memory\|MEMORY" "$HERMES_HOME/logs/gateway.log" 2>/dev/null | grep -iv "rss\|MallocStack\|monitor" | tail -20

echo ""
echo "── 6. Check gateway.log for memory entries (last written) ──"
grep -i "current_entries\|memory.*entries\|wrote memory\|read memory\|memory.*tool" "$HERMES_HOME/logs/gateway.log" 2>/dev/null | tail -10

echo ""
echo "── 7. Session storage — check recent session for memory ──"
SESSION_DIR="$HERMES_HOME/sessions"
if [ -d "$SESSION_DIR" ]; then
  LATEST=$(ls -t "$SESSION_DIR"/*.json 2>/dev/null | head -3)
  for f in $LATEST; do
    echo "Session: $f"
    python3 -c "
import json, sys
try:
    d = json.load(open('$f'))
    mem = d.get('memory', d.get('memories', None))
    if mem:
        print('Memory entries found:')
        print(json.dumps(mem, indent=2)[:2000])
    else:
        print('No memory key found in session')
except: pass
" 2>/dev/null
  done
fi

echo ""
echo "Done."
sleep 8
