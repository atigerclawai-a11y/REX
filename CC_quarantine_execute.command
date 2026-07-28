#!/bin/bash
# CC_quarantine_execute.command
# Gold Health Systems — hermes-workspace quarantine
# APPROVED by Kato — June 4 2026
# PAE: Propose ✅ Approve ✅ Execute ✅

QDIR="$HOME/Desktop/REX/CC_hermes_desktop_quarantine_20260604"
LOG="$HOME/Desktop/REX/logs/cc_quarantine_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$QDIR" "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════════"
echo "  hermes-workspace QUARANTINE — $(date)"
echo "  Approved by Kato (do it)"
echo "  Destination: $QDIR"
echo "══════════════════════════════════════════════════════"
echo ""

# STEP A — Disable LaunchAgents first (prevents auto-restart)
echo "── A. Disabling LaunchAgents ─────────────────────────"
for plist in \
  "$HOME/Library/LaunchAgents/com.hermes.cloud-workspace.plist" \
  "$HOME/Library/LaunchAgents/com.hermes.workspace.plist"; do
  if [ -f "$plist" ]; then
    launchctl unload "$plist" 2>/dev/null && echo "  ✅ Unloaded: $(basename $plist)" \
      || echo "  ℹ️  Not loaded (already inactive): $(basename $plist)"
    mv "$plist" "$QDIR/" && echo "  ✅ Moved: $(basename $plist)" \
      || echo "  ⚠️  Move failed: $(basename $plist)"
  else
    echo "  — Not found: $(basename $plist)"
  fi
done
echo ""

# STEP B — Move hermes-workspace.app bundle
echo "── B. Moving hermes-workspace.app ───────────────────"
if [ -d "/Applications/hermes-workspace.app" ]; then
  mv "/Applications/hermes-workspace.app" "$QDIR/" \
    && echo "  ✅ Moved /Applications/hermes-workspace.app" \
    || echo "  ⚠️  Move failed — may need sudo. Skipping."
else
  echo "  — /Applications/hermes-workspace.app not found"
fi
# Leave Hermes.app and HermesCloud.app for now (separate investigation needed)
echo "  ℹ️  /Applications/Hermes.app — LEFT IN PLACE (needs investigation)"
echo "  ℹ️  /Applications/HermesCloud.app — LEFT IN PLACE (needs investigation)"
echo ""

# STEP C — Move Application Support data
echo "── C. Moving Application Support/hermes-workspace ───"
if [ -d "$HOME/Library/Application Support/hermes-workspace" ]; then
  mv "$HOME/Library/Application Support/hermes-workspace" "$QDIR/AppSupport_hermes-workspace" \
    && echo "  ✅ Moved Application Support/hermes-workspace" \
    || echo "  ⚠️  Move failed"
else
  echo "  — Application Support/hermes-workspace not found"
fi
echo ""

# STEP D — Move ~/hermes-workspace/ home dir
echo "── D. Moving ~/hermes-workspace/ ────────────────────"
if [ -d "$HOME/hermes-workspace" ]; then
  mv "$HOME/hermes-workspace" "$QDIR/hermes-workspace-home" \
    && echo "  ✅ Moved ~/hermes-workspace to quarantine" \
    || echo "  ⚠️  Move failed"
else
  echo "  — ~/hermes-workspace not found"
fi
echo ""

# STEP E — Leave crash report in place (evidence)
echo "── E. Crash report ───────────────────────────────────"
CRASH_PLIST=$(find "$HOME/Library/Application Support/CrashReporter" -name "*hermes-workspace*" 2>/dev/null | head -1)
if [ -n "$CRASH_PLIST" ]; then
  echo "  ℹ️  Crash report LEFT IN PLACE (evidence):"
  echo "     $CRASH_PLIST"
else
  echo "  — No crash report found"
fi
echo ""

# STEP F — Write quarantine manifest
echo "── F. Quarantine manifest ────────────────────────────"
cat > "$QDIR/QUARANTINE_MANIFEST.txt" << MANIFEST
hermes-workspace QUARANTINE MANIFEST
Gold Health Systems — $(date)
Approved by: Kato (Chairman)
Reason: hermes-workspace modified ~/.hermes/config.yaml at ~12:47 PM June 4, 2026

Files quarantined:
$(ls -la "$QDIR" 2>/dev/null)

Restoration:
  To restore hermes-workspace: move files back from this directory.
  To re-enable LaunchAgents: move .plist files back to ~/Library/LaunchAgents/
    then: launchctl load ~/Library/LaunchAgents/com.hermes.cloud-workspace.plist

IMPORTANT: Do NOT permanently delete any of these files without Kato approval.
MANIFEST
echo "  ✅ QUARANTINE_MANIFEST.txt written"
echo ""

echo "══════════════════════════════════════════════════════"
echo "  QUARANTINE COMPLETE — $(date)"
echo "  All items moved to: $QDIR"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
read -p "Press Enter to close..."
