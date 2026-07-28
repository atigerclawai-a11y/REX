#!/bin/bash
# CC_launch_hermes_desktop.command — opens Hermes desktop → gateway port 3002
HERMES_API_URL=http://127.0.0.1:3002 \
HERMES_DASHBOARD_URL=http://127.0.0.1:9120 \
open "/Applications/Hermes.app"
