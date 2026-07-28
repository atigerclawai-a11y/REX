#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  REX — One-shot Backup Migration to Cartoons
#
#  Moves existing REX backup trees OFF the Mac's internal drive and
#  onto the external Cartoons drive at /Volumes/Cartoons/REX_Backups/.
#  Sources migrated:
#    1. ~/Desktop/REX/REX_Backups/   (in-tree — the biggest offender;
#                                     these were being indexed by REX
#                                     as if they were live sources)
#    2. ~/Desktop/REX_Backups/       (sibling of REX — the old script's
#                                     historical output location)
#
#  Behaviour:
#    • Dry-run by default. Pass --commit to actually move anything.
#    • rsync with --remove-source-files semantics (via rsync + rm of
#      emptied dirs) — nothing is deleted until a successful copy is
#      verified on Cartoons.
#    • After a successful move, leaves a MOVED_TO_CARTOONS.txt stub in
#      each original location explaining where the data went.
#    • NEVER auto-runs. You invoke it explicitly.
#    • NEVER deletes anything on Cartoons.
#
#  Usage:
#    ./migrate-backups-to-cartoons.command                  # dry run
#    ./migrate-backups-to-cartoons.command --commit         # actually migrate
# ─────────────────────────────────────────────────────────────────────

set -u

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

COMMIT=0
if [ "${1:-}" = "--commit" ]; then
  COMMIT=1
fi

REX_ROOT="$HOME/Desktop/REX"
IN_TREE_SRC="$REX_ROOT/REX_Backups"
SIBLING_SRC="$HOME/Desktop/REX_Backups"

# Locate Cartoons (case variants)
CARTOONS_MOUNT=""
for candidate in "/Volumes/Cartoons" "/Volumes/cartoons"; do
  if [ -d "$candidate" ]; then
    CARTOONS_MOUNT="$candidate"
    break
  fi
done

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   🚚  REX Backup Migration → Cartoons${NC}"
if [ $COMMIT -eq 1 ]; then
  echo -e "${RED}   MODE: COMMIT (actual move)${NC}"
else
  echo -e "${YELLOW}   MODE: DRY RUN (re-run with --commit to move)${NC}"
fi
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Preflight
if [ -z "$CARTOONS_MOUNT" ]; then
  echo -e "${RED}✗ Cartoons external drive is NOT mounted.${NC}"
  echo -e "${YELLOW}   Plug it in and re-run.${NC}"
  echo "Press Enter to close..."; read; exit 2
fi

DEST_ROOT="$CARTOONS_MOUNT/REX_Backups"
if [ $COMMIT -eq 1 ]; then
  mkdir -p "$DEST_ROOT"
fi

echo -e "${GREEN}✓ Cartoons mounted at: $CARTOONS_MOUNT${NC}"
echo -e "${GREEN}  Destination root:    $DEST_ROOT${NC}\n"

# ── Function: migrate one source tree ────────────────────────────────
migrate_tree() {
  local src="$1"
  local label="$2"

  echo -e "${YELLOW}── Source:${NC} $src  (${label})"

  if [ ! -d "$src" ]; then
    echo -e "  ${YELLOW}–${NC} Not present — nothing to migrate from this location.\n"
    return 0
  fi

  local count
  count=$(find "$src" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')
  local size
  size=$(du -sh "$src" 2>/dev/null | awk '{print $1}')

  echo -e "  Found: $count subdirectory(ies), total $size"

  # List what we'd copy
  find "$src" -maxdepth 1 -mindepth 1 -type d | sort | while read -r d; do
    local sz
    sz=$(du -sh "$d" 2>/dev/null | awk '{print $1}')
    echo -e "    • $(basename "$d")  [$sz]"
  done

  if [ $COMMIT -eq 0 ]; then
    echo -e "  ${YELLOW}[dry-run] Would rsync → $DEST_ROOT/ and remove source.${NC}\n"
    return 0
  fi

  # rsync each top-level subdir individually so we can verify and
  # delete each one atomically.
  local moved=0
  local failed=0
  while IFS= read -r d; do
    local name
    name=$(basename "$d")
    local target="$DEST_ROOT/$name"

    if [ -e "$target" ]; then
      echo -e "  ${YELLOW}!${NC} $name — already exists on Cartoons, skipping move (source kept)."
      continue
    fi

    echo -n "  Moving $name ... "
    if rsync -a --quiet "$d/" "$target/"; then
      # Verify size matches before deleting source
      local src_sz tgt_sz
      src_sz=$(du -sb "$d"     2>/dev/null | awk '{print $1}')
      tgt_sz=$(du -sb "$target" 2>/dev/null | awk '{print $1}')
      if [ "$src_sz" = "$tgt_sz" ]; then
        rm -rf "$d"
        echo -e "${GREEN}ok${NC}"
        moved=$((moved + 1))
      else
        echo -e "${RED}size mismatch (src=$src_sz, tgt=$tgt_sz) — source KEPT${NC}"
        failed=$((failed + 1))
      fi
    else
      echo -e "${RED}rsync failed — source KEPT${NC}"
      failed=$((failed + 1))
    fi
  done < <(find "$src" -maxdepth 1 -mindepth 1 -type d | sort)

  echo -e "  ${GREEN}✓ Moved: $moved${NC}   ${RED}Failed: $failed${NC}"

  # If the source dir is now empty (ignoring hidden macOS cruft),
  # leave a stub so future-you knows where the data went.
  local remaining
  remaining=$(find "$src" -maxdepth 1 -mindepth 1 | grep -v '/\.DS_Store$' | wc -l | tr -d ' ')
  if [ "$remaining" = "0" ]; then
    cat > "$src/MOVED_TO_CARTOONS.txt" <<EOF
This directory's contents were migrated to the external Cartoons drive.
Migration run: $(date '+%Y-%m-%d %H:%M:%S %Z')
New location:  $DEST_ROOT/

REX no longer reads backups from this location. Future snapshots are
written by rex-backup.command directly to Cartoons.

You can safely delete this stub file (and the empty parent dir if it's
no longer needed). It exists only as a breadcrumb.
EOF
    echo -e "  ${GREEN}✓ Left MOVED_TO_CARTOONS.txt stub in $src${NC}\n"
  else
    echo -e "  ${YELLOW}  $remaining item(s) still in source — no stub written.${NC}\n"
  fi
}

# ── Run migrations ───────────────────────────────────────────────────
migrate_tree "$IN_TREE_SRC" "in-tree: ~/Desktop/REX/REX_Backups — HIGHEST PRIORITY"
migrate_tree "$SIBLING_SRC" "sibling: ~/Desktop/REX_Backups — old script output"

# ── Summary ──────────────────────────────────────────────────────────
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $COMMIT -eq 0 ]; then
  echo -e "${YELLOW}  DRY RUN complete. Re-run with --commit to migrate.${NC}"
else
  TOTAL=$(find "$DEST_ROOT" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
  TOTAL_SIZE=$(du -sh "$DEST_ROOT" 2>/dev/null | awk '{print $1}')
  echo -e "${GREEN}  ✅  Migration done.${NC}"
  echo -e "${GREEN}  📁  Cartoons now holds $TOTAL snapshot folder(s) ($TOTAL_SIZE).${NC}"
fi
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

echo "Press Enter to close..."; read
