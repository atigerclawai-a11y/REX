#!/bin/bash
# CC_switch_to_mistral.command
# Switch Hermie from qwen3:14b to mistral-small (128k context, no thinking mode)
# Also fixes MINIMUM_CONTEXT_LENGTH floor (was not patched due to underscore notation)
# Optimized for 24GB unified memory

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_switch_to_mistral_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

OLD_MODEL=qwen3:14b-hermie
NEW_BASE=mistral-small
NEW_MODEL=mistral-hermie
META=~/.hermes/hermes-agent/agent/model_metadata.py
HERMES_SRC=~/.hermes/hermes-agent
CFG=~/.hermes/profiles/default/config.yaml
PLIST=~/Library/LaunchAgents/ai.hermes.gateway.plist
KEY=$(grep "API_SERVER_KEY" ~/.hermes/.env | cut -d= -f2 | tr -d '[:space:]')

echo "══════════════════════════════════════════════════════"
echo "  CC_switch_to_mistral — $(date)"
echo "  Old model: $OLD_MODEL → New: $NEW_MODEL"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1: Pull mistral-small if not already cached ────────
echo "── 1: Pull mistral-small (128k context, ~14GB) ────────"
CACHED=$(ollama list 2>/dev/null | grep "^mistral-small" | head -1)
if [ -n "$CACHED" ]; then
  echo "  ✅ Already cached: $CACHED"
else
  echo "  Pulling $NEW_BASE — this may take 10–20 min on first download..."
  echo "  (progress below)"
  ollama pull "$NEW_BASE"
  if [ $? -ne 0 ]; then
    echo "  ❌ Pull failed. Check network and try: ollama pull $NEW_BASE"
    exit 1
  fi
  echo "  ✅ Pull complete"
fi
echo ""

# ── 2: Extract Hermie system prompt from old model ─────
echo "── 2: Extract Hermie system prompt from $OLD_MODEL ───"
MODELFILE_PATH=/tmp/Mistral_Hermie_Modelfile

OLD_MODELFILE=$(ollama show "$OLD_MODEL" --modelfile 2>/dev/null)
if [ -n "$OLD_MODELFILE" ]; then
  # Extract SYSTEM block
  SYSTEM_PROMPT=$(echo "$OLD_MODELFILE" | awk '/^SYSTEM """/,/^"""/' | sed '1d;$d')
  if [ -z "$SYSTEM_PROMPT" ]; then
    # Try single-line SYSTEM
    SYSTEM_PROMPT=$(echo "$OLD_MODELFILE" | grep "^SYSTEM " | sed 's/^SYSTEM //')
  fi
  echo "  System prompt preview (first 150 chars):"
  echo "  ${SYSTEM_PROMPT:0:150}..."
  echo ""
  HAS_SYSTEM=true
else
  echo "  ⚠️  Could not read old model — using default Hermie prompt"
  HAS_SYSTEM=false
fi
echo ""

# ── 3: Build new Modelfile ─────────────────────────────
echo "── 3: Build Modelfile for $NEW_MODEL ─────────────────"
cat > "$MODELFILE_PATH" << 'MODELFILE_HEADER'
FROM mistral-small

PARAMETER num_ctx 65536
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1

MODELFILE_HEADER

if [ "$HAS_SYSTEM" = true ] && [ -n "$SYSTEM_PROMPT" ]; then
  echo 'SYSTEM """' >> "$MODELFILE_PATH"
  echo "$SYSTEM_PROMPT" >> "$MODELFILE_PATH"
  echo '"""' >> "$MODELFILE_PATH"
else
  cat >> "$MODELFILE_PATH" << 'DEFAULT_SYSTEM'
SYSTEM """You are Hermie, a local AI assistant integrated with the Hermes gateway. You are helpful, direct, and concise. You have access to tools and can help with tasks, questions, and operations. Always be clear and to the point."""
DEFAULT_SYSTEM
fi

echo "  Modelfile written to $MODELFILE_PATH"
echo "  PARAMETER lines:"
grep "PARAMETER\|FROM" "$MODELFILE_PATH"
echo ""

# ── 4: Create mistral-hermie model ─────────────────────
echo "── 4: Create model $NEW_MODEL ─────────────────────────"
ollama create "$NEW_MODEL" -f "$MODELFILE_PATH"
if [ $? -eq 0 ]; then
  echo "  ✅ Model $NEW_MODEL created"
else
  echo "  ❌ Model creation failed"
  exit 1
fi

# Verify
echo "  Verifying:"
ollama show "$NEW_MODEL" | grep -E "context|num_ctx|parameter|architecture" | head -5
echo ""

# ── 5: Fix MINIMUM_CONTEXT_LENGTH (underscore-aware) ──
echo "── 5: Patch MINIMUM_CONTEXT_LENGTH → 8000 ─────────────"
if [ ! -f "$META" ]; then
  echo "  ❌ model_metadata.py not found at $META"
