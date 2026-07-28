#!/bin/bash
# CC_approve_hermes_pairing.command — Auto-approve the current pending Hermes pairing code
# Double-click this from Finder. Works as long as the gateway is running.

exec > >(tee "$HOME/Desktop/REX/logs/CC_hermes_pair_$(date +%Y%m%d_%H%M%S).log") 2>&1
mkdir -p "$HOME/Desktop/REX/logs"
echo "=== Hermes Pairing Approval $(date) ==="
cd ~
source ~/.zshrc 2>/dev/null || export PATH="$HOME/.hermes/hermes-agent/venv/bin:$HOME/.local/bin:$PATH"

echo "Listing pending codes..."
PAIRING_OUTPUT=$(hermes pairing list 2>&1)
echo "$PAIRING_OUTPUT"

CODE=$(echo "$PAIRING_OUTPUT" | grep -oE '\b[A-Z0-9]{8}\b' | head -1)

if [ -z "$CODE" ]; then
    echo ""
    echo "No pending code found. Send any message to @Hermes_Cloud_May_bot first to generate one."
else
    echo "Approving code: $CODE"
    hermes pairing approve telegram "$CODE"
    echo "Done! Check Telegram for Hermes response."
fi

echo ""
echo "Press any key to close..."
read -n 1
