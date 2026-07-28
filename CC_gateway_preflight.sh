#!/bin/bash
# CC_gateway_preflight.sh — Kill stale MCP processes before gateway starts
# Prevents MCP duplication on gateway restart.
# Invoked by launchd ai.hermes.gateway-cloud.plist.
#
# SAFETY: Only kills processes from ~/.hermes-cloud/mcp-servers/.
# Does NOT touch the gateway, other Hermes profiles, or user processes.

set -e

MCP_DIR="$HOME/.hermes-cloud/mcp-servers"
LOG="$HOME/.hermes/profiles/cloud/logs/gateway_preflight.log"

echo "=== Preflight $(date) ===" >> "$LOG"

# 1. Kill Python MCP servers (identified by mcp-servers/ in command line)
KILLED=0
for pid in $(ps aux | grep "mcp-servers/" | grep -v grep | awk '{print $2}'); do
    kill -9 "$pid" 2>/dev/null && KILLED=$((KILLED + 1))
done
echo "Killed $KILLED Python MCP processes" >> "$LOG"

# 2. Kill Node-based MCP servers
NODE_KILLED=0
for pid in $(pgrep -f "mcp-server-" 2>/dev/null); do
    kill -9 "$pid" 2>/dev/null && NODE_KILLED=$((NODE_KILLED + 1))
done
echo "Killed $NODE_KILLED Node MCP processes" >> "$LOG"

# 3. Kill n8n MCP
N8N_KILLED=0
for pid in $(pgrep -f "n8n-mcp" 2>/dev/null); do
    kill -9 "$pid" 2>/dev/null && N8N_KILLED=$((N8N_KILLED + 1))
done
echo "Killed $N8N_KILLED n8n MCP processes" >> "$LOG"

TOTAL=$((KILLED + NODE_KILLED + N8N_KILLED))
echo "Total cleaned: $TOTAL" >> "$LOG"

# Brief pause for OS to reap
sleep 2

# Verify cleanup
REMAINING=$(ps aux | grep "mcp-servers/" | grep -v grep | wc -l | tr -d ' ')
echo "Remaining MCP processes after cleanup: $REMAINING" >> "$LOG"

# 4. Start the gateway (exec replaces this shell so launchd tracks the right PID)
exec /Users/mainsobhelper/.hermes/hermes-agent/venv/bin/python \
    -m hermes_cli.main \
    --profile cloud \
    gateway run \
    --replace
