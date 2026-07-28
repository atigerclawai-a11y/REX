#!/bin/bash
# Victoria Daily Attendance Caller — 2 PM Mon-Fri
# Hermes cron wrapper for goj_victoria_caller.py

cd /Users/mainsobhelper/Desktop/REX || exit 1
exec /Users/mainsobhelper/Desktop/REX/.venv-ocr/bin/python goj_victoria_caller.py