else
  CURRENT=$(grep "MINIMUM_CONTEXT_LENGTH\s*=" "$META" | head -1)
  echo "  Current: $CURRENT"
  cp "$META" "${META}.bak_mistral_${TIMESTAMP}"

  # Handle both underscore and plain notation
  perl -pi -e 's/MINIMUM_CONTEXT_LENGTH\s*=\s*64_000/MINIMUM_CONTEXT_LENGTH = 8000/g' "$META"
  perl -pi -e 's/MINIMUM_CONTEXT_LENGTH\s*=\s*64000/MINIMUM_CONTEXT_LENGTH = 8000/g' "$META"

  AFTER=$(grep "MINIMUM_CONTEXT_LENGTH\s*=" "$META" | head -1)
  echo "  After:   $AFTER"
  if echo "$AFTER" | grep -q "8000"; then
    echo "  ✅ Floor patched to 8000"
  else
    echo "  ❌ Patch failed — check file manually at $META"
  fi
fi
echo ""

# ── 6: Clear Python bytecode cache ─────────────────────
echo "── 6: Clear __pycache__ ────────────────────────────────"
find "$HERMES_SRC" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "  ✅ Bytecode cache cleared"
echo ""

# ── 7: Update Hermes config.yaml ───────────────────────
echo "── 7: Update Hermes config to use $NEW_MODEL ──────────"
if [ ! -f "$CFG" ]; then
  echo "  ❌ Config not found at $CFG"
else
  cp "$CFG" "${CFG}.bak_mistral_${TIMESTAMP}"
  echo "  Before:"
  grep "name:" "$CFG" | head -3

  # Update model name
  sed -i '' "s/name: qwen3:14b-hermie/name: $NEW_MODEL/" "$CFG"
  sed -i '' "s/name: qwen3:14b/name: $NEW_MODEL/" "$CFG"

  echo "  After:"
  grep "name:" "$CFG" | head -3

  # Verify context_length setting
  echo "  Context settings:"
  grep -E "context_length|ollama_num_ctx" "$CFG"
fi
echo ""

# ── 8: Restart Hermes gateway ──────────────────────────
echo "── 8: Restart Hermes gateway ──────────────────────────"
launchctl unload "$PLIST" 2>/dev/null || true
sleep 2
pkill -f "hermes_cli.main.*--profile default" 2>/dev/null || true
sleep 8
launchctl load "$PLIST"
echo "  Waiting 20s for gateway init..."
sleep 20
echo ""

# ── 9: Port check ──────────────────────────────────────
echo "── 9: Port check ───────────────────────────────────────"
LISTENER=$(lsof -i :65001 -P -n 2>/dev/null | grep LISTEN)
if [ -n "$LISTENER" ]; then
  echo "  ✅ Port 65001 listening"
else
  echo "  ❌ Port 65001 not listening"
  echo "  Gateway log (last 10 lines):"
  find ~/.hermes -name "gateway.log" 2>/dev/null | head -1 | xargs tail -10 2>/dev/null
  exit 1
fi
echo ""

# ── 10: Smoke test (90s) ───────────────────────────────
echo "── 10: Chat smoke test (90s) ──────────────────────────"
if [ -z "$KEY" ]; then
  echo "  ⚠️  No API key — skipping"
else
  START=$(date +%s)
  CHAT=$(curl -s -w "\nHTTP:%{http_code}" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$NEW_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Say just OK\"}],\"max_tokens\":5,\"stream\":false}" \
    --max-time 90 \
    http://127.0.0.1:65001/v1/chat/completions)
  END=$(date +%s)
  HTTP_CODE=$(echo "$CHAT" | grep "HTTP:" | cut -d: -f2)
  ELAPSED=$((END - START))

  if [ "$HTTP_CODE" = "200" ]; then
    REPLY=$(echo "$CHAT" | grep -v "HTTP:" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d['choices'][0]['message']['content'][:200])
except Exception as e:
    print('(parse error: ' + str(e) + ')')
" 2>/dev/null)
    echo "  ✅ HTTP 200 in ${ELAPSED}s"
    echo "  Hermie replied: \"$REPLY\""
    echo ""
    echo "  ✅✅✅ HERMIE IS LIVE on mistral-small — @HermieChatt_bot should be working"
  else
    echo "  ❌ HTTP $HTTP_CODE after ${ELAPSED}s"
    echo "  $(echo "$CHAT" | grep -v "HTTP:" | head -3)"
    echo ""
    echo "  Gateway log (last 20 lines):"
    find ~/.hermes -name "gateway.log" 2>/dev/null | head -1 | xargs tail -20 2>/dev/null
  fi
fi
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo "  New model: $NEW_MODEL (based on mistral-small, 128k ctx)"
echo "  Hermes floor: 8000 (was 64000)"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
