# REX Backup Decouple — Verification Report

**Date:** 2026-04-18
**Operator directive (Kato):** "Make sure it doesnt interfere with any of my build and nothing is ever pulled from there as a source, I believe best is to just have it on the external Cartoons drive."
**Author of changes:** Claude (Cowork mode) — working against `/Volumes/REX` mount from a sandbox, no execution on the Mac.
**Reviewer expected:** Cline (with real on-Mac bash access).

---

## 1. Design invariants (do not break)

1. **REX snapshots live ONLY on the external Cartoons drive.** Accepted paths: `/Volumes/Cartoons/REX_Backups/` or `/Volumes/cartoons/REX_Backups/` (macOS volume name case can vary).
2. **No fallback to the Mac's internal disk.** If Cartoons isn't mounted, backup and drill operations fail loudly rather than silently writing to `~/Desktop`.
3. **Nothing in the REX build tree reads snapshots as a source.** Runtime, scanners, health checks, and dashboards either look at Cartoons or report "drive not mounted" — they never fall through to an in-tree `REX_Backups/` folder.
4. **Every snapshot carries a `DO_NOT_USE_AS_SOURCE.txt` marker.** Defensive breadcrumb for future-you or future-me.
5. **GOJ backups are untouched.** `~/Desktop/REX/GOJ_Backups/` and all GOJ code paths are out of scope for this decouple.
6. **`.last_backup` timestamp file lives in REX root.** It's a status marker, not snapshot content; health probes still read it.

---

## 2. Files changed

| File | Role | What changed |
|---|---|---|
| `rex-backup.command` | Daily backup script | Rewrote target from `~/Desktop/REX_Backups/` → `/Volumes/Cartoons/REX_Backups/` with lowercase fallback. Hard-fails if drive unmounted (exit 2) or unwritable (exit 3). Writes `DO_NOT_USE_AS_SOURCE.txt` into each snapshot. Added `REX_Backups/` to the rsync exclude list as defense-in-depth. 14-snapshot retention + governed-asset verification preserved. |
| `config/session.yaml` | REX session config | `rex_backup_root` blanked (`""`) with a doc-comment explaining the deprecation and pointing at `rex_restore_drill.py` as the single source of truth. `goj_backup_root` untouched. |
| `backend/rex_restore_drill.py` | Restore drill engine | `REX_BACKUP_ROOT` is no longer a module-level hardcoded `_BASE.parent / "REX_Backups"`. Introduced `_resolve_rex_backup_root()` that returns a Cartoons path or `None`. `_find_snapshot()` re-resolves on every call (handles mid-session drive plug-in) and gracefully drops REX snapshots from consideration when the drive is absent. "No snapshot found" error message updated to mention Cartoons. |
| `backend/main.py` | FastAPI backend | `/api/backup/status` reads from Cartoons (either casing). Returns `cartoons_mounted: false` and `backup_dir: null` when the drive is absent — no fallback. |
| `backend/rex_command_center_status.py` | Command Center status widget | `_backup_status()` rewritten to read Cartoons-only. Returns a clean "drive not mounted" payload for the UI. The pre-existing `skip = {"REX_Backups", ...}` source-tree scan exclusion was left alone — still correct. |
| `REX_HEALTH_CHECK.command` | Health check shell script | `BACKUP_DIR` now auto-detected from Cartoons (both casings). Warns plainly if the drive is unmounted, rather than falsely reporting "REX_Backups folder not found." |
| `teach_system_knowledge.command` | REX self-teaching facts | The "where are my backups?" fact rewritten to state Cartoons-only, the `DO_NOT_USE_AS_SOURCE.txt` marker, and the hard-fail behaviour. Keywords include `cartoons` and `external drive`. |
| `index.html`, `index copy.html`, `index_demo.html` | Dashboard UI | "Backup to REX_Backups" button label → "Backup to Cartoons". Toast message likewise. |

## 3. New file

