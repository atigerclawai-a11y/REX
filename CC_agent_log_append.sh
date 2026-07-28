#!/bin/bash
# CC_agent_log_append.sh
# Usage: ./CC_agent_log_append.sh "AgentName" "One sentence description of completed task."
# Example: ./CC_agent_log_append.sh "Hermie" "Processed 3 new menu scan PDFs via 4-engine OCR pipeline with 97% confidence."

AGENT="${1:-Unknown}"
TASK="${2:-Task description missing}"
LOG_FILE="$HOME/Desktop/Gold_Health_Systems/BRAIN/Agent_Activity_Log.md"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")

echo "- [$TIMESTAMP] **$AGENT** — $TASK" >> "$LOG_FILE"
echo "✅ Logged: [$TIMESTAMP] $AGENT — $TASK"
