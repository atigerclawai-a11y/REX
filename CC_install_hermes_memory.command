#!/bin/bash
# CC_install_hermes_memory.command
# Installs the Hermes knowledge archive into the LIVE, uchg-locked MEMORY.md.
# Kato-run only (the agent harness is blocked from touching the locked memory).
#
# It is SAFE-BY-DEFAULT:
#   1. backs up the current MEMORY.md (timestamped) before anything
#   2. shows you the size change and PAUSES for an explicit "yes"
#   3. clears the uchg lock, installs, re-locks, verifies
#   4. prints a one-line rollback command
#
# NOTE: MEMORY.md is normally a COMPACT §-delimited file (~2.8 KB). The archive is ~27 KB.
# Installing it makes Hermes's working memory ~13× larger. Abort at the prompt if that's
# not what you want — the report already lives durably in the archive either way.
set -euo pipefail

SRC=~/Desktop/REX/CC_HERMES_KNOWLEDGE.md
DST=~/.hermes/profiles/cloud/memories/MEMORY.md
BKDIR=~/Desktop/REX/CC_memory_backups
STAMP=$(date +%Y%m%d_%H%M%S)
LOG=~/Desktop/REX/logs/CC_install_hermes_memory_${STAMP}.log
exec > >(tee "$LOG") 2>&1

[ -f "$SRC" ] || { echo "❌ source missing: $SRC"; exit 1; }
[ -f "$DST" ] || { echo "❌ target missing: $DST"; exit 1; }

mkdir -p "$BKDIR"
BK="$BKDIR/MEMORY.md.bak_${STAMP}"
cp -p "$DST" "$BK"
echo "✅ backed up current MEMORY.md → $BK"

CUR=$(wc -c < "$DST" | tr -d ' ')
NEW=$(wc -c < "$SRC" | tr -d ' ')
echo
echo "  current MEMORY.md : ${CUR} bytes"
echo "  archive to install: ${NEW} bytes"
echo "  flags on target   : $(ls -lO "$DST" | awk '{print $5}')"
echo
read -r -p "Overwrite the live MEMORY.md with the archive? [y/N] " ANS
case "$ANS" in
  y|Y|yes|YES) ;;
  *) echo "Aborted. Nothing changed. Backup kept at $BK"; exit 0 ;;
esac

# Clear the immutable lock (owner can clear uchg without sudo; if a PIN wrapper guards it,
# this will fail and you'll be told to clear it manually).
if ! chflags nouchg "$DST" 2>/dev/null; then
  echo "⚠️  could not clear uchg on $DST automatically."
  echo "    Clear it manually, then re-run:  chflags nouchg \"$DST\""
  exit 1
fi

cp "$SRC" "$DST"
chmod 600 "$DST"
chflags uchg "$DST"

# Verify: content matches source (ignoring the lock) and lock is back on.
if cmp -s "$SRC" "$DST"; then
  echo "✅ installed archive → $DST  ($(wc -c < "$DST" | tr -d ' ') bytes)"
else
  echo "❌ verify FAILED — restoring backup"
  chflags nouchg "$DST" 2>/dev/null || true
  cp "$BK" "$DST"; chflags uchg "$DST" 2>/dev/null || true
  echo "Restored from $BK"; exit 1
fi
ls -lO "$DST" | grep -q uchg && echo "✅ uchg re-locked" || echo "⚠️  re-lock did not stick — run: chflags uchg \"$DST\""

echo
echo "Rollback if needed:"
echo "  chflags nouchg \"$DST\" && cp \"$BK\" \"$DST\" && chflags uchg \"$DST\""
