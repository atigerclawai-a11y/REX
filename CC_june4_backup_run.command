#!/bin/bash
# CC_june4_backup_run.command
# Gold Health Systems — June 4 2026 Backup
# Backs up Mac-side config & state into the backup folder already created.

BACKUP_DIR="$HOME/Desktop/REX/CC_june4_backup_20260604_174528"
LOG="$HOME/Desktop/REX/logs/cc_june4_backup_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  GHS JUNE 4 BACKUP — $(date)"
echo "  Target: $BACKUP_DIR"
echo "══════════════════════════════════════════════════"

# 1. ~/.hermes/profiles/cloud/ — SKIP memories/ (PIN-locked)
echo ""
echo "── 1. hermes profiles/cloud (skip memories/) ────"
mkdir -p "$BACKUP_DIR/hermes_profiles_cloud"
rsync -a --exclude='memories/' ~/.hermes/profiles/cloud/ "$BACKUP_DIR/hermes_profiles_cloud/" \
  && echo "  ✅ Done" || echo "  ⚠️  rsync had errors (check permissions)"

# 2. ~/.hermes/state-snapshots/
echo ""
echo "── 2. hermes state-snapshots ────────────────────"
if [ -d ~/.hermes/state-snapshots/ ]; then
  mkdir -p "$BACKUP_DIR/hermes_state-snapshots"
  cp -r ~/.hermes/state-snapshots/ "$BACKUP_DIR/hermes_state-snapshots/" \
    && echo "  ✅ Done" || echo "  ⚠️  errors"
else
  echo "  No state-snapshots dir (skipped)"
fi

# 3. ~/.hermes/config.yaml + all bak files
echo ""
echo "── 3. hermes root config.yaml + bak files ───────"
mkdir -p "$BACKUP_DIR/hermes_root_config"
cp ~/.hermes/config.yaml "$BACKUP_DIR/hermes_root_config/" 2>/dev/null && echo "  ✅ config.yaml"
for f in ~/.hermes/config.yaml.bak.*; do
  [ -f "$f" ] && cp "$f" "$BACKUP_DIR/hermes_root_config/" && echo "  ✅ $(basename $f)"
done

# 4. LaunchAgent plists
echo ""
echo "── 4. LaunchAgent plists ────────────────────────"
mkdir -p "$BACKUP_DIR/launchagents"
for plist in \
  ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist \
  ~/Library/LaunchAgents/ai.hermes.gateway.plist \
  ~/Library/LaunchAgents/com.ghs.dock-fix.plist \
  ~/Library/LaunchAgents/com.rex.backend.plist \
  ~/Library/LaunchAgents/com.goj.datarex.plist \
  ~/Library/LaunchAgents/com.tigerclaw.api.plist \
  ~/Library/LaunchAgents/com.goj.n8n.plist \
  ~/Library/LaunchAgents/com.hermes.claus-watchman.plist; do
  if [ -f "$plist" ]; then
    cp "$plist" "$BACKUP_DIR/launchagents/" && echo "  ✅ $(basename $plist)"
  else
    echo "  — $(basename $plist) not found"
  fi
done

# 5. Write manifest
echo ""
echo "── 5. Writing manifest ──────────────────────────"
cat > "$BACKUP_DIR/MANIFEST.txt" << MANIFEST
Gold Health Systems — June 4 2026 Backup Manifest
Generated: $(date)
Reason: Hermes desktop app (hermes-workspace) modified ~/.hermes/config.yaml at ~12:47 PM today.
        This backup preserves all work done before and after that incident.

Contents:
  hermes_profiles_cloud/     ← ~/.hermes/profiles/cloud/ (memories/ skipped — PIN-locked)
  hermes_state-snapshots/    ← ~/.hermes/state-snapshots/ (contains: 20260604-023854-pre-update)
  hermes_root_config/        ← ~/.hermes/config.yaml + all .bak.* files
  launchagents/              ← All critical LaunchAgent plist files
  REX_commands/              ← ~/Desktop/REX/*.command (copied by sandbox)
  REX_py_toplevel/           ← ~/Desktop/REX/*.py top-level (copied by sandbox)

Key config.yaml timestamps:
  ~/.hermes/config.yaml             — last modified Jun 4 13:13 (post-incident)
  config.yaml.bak.20260604_124719  — Jun 4 06:16 (pre-incident, SAFE version)
  config.yaml.bak.20260604_131352  — Jun 4 13:13 (at incident time)

Pre-update Hermes snapshot: state-snapshots/20260604-023854-pre-update

IMPORTANT: SOUL.md and MEMORY.md were NOT backed up (chflags uchg — PIN required).
MANIFEST
echo "  ✅ MANIFEST.txt written"

echo ""
echo "══════════════════════════════════════════════════"
echo "  BACKUP COMPLETE — $(date)"
echo "  Backup at: $BACKUP_DIR"
echo "══════════════════════════════════════════════════"
read -p "Press Enter to close..."
