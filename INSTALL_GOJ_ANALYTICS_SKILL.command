#!/bin/bash
# GOJ Analytics Skill Installer
# Double-click this file to install the skill into Claude

SKILL_FILE="$(dirname "$0")/goj-analytics.skill"
SKILLS_DIR="$HOME/Library/Application Support/Claude/claude_desktop_config"
COWORK_SKILLS="$HOME/Library/Application Support/Claude/skills"

# Try to find the Claude skills directory
if [ -d "$HOME/.claude/skills" ]; then
    TARGET="$HOME/.claude/skills"
elif [ -d "$COWORK_SKILLS" ]; then
    TARGET="$COWORK_SKILLS"
else
    TARGET="$HOME/.claude/skills"
    mkdir -p "$TARGET"
fi

echo "Installing GOJ Analytics skill..."
echo "Target: $TARGET"

# Unzip the .skill file (it's a standard zip)
cd "$TARGET"
unzip -o "$SKILL_FILE" -d "$TARGET"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Installed successfully!"
    echo "Skill location: $TARGET/goj-analytics/"
    echo ""
    echo "Scripts are ready at: $TARGET/goj-analytics/scripts/"
    echo "Run any script with: python3 <script>.py --help"
    echo ""
    echo "Also installing Python dependencies..."
    pip install openpyxl reportlab --break-system-packages --quiet
    echo "✓ Dependencies ready."
else
    echo ""
    echo "✗ Install failed. Try manually:"
    echo "  1. Open Terminal"
    echo "  2. Run: unzip '$SKILL_FILE' -d ~/.claude/skills/"
    echo "  3. Run: pip install openpyxl reportlab --break-system-packages"
fi

echo ""
read -p "Press Enter to close..."
