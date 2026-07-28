#!/bin/bash
# CC_lock_screen.command — One-click lock screen when leaving desk
# Double-click this from Dock or Desktop to lock immediately.
# No log needed — this is a one-shot action.

/System/Library/CoreServices/Menu\ Extras/User.menu/Contents/Resources/CGSession -suspend
