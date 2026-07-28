#!/bin/bash
# Nightly backup: GOJ attendance DB + auth_tracker
# Requires /Volumes/cartoons to be mounted

SRC_ATTEND="$HOME/Desktop/REX/attendance.db"
SRC_AUTH="$HOME/Documents/goj files/auth_tracker.db"
DEST="/Volumes/cartoons/hermes-backups/attendance"
TS=$(date +%Y-%m-%d)

if [ ! -d /Volumes/cartoons ]; then
    echo "❌ cartoons not mounted — skipping backup"
    exit 1
fi

mkdir -p "$DEST"
cp "$SRC_ATTEND" "$DEST/attendance-${TS}.db" && echo "✅ attendance → $DEST/attendance-${TS}.db"
cp "$SRC_AUTH"    "$DEST/auth_tracker-${TS}.db" && echo "✅ auth_tracker → $DEST/auth_tracker-${TS}.db"

# Keep last 30 days
find "$DEST" -name "attendance-*.db" -mtime +30 -delete
find "$DEST" -name "auth_tracker-*.db" -mtime +30 -delete
