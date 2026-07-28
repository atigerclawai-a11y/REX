#!/bin/bash
# CC_dock_reset.command — Force dock back to bottom, disable auto-hide

echo "== Dock Full Reset =="
echo "Setting position: bottom"
defaults write com.apple.dock orientation -string "bottom"

echo "Disabling auto-hide"
defaults write com.apple.dock autohide -bool false

echo "Re-enabling dock"
defaults write com.apple.dock static-only -bool false

echo "Setting tile-size to 60"
defaults write com.apple.dock tilesize -int 60

echo "Killing and restarting Dock..."
killall Dock
sleep 3
echo "Done — dock should be back at the bottom."
read -p "Press any key to close..."
