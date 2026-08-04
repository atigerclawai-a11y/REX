#!/bin/bash
# =============================================================================
# CC_backup_output_to_gdrive.sh — GDrive Output Backup (DRAFT v1.3)
# =============================================================================
# STATUS: DRAFT — PAE proposal filed by Night Shift Cycle 2 (2026-08-04 03:15),
#   draft completed by Cycle 4 (05:10). NOT YET ACTIVE. Do NOT install until
#   Kato approves: ~/Documents/GHS-Vault/Cloud Backups/claude-wiki/concepts/
#   "Pending Approvals.md" → "GDrive Output Backup — recreate or pause".
#
# PURPOSE: Recreate work-profile cron b6c93f4f223e ("GDrive Output Backup",
#   23:00 daily). The ORIGINAL job 379f61695136 was a never-implemented exit-2
#   stub; b6c93f4f223e has failed EVERY run (exit 127) because this script was
#   deleted in the Aug 3 REX scripts incident and was never rebuilt. Recovery
#   hunt (C2) confirmed it is unrecoverable from any local source, and that
#   CC_daily_backup.sh's rsync include pattern (*.py|*.command|*.md|*.json)
#   NEVER captures .sh files — so any recreated .sh must ALSO be covered by a
#   backup-pattern fix (see follow-up in the PAE proposal), or it will be lost
#   in the next incident.
#
# BEHAVIOR:
#   1. Ensures Drive folder "REX_Output_Backup" exists (root level)
#   2. Ensures Drive subfolder "YYYYMMDD" exists under it
#   3. Uploads every TOP-LEVEL file in ~/Desktop/REX/output/ into that folder
#   4. Skips files whose name already exists in today's folder (idempotent)
#   5. Continues past individual upload failures; exits 1 if ANY failed
#
# DEPENDENCIES (all verified present 2026-08-04):
#   - jq                         (system /usr/bin/jq)
#   - google-workspace skill google_api.py (drive search / upload / create-folder)
#   - OAuth token with DRIVE scope — ⚠️ VERIFIED 2026-08-04: the CLOUD-profile
#     token (~/.hermes/profiles/cloud/google_token.json) is AUTHENTICATED but
#     has NO drive scope (any Drive call → 403 insufficientPermissions). The
#     WORK-profile token (~/.hermes/profiles/work/google_token.json) HAS
#     auth/drive. google_api.py resolves $HERMES_HOME/google_token.json, so we
#     FORCE HERMES_HOME to the work profile below — this is what makes Drive
#     calls succeed (verified live: drive search → valid JSON, exit 0).
#   - ~/.rex-venv/bin/python3 (google-api-python-client verified)
#
# INSTALL (after approval):
#   cp _DRAFT_CC_backup_output_to_gdrive.sh ~/Desktop/REX/CC_backup_output_to_gdrive.sh
#   chmod +x ~/Desktop/REX/CC_backup_output_to_gdrive.sh
#   # cron wrapper at ~/.hermes/profiles/work/scripts/CC_backup_output_to_gdrive.sh
#   # already execs the canonical path — no job change needed. The job runs on
#   # the WORK profile, so HERMES_HOME defaults to work naturally.
#   # TEST first: bash -n + preflight probe + a dry run against a copy of
#   # output/ (see PAE). Live uploads must not run before Kato approves.
# =============================================================================
set -uo pipefail

SRC="${HOME}/Desktop/REX/output"
TS="$(date +%Y%m%d)"
# google_api.py reads $HERMES_HOME/google_token.json; the WORK token is the one
# with Drive scope (cloud token verified scope-less for Drive, 403). b6c93f4f223e
# is a work-profile job, so work is the correct default; allow override.
export HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes/profiles/work}"
GAPI_PY="${HOME}/.hermes/profiles/cloud/skills/productivity/google-workspace/scripts/google_api.py"
PY="${PYTHON:-${HOME}/.rex-venv/bin/python3}"   # has google-api-python-client
ROOT_FOLDER="REX_Output_Backup"                 # parent folder under Drive root
PARENT_Q="name='${ROOT_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
LOG_FILE="${HOME}/Desktop/REX/logs/gdrive_output_backup.log"
FAILED=0

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE"; }

# --- preflight ---------------------------------------------------------------
[ -d "$SRC" ] || { log "ERROR: source dir $SRC missing"; exit 2; }
command -v jq >/dev/null || { log "ERROR: jq required"; exit 2; }
[ -f "$GAPI_PY" ] || { log "ERROR: google_api.py not found at $GAPI_PY"; exit 2; }
# Scope probe: a read-only Drive search must succeed. A 403 here means the
# resolved token ($HERMES_HOME/google_token.json) lacks Drive scope — switch
# HERMES_HOME to the work profile (token verified to carry auth/drive).
if ! PROBE=$("$PY" "$GAPI_PY" drive search "$PARENT_Q" --raw-query --max 1 2>&1); then
    log "ERROR: Drive API unreachable — check token scopes at $HERMES_HOME/google_token.json (need auth/drive). Probe output: $(echo "$PROBE" | head -1)"
    exit 1
fi

# --- 1. find-or-create parent folder -----------------------------------------
PARENT_ID=$("$PY" "$GAPI_PY" drive search "$PARENT_Q" --raw-query --max 1 2>/dev/null | jq -r 'if length > 0 then .[0].id else empty end')
if [ -z "$PARENT_ID" ]; then
    log "Parent '$ROOT_FOLDER' not found — creating"
    PARENT_ID=$("$PY" "$GAPI_PY" drive create-folder "$ROOT_FOLDER" 2>>"$LOG_FILE" | jq -r '.id // empty')
    [ -n "$PARENT_ID" ] || { log "ERROR: could not create parent folder"; exit 1; }
fi

# --- 2. find-or-create today's date folder -----------------------------------
DAY_ID=$("$PY" "$GAPI_PY" drive search "name='${TS}' and '${PARENT_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false" --raw-query --max 1 2>/dev/null | jq -r 'if length > 0 then .[0].id else empty end')
if [ -z "$DAY_ID" ]; then
    DAY_ID=$("$PY" "$GAPI_PY" drive create-folder "$TS" --parent "$PARENT_ID" 2>>"$LOG_FILE" | jq -r '.id // empty')
    [ -n "$DAY_ID" ] || { log "ERROR: could not create date folder $TS"; exit 1; }
fi
log "Target: REX_Output_Backup/$TS (folder $DAY_ID)"

# --- 3. upload top-level files, skipping names already present ----------------
COUNT=0
for f in "$SRC"/*; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    EXISTS=$("$PY" "$GAPI_PY" drive search "name='${base}' and '${DAY_ID}' in parents and trashed=false" --raw-query --max 1 2>/dev/null | jq -r 'if length > 0 then .[0].id else empty end')
    if [ -n "$EXISTS" ]; then
        log "SKIP $base (already uploaded as $EXISTS)"
        continue
    fi
    if "$PY" "$GAPI_PY" drive upload "$f" --name "$base" --parent "$DAY_ID" >>"$LOG_FILE" 2>&1; then
        log "OK   $base"
        COUNT=$((COUNT+1))
    else
        log "FAIL $base"
        FAILED=1
    fi
done

log "Done: $COUNT uploaded, any_failed=${FAILED}"
exit "$FAILED"
