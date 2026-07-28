#!/bin/bash
# CC_apply_mcp_trim.command
# Trims Claude Desktop MCPs from 17 → 8, removes openrouter (rules violation)
# PAE — Execute step. Run only after Kato approves CC_claude_desktop_config_PROPOSED.json
exec > >(tee "$HOME/Desktop/REX/logs/mcp_trim_$(date +%Y%m%d_%H%M%S).log") 2>&1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
pass(){ echo -e "${GREEN}✅  $1${NC}"; }
fail(){ echo -e "${RED}❌  $1${NC}"; exit 1; }
info(){ echo -e "${CYAN}ℹ️   $1${NC}"; }

CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
PROPOSED="$HOME/Desktop/REX/CC_claude_desktop_config_PROPOSED.json"
BACKUP="$HOME/Desktop/REX/CC_backups/claude_desktop_config.json.bak_$(date +%Y%m%d_%H%M%S)"

echo -e "${BOLD}=== MCP TRIM — 17 → 8 ===${NC}"
echo ""

# Verify proposed file exists
if [ ! -f "$PROPOSED" ]; then
    fail "Proposed config not found at $PROPOSED"
fi

# Back up current config
mkdir -p "$HOME/Desktop/REX/CC_backups"
if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$BACKUP"
    pass "Backed up current config → $(basename $BACKUP)"
else
    info "No existing config found at expected path — will create fresh"
fi

# Apply proposed config
cp "$PROPOSED" "$CONFIG"
pass "Applied trimmed config (8 MCPs)"

# Count MCPs in new config
MCP_COUNT=$(python3 -c "import json; d=json.load(open('$CONFIG')); print(len(d.get('mcpServers',{})))" 2>/dev/null)
info "MCP servers in new config: $MCP_COUNT"

echo ""
echo -e "${BOLD}MCPs removed:${NC}"
echo "  ❌ openrouter (RULES VIOLATION — banned by CLAUDE.md)"
echo "  ❌ comfyui"
echo "  ❌ retell"
echo "  ❌ elevenlabs"
echo "  ❌ twilio"
echo "  ❌ perplexity"
echo "  ❌ groq"
echo "  ❌ mistral"
echo "  ❌ openai"
echo ""
echo -e "${BOLD}MCPs kept:${NC}"
echo "  ✅ hermes · telegram · n8n · instagram · antigravity · claude · grok · tavily"
echo ""
echo -e "${CYAN}Restart Claude Desktop to apply changes.${NC}"
echo ""
read -p "Press Enter to close..."
