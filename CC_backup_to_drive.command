#!/bin/bash
# CC_backup_to_drive.command
# Full GHS/GOJ/Hermes backup to portable hard drive
# Run before any repo installations or major system changes
# Double-click to run, or: bash CC_backup_to_drive.command

set -e

LOG="$HOME/Desktop/REX/logs/cc_backup_$(date +%Y-%m-%d_%H%M%S).log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "======================================================"
echo " GHS/Hermes Full Backup — $(date)"
echo "======================================================"

# -------------------------------------------------------
# STEP 1: Find the portable drive
# -------------------------------------------------------
echo ""
echo ">>> Scanning for external drives..."

EXTERNAL_DRIVES=()
for vol in /Volumes/*/; do
    # Skip the main Mac boot disk
    if [ "$vol" = "/Volumes/Macintosh HD/" ] || [ "$vol" = "/Volumes/Macintosh HD - Data/" ]; then
        continue
    fi
    # Skip virtual/system volumes
    volname=$(basename "$vol")
    if [[ "$volname" == "Recovery" ]] || [[ "$volname" == "VM" ]] || [[ "$volname" == "Preboot" ]]; then
        continue
    fi
    EXTERNAL_DRIVES+=("$vol")
done

if [ ${#EXTERNAL_DRIVES[@]} -eq 0 ]; then
    echo ""
    echo "ERROR: No external drives found in /Volumes/"
    echo "Please connect your portable hard drive and try again."
    echo ""
    echo "Available volumes:"
    ls /Volumes/
    exit 1
fi

echo ""
echo "Found ${#EXTERNAL_DRIVES[@]} external drive(s):"
for i in "${!EXTERNAL_DRIVES[@]}"; do
    echo "  [$i] ${EXTERNAL_DRIVES[$i]}"
done

# If only one drive, use it automatically
if [ ${#EXTERNAL_DRIVES[@]} -eq 1 ]; then
    TARGET_DRIVE="${EXTERNAL_DRIVES[0]}"
    echo ""
    echo ">>> Using: $TARGET_DRIVE"
else
    echo ""
    echo "Multiple drives found. Edit this script and set TARGET_DRIVE manually."
    echo "Or connect only the drive you want to back up to."
    exit 1
fi

# -------------------------------------------------------
# STEP 2: Create timestamped backup destination
# -------------------------------------------------------
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_DIR="${TARGET_DRIVE}GHS_Backups/backup_${TIMESTAMP}"

echo ""
echo ">>> Creating backup directory: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Check available space (need at least 5GB free)
AVAIL_KB=$(df -k "$TARGET_DRIVE" | tail -1 | awk '{print $4}')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
echo "    Available space on drive: ${AVAIL_GB}GB"
if [ "$AVAIL_KB" -lt 5000000 ]; then
    echo "WARNING: Less than 5GB free on drive. Backup may fail. Proceeding anyway..."
fi

# -------------------------------------------------------
# STEP 3: Define what to back up
# -------------------------------------------------------

backup_item() {
    local src="$1"
    local label="$2"

    if [ ! -e "$src" ]; then
        echo "    [SKIP] $label — not found at $src"
        return
    fi

    local dest_parent="$BACKUP_DIR/$(dirname "${src/#$HOME\//home/}")"
    mkdir -p "$dest_parent"

    echo "    [COPY] $label"
    rsync -a --exclude="*.pyc" --exclude="__pycache__" \
              --exclude=".git" --exclude="node_modules" \
              --exclude="*.log" \
              "$src" "$dest_parent/" 2>&1 | head -5
}

echo ""
echo ">>> Backing up critical paths..."
echo ""

# --- Hermes core systems ---
echo "--- Hermes ---"
backup_item "$HOME/.hermes"            "Hermes main install (~/.hermes)"
backup_item "$HOME/.hermes-cloud"      "Hermes cloud install (~/.hermes-cloud)"

# --- REX scripts and configs ---
echo ""
echo "--- REX / Desktop ---"
backup_item "$HOME/Desktop/REX"                   "REX scripts and configs"
backup_item "$HOME/Desktop/Gold_Health_Systems"   "Gold Health Systems folder"

# --- GOJ files and database ---
echo ""
echo "--- GOJ Operations ---"
backup_item "$HOME/Documents/goj files"           "GOJ files (menus, auth, dashboard DB)"

# --- LaunchAgent plists ---
echo ""
echo "--- LaunchAgents ---"
backup_item "$HOME/Library/LaunchAgents"          "LaunchAgent plists"

# --- Google auth tokens ---
echo ""
echo "--- Google Auth ---"
backup_item "$HOME/.rex_google_token.json"        "Google OAuth token"
backup_item "$HOME/.rex_google_credentials.json"  "Google credentials symlink"

# --- Cloudflare tunnel config ---
echo ""
echo "--- Cloudflare ---"
backup_item "$HOME/.cloudflared"                  "Cloudflare tunnel config"

# --- Claude config ---
echo ""
echo "--- Claude ---"
backup_item "$HOME/.claude"                       "Claude config directory"

# --- Ollama models list (not the models themselves — too large) ---
echo ""
echo "--- Ollama ---"
if command -v ollama &>/dev/null; then
    echo "    [LIST] Ollama models inventory"
    mkdir -p "$BACKUP_DIR/ollama"
    ollama list > "$BACKUP_DIR/ollama/models_list_${TIMESTAMP}.txt" 2>&1
    echo "    Saved model list to backup"
fi

# -------------------------------------------------------
# STEP 4: Write a manifest
# -------------------------------------------------------
echo ""
echo ">>> Writing backup manifest..."

MANIFEST="$BACKUP_DIR/MANIFEST.txt"
cat > "$MANIFEST" << MANIFEST_EOF
GHS/Hermes Backup Manifest
===========================
Date: $(date)
Mac user: $(whoami)
Hostname: $(hostname)
macOS: $(sw_vers -productVersion 2>/dev/null || echo "unknown")

Backed up from: $HOME
Backed up to: $BACKUP_DIR

Contents:
MANIFEST_EOF

find "$BACKUP_DIR" -maxdepth 3 -not -name "MANIFEST.txt" | sort | head -100 >> "$MANIFEST"

# -------------------------------------------------------
# STEP 5: Size check
# -------------------------------------------------------
echo ""
echo ">>> Backup size:"
du -sh "$BACKUP_DIR"

echo ""
echo "======================================================"
echo " BACKUP COMPLETE"
echo " Location: $BACKUP_DIR"
echo " Log: $LOG"
echo "======================================================"
echo ""
echo "Press any key to close..."
read -n 1 -s
