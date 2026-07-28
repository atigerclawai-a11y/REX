#!/bin/bash
# CC_build_nerve_center.command — Build and launch the GHS Nerve Center (Tauri)
# Requires: Rust + cargo, Node.js + npm, @tauri-apps/cli
exec > >(tee "$HOME/Desktop/REX/logs/nerve_center_build_$(date +%Y%m%d_%H%M%S).log") 2>&1

echo "=== GHS NERVE CENTER BUILD ==="
echo "Time: $(date)"
echo ""

NERVE_DIR="$HOME/Desktop/REX/CC_nerve_center"
cd "$NERVE_DIR" || { echo "❌ CC_nerve_center directory not found"; read; exit 1; }

# Check prerequisites
echo "[1/5] Checking prerequisites..."
command -v cargo >/dev/null || { echo "❌ Rust not found. Install from https://rustup.rs"; read; exit 1; }
command -v node >/dev/null || { echo "❌ Node.js not found. Install from https://nodejs.org"; read; exit 1; }
echo "✅ Rust: $(rustc --version)"
echo "✅ Node: $(node --version)"

# Install Tauri CLI if needed
echo ""
echo "[2/5] Checking Tauri CLI..."
if ! npx tauri --version >/dev/null 2>&1; then
    echo "Installing @tauri-apps/cli..."
    npm install --save-dev @tauri-apps/cli @tauri-apps/api
fi
echo "✅ Tauri: $(npx tauri --version)"

# Add macOS arm64 Rust target
echo ""
echo "[3/5] Ensuring Rust target..."
rustup target add aarch64-apple-darwin 2>/dev/null
echo "✅ arm64 target ready"

# Build
echo ""
echo "[4/5] Building Nerve Center..."
echo "    (This takes 3–8 minutes on first build)"
npx tauri build --target aarch64-apple-darwin

if [ $? -eq 0 ]; then
    APP="$NERVE_DIR/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/GHS Nerve Center.app"
    echo ""
    echo "✅ BUILD SUCCESSFUL"
    echo ""
    echo "[5/5] Installing to Applications..."
    if [ -d "$APP" ]; then
        cp -R "$APP" "/Applications/"
        echo "✅ Installed: /Applications/GHS Nerve Center.app"
        echo ""
        echo "Launching..."
        open "/Applications/GHS Nerve Center.app"
    else
        echo "⚠️  App bundle at: $APP"
        open "$NERVE_DIR/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/"
    fi
else
    echo ""
    echo "❌ Build failed. Check the log above."
    echo ""
    echo "Quick preview (opens in browser without Tauri):"
    open "$NERVE_DIR/index.html"
fi

echo ""
read -p "Press Enter to close..."
