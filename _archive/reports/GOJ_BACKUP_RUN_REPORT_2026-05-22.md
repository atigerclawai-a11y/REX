# GOJ Operational Backup — Run Report

**Run:** Friday, May 22 2026, 10:11 UTC (scheduled task `rex-goj-backup`)
**Script:** `~/Desktop/REX/rex-backup-goj.command`
**Result:** Backup completed successfully (exit code 0). Pruning step did not complete — see note below.

## Verification

- Output directory created: `~/Desktop/REX/GOJ_Backups/GOJ_2026-05-22_10-11/` — confirmed.
- `MANIFEST.txt` present inside it (3,727 bytes, lists 29 files) — confirmed.
- `.last_goj_backup` timestamp updated to `Fri May 22 10:11:20 UTC 2026` — confirmed.

## What was captured (29 files, 524K)

- **Telegram** — `rex_telegram_config.json`, `rex_rexxie_telegram_config.json`.
- **Gmail** — `rex_gmail_auth.py`, `rex_paperless_config.json`, `rex_queue_config.json`, `gmail_token.json`, `goj_signin_processed.json`.
- **Google Drive** — `GOJ_Master_Routes.json`.
- **Prompt Registry** — `prompt_registry.json` (index), `prompt_audit.log` (96 entries), `prompt_edits.db`, and the full `prompts/` tree: 17 files including 6 version snapshots. All critical registry items present.

## Items skipped (not found — not errors)

- `.telegram_channel_cache.json` — lives in the user home directory, outside the REX folder; not reachable from the scheduled-run environment.
- `.drive_sync.json` — not present in the REX folder.
- `uploads/` — directory is empty, nothing to copy.

## Note: pruning did not complete this run

The script targets backups older than 30 days for removal (15 snapshots, Apr 5–19). In this scheduled run the `rm` operations returned "Operation not permitted" for files belonging to earlier backup runs, so those 15 directories were **not** actually deleted. `GOJ_Backups/` currently holds **52 snapshots**.

The script reports "Pruned 15" because it does not check the exit status of `rm`; the count is cosmetic. This is most likely a file-ownership artifact of the sandboxed scheduled-run environment rather than a problem with the backup data itself. Running the script directly on the Mac (where all files are owned by the local user) should prune normally. If the snapshot count keeps growing, run `~/Desktop/REX/rex-backup-goj.command` manually once, or delete the pre-April-22 `GOJ_*` folders by hand.

## Minor discrepancy

The scheduled-task description states output goes to `~/Desktop/REX_GOJ_Backups/`. The script actually writes to `~/Desktop/REX/GOJ_Backups/` (inside the REX folder). Backups are landing correctly; only the documented path differs.