| File | Role |
|---|---|
| `migrate-backups-to-cartoons.command` | **One-shot migration helper.** Dry-run by default; pass `--commit` to actually move. Migrates `~/Desktop/REX/REX_Backups/` (in-tree — highest priority) and `~/Desktop/REX_Backups/` (old sibling) onto Cartoons. Per-folder rsync → byte-count verify → source `rm` only on size match. Leaves `MOVED_TO_CARTOONS.txt` breadcrumb in each emptied source. Never auto-runs, never deletes data on Cartoons. |

---

## 4. Verification checklist — for Cline

Run each of these from a shell on the Mac with `cd ~/Desktop/REX` already done. They're read-only and safe.

### 4a. Syntax sanity

```bash
# Python files compile
python3 -m py_compile backend/main.py backend/rex_restore_drill.py backend/rex_command_center_status.py && echo "Python OK"

# Shell scripts parse
for f in rex-backup.command migrate-backups-to-cartoons.command REX_HEALTH_CHECK.command teach_system_knowledge.command; do
  bash -n "$f" && echo "  $f OK" || echo "  $f FAILED"
done

# YAML parses
python3 -c "import yaml; yaml.safe_load(open('config/session.yaml')); print('YAML OK')"
```

### 4b. No active path still points at the old backup locations

```bash
# Should list ONLY migrate-backups-to-cartoons.command (the migration helper itself).
grep -rn 'Desktop/REX_Backups\|REX_DIR/REX_Backups\|_BASE\.parent / "REX_Backups"' \
  --include='*.py' --include='*.sh' --include='*.command' \
  --include='*.yaml' --include='*.html' --include='*.js' \
  --exclude-dir=REX_Backups --exclude-dir=.venv --exclude-dir=node_modules \
  --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=_archive \
  2>/dev/null
```

Expected output: only lines from `migrate-backups-to-cartoons.command`. Anything else is a miss.

### 4c. All backup-status readers target Cartoons

```bash
grep -n 'Volumes/Cartoons/REX_Backups\|Volumes/cartoons/REX_Backups' \
  backend/main.py backend/rex_restore_drill.py backend/rex_command_center_status.py \
  REX_HEALTH_CHECK.command rex-backup.command
```

Expected: each file above appears at least once with the Cartoons path.

### 4d. Dry-run the backup script with no Cartoons connected

```bash
# With Cartoons UNPLUGGED, this should exit with code 2 and a clear message.
# Don't press Enter at the end; just Ctrl-C out after the error.
./rex-backup.command
echo "exit=$?"
```

Expected: "Cartoons external drive is NOT mounted" in red, exit code 2, nothing written to Desktop.

### 4e. Dry-run the migration helper (safe — no --commit)

```bash
./migrate-backups-to-cartoons.command
# (Don't pass --commit yet.)
```

Expected: inventory of what would move, no filesystem changes. If Cartoons is unmounted it exits 2 without moving anything.

### 4f. End-to-end backup test (requires Cartoons)

1. Plug Cartoons in.
2. `./rex-backup.command`
3. Verify a new `REX_YYYY-MM-DD_HH-MM` folder exists on `/Volumes/Cartoons/REX_Backups/`.
4. Verify it contains `DO_NOT_USE_AS_SOURCE.txt`.
5. Verify `~/Desktop/REX/.last_backup` updated to the new stamp.
6. `cat ~/Desktop/REX/.last_backup`.

### 4g. Restore-drill sanity (requires Cartoons + at least one snapshot)

```bash
python3 -c "
from backend.rex_restore_drill import RestoreDrill
d = RestoreDrill()
r = d.run()
print('result:', r.result)
print('snapshot:', r.snapshot_used)
print('notes:', r.notes)
"
```

Expected with Cartoons mounted: `result=passed` or at worst `failed` for a real governed-file reason — NOT "No snapshot found". Without Cartoons: `result=failed` with the "Cartoons drive" mention in `notes`.

### 4h. Migration (when you're ready — destructive on source)

```bash
# Plug in Cartoons, run once:
./migrate-backups-to-cartoons.command --commit
# Verify Cartoons now holds the snapshots and local dirs are empty or only contain MOVED_TO_CARTOONS.txt.
ls -la ~/Desktop/REX/REX_Backups 2>/dev/null
ls -la ~/Desktop/REX_Backups 2>/dev/null
ls /Volumes/Cartoons/REX_Backups/ 2>/dev/null | head -20
```

