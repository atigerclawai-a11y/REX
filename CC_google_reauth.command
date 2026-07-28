#!/bin/bash
# Double-click to reauthorize Google OAuth
# Opens a browser for Google sign-in, saves fresh token
cd ~/Desktop/REX || exit 1
.venv-ocr/bin/python3 CC_google_reauth.py
echo ""
echo "Press any key to close..."
read -n 1
