#!/bin/bash
CONFIG="$HOME/.cloudflared/hermestigerclaw.yml"
cp "$CONFIG" "${CONFIG}.backup_$(date +%Y%m%d_%H%M%S)"
echo "Backed up to ${CONFIG}.backup_..."
echo "Edit $CONFIG and add the ingress rules shown above."
echo "Then: launchctl unload + load the cloudflared plist"