---

## 5. Out of scope (intentionally NOT changed)

| Item | Why |
|---|---|
| `~/Library/LaunchAgents/com.rex.daily-backup.plist` | Not reachable from the Cowork sandbox. The plist calls `rex-backup.command`, which now targets Cartoons on its own, so the plist itself is fine as-is. If you want the job to only run when Cartoons is mounted, switch the agent to use `StartOnMount` / `WatchPaths` pointing at `/Volumes/Cartoons`. |
| `~/.rex/` memory directory | Still backed up as a sidecar into each snapshot on Cartoons. Unchanged behaviour. |
| `GOJ_Backups/` and all GOJ code | Operator directive was REX-specific. |
| Historical markdown docs (`REX_CLAUDE_CONTEXT.md`, `REX_STARTUP_CHECKLIST.md`, `MASTER_SYSTEM_FILE_LOG.md`, `CARTOONS_BACKUP_MANIFEST.md`, `REX_PHASE_ARCHIVE/…`, `BUILD_DECISION_HISTORY.md`) | Descriptive, not executed. Refreshing them is a doc-cleanup pass, not a correctness issue. |
| `_archive/old_shell_scripts/rex_encrypted_backup.sh` and `rex_decrypt_backup.sh` | Already archived and already targeted `/Volumes/cartoons/REX_Backups/`. No change needed. |
| Keychain-held encryption key for `rex_encrypted_backup.sh` | Not reachable from Cowork. |

---

## 6. Known follow-up decisions

1. **Scheduled-task platform.** Today's Cowork scheduled run of `rex-backup.command` failed because the Cowork sandbox has no real `$HOME`. For this kind of on-Mac work, prefer a macOS LaunchAgent (`plist`) over a Cowork scheduled task. The script's hard-fail behaviour means a missed run is visible, not silent.
2. **Should the script trigger a Mac notification on hard-fail?** Right now it just prints red text and waits for Enter. If the LaunchAgent runs it headless, the error is invisible. Low-effort add: `osascript -e 'display notification ...'` in the failure paths.
3. **Encrypted-backup script.** `_archive/old_shell_scripts/rex_encrypted_backup.sh` already targets Cartoons. If you want encrypted-at-rest snapshots in addition to the plaintext rsync, that script can be revived and run alongside `rex-backup.command`. Currently out of scope.
4. **Launched dashboard buttons are cosmetic.** The "Backup to Cartoons" button in `index.html` only shows a toast — it doesn't actually call `rex-backup.command`. Wiring it up is a separate task.

---

## 7. File-by-file diff summary

All paths relative to `~/Desktop/REX/`.

- `rex-backup.command` — replaced (full rewrite). 155 lines. Executable bit preserved.
- `config/session.yaml` — two-line change; `rex_backup_root` blanked with header comment.
- `backend/rex_restore_drill.py` — three hunks: imports area, `_find_snapshot`, error-message string.
- `backend/main.py` — one hunk: `/api/backup/status` handler.
- `backend/rex_command_center_status.py` — one hunk: `_backup_status()` body.
- `REX_HEALTH_CHECK.command` — one hunk: `BACKUP_DIR` resolution + warning text.
- `teach_system_knowledge.command` — one fact row replaced.
- `index.html`, `index copy.html`, `index_demo.html` — one line each (button label + toast text).
- `migrate-backups-to-cartoons.command` — NEW, 175 lines, executable.

---

## 8. Sign-off criteria

Accept this decouple as done when all of the following are true:

- [ ] All `4a` syntax checks pass.
- [ ] `4b` grep returns only the migration helper.
- [ ] `4c` grep shows Cartoons paths in every listed file.
- [ ] `4d` reproduces the hard-fail without Cartoons.
- [ ] `4f` produces a real snapshot on Cartoons with the marker file.
- [ ] `4g` restore drill runs to completion (or fails with a real governed-file reason — not "no snapshot").
- [ ] Migration (`4h`) has been run once, and `~/Desktop/REX/REX_Backups/` and `~/Desktop/REX_Backups/` are either gone or contain only `MOVED_TO_CARTOONS.txt`.
