#!/bin/bash
# PAE Gate — Kato must approve before Victoria calls
# This file is the kill switch. If it exists with "approved", calls go.
# If it doesn't exist or says "hold", calls are blocked.

APPROVAL_FILE="$HOME/.victoria_approval"

case "${1:-check}" in
    approve)
        echo "approved $(date '+%Y-%m-%d %H:%M')" > "$APPROVAL_FILE"
        echo "✅ Victoria calls APPROVED"
        ;;
    hold)
        echo "hold $(date '+%Y-%m-%d %H:%M')" > "$APPROVAL_FILE"
        echo "⛔ Victoria calls HELD"
        ;;
    check)
        if [ -f "$APPROVAL_FILE" ]; then
            read STATUS DATE < "$APPROVAL_FILE"
            if [ "$STATUS" = "approved" ]; then
                FILE_DATE=$(echo "$DATE" | cut -d' ' -f1)
                TODAY=$(date '+%Y-%m-%d')
                if [ "$FILE_DATE" = "$TODAY" ]; then
                    echo "approved"
                    exit 0
                fi
            fi
        fi
        echo "hold"
        exit 1
        ;;
esac
