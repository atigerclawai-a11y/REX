#!/bin/bash
# CC_create_obsidian_log.command
# Creates ~/Desktop/Gold_Health_Systems/BRAIN/Agent_Activity_Log.md
# Sets up the per-agent, timestamped, one-sentence task log Kato requested.

BRAIN="$HOME/Desktop/Gold_Health_Systems/BRAIN"
LOG_FILE="$BRAIN/Agent_Activity_Log.md"
APPEND_SCRIPT="$HOME/Desktop/REX/CC_agent_log_append.sh"

echo "Creating Obsidian Agent Activity Log..."

mkdir -p "$BRAIN"

# Create the main log file (only if it doesn't exist)
if [ ! -f "$LOG_FILE" ]; then
cat > "$LOG_FILE" << 'EOF'
# Agent Activity Log
*Gold Health Systems · Auto-maintained by all agents*
*Format: `- [YYYY-MM-DD HH:MM] **Agent** — One-sentence description of completed task.`*
*Kato can ask any agent: "what happened at [time]?" or "what did Hermie do today?" and get a full account.*

---

EOF
echo "Created new log file: $LOG_FILE"
else
echo "Log file already exists — appending to it."
fi

# Append today's completed tasks (June 4 2026)
cat >> "$LOG_FILE" << 'EOF'
## 2026-06-04

- [2026-06-04 13:22] **Hermes (Claude)** — Created CC_fix_dock_permanent.command and installed com.ghs.dock-fix.plist LaunchAgent to keep the Dock permanently visible.
- [2026-06-04 13:22] **Hermes (Claude)** — Fixed keychain unlock issue by running CC_fix_keychain.command, resolving Chrome auth prompts.
- [2026-06-04 13:48] **Hermes (Claude)** — Ran full GHS system audit (CC_audit_runner.command): checked Tailscale (✅ connected), Ollama (✅ 7 models including gemma4:26b), AutoResearch (⚠️ in ~/Documents not ~/Desktop), Nous skills (✅ 40+ skills), Obsidian vaults (✅ 4 found), service health (REX ✅, Hermes GW ✅, :8080 ⚠️ 404 on /health).
- [2026-06-04 13:54] **Hermes (Claude)** — Created full June 4 backup snapshot (CC_june4_backup_20260604_174528) including all hermes profiles/cloud config, 7 config.yaml bak files, state-snapshot 20260604-023854-pre-update, and all 8 LaunchAgent plists.
- [2026-06-04 13:54] **Hermes (Claude)** — Wrote CC_audit_report_june4.md and CC_quarantine_proposal.txt identifying hermes-workspace as the config.yaml incident culprit with 7-item quarantine footprint.
- [2026-06-04 14:00] **Hermes (Claude)** — Executed approved quarantine of hermes-workspace: unloaded com.hermes.cloud-workspace.plist and com.hermes.workspace.plist LaunchAgents, moved hermes-workspace.app, AppSupport dir, and ~/hermes-workspace/ home dir to CC_hermes_desktop_quarantine_20260604/.
- [2026-06-04 14:05] **Hermes (Claude)** — Ran config.yaml diff (pre-incident vs current), inventoried ~/Documents/autoresearch, copied GOJ working doc and datarex app.py to REX for editing, and performed full service diagnostic.

EOF

echo "✅ June 4 entries written"
echo ""
echo "Log file: $LOG_FILE"
echo "$(wc -l < "$LOG_FILE") lines total"

# Create the reusable append helper script (for any agent to use going forward)
cat > "$APPEND_SCRIPT" << 'SCRIPT'
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
SCRIPT
chmod +x "$APPEND_SCRIPT"
echo "✅ CC_agent_log_append.sh created (reusable by any agent)"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  Obsidian Agent Log setup complete — $(date)"
echo "  File: $LOG_FILE"
echo "  Append helper: $APPEND_SCRIPT"
echo "══════════════════════════════════════════════════════"
read -p "Press Enter to close..."
