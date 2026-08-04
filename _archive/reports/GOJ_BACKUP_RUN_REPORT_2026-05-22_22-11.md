# REX GOJ Operational Backup — Run Report

**Run:** Friday, May 22, 2026 — 22:11 UTC (automated scheduled task `rex-goj-backup`)
**Script:** `~/Desktop/REX/rex-backup-goj.command`
**Result:** Backup created successfully (exit code 0). One non-fatal issue — see *Pruning* below.

---

## Outcome

The new backup snapshot was created and verified:

- **Location:** `~/Desktop/REX/GOJ_Backups/GOJ_2026-05-22_22-11/`
- **MANIFEST.txt:** present (3,547 bytes, lists 29 files)
- **Files captured:** 29 files, 524 KB total
- **Timestamp file** `~/Desktop/REX/.last_goj_backup` updated to `Fri May 22 22:11:16 UTC 2026`

## What was backed up

| Section | Result |
|---|---|
| [1/5] Telegram config & cache | `rex_telegram_config.json`, `rex_rexxie_telegram_config.json` copied. `~/.telegram_channel_cache.json` **skipped** — see Notes. |
| [2/5] Authorization document uploads | `~/Desktop/REX/uploads/` is empty — nothing to copy. |
| [3/5] Gmail config & cached results | All 5 files copied: `rex_gmail_auth.py`, `rex_paperless_config.json`, `rex_queue_config.json`, `gmail_token.json`, `goj_signin_processed.json`. |
| [4/5] Google Drive sync manifest | `GOJ_Master_Routes.json` copied. `.drive_sync.json` **not found** in the REX folder — skipped. |
| [5/5] Prompt Registry | 20 files copied: registry index, audit log (96 entries), `prompt_edits.db`, and the full `prompts/` tree (17 files, 6 version snapshots). |

## Issue — automatic pruning did not run

The script's 30-day prune step reported "Pruned 15 old backup(s)", but **no old backups were actually deleted.** Every `rm` call returned `Operation not permitted`, and all 53 prior snapshots remain in `GOJ_Backups/` (54 total including today's).

Cause: this scheduled run executes in a sandboxed environment that can create and write files in the REX folder but cannot delete pre-existing files there. The script prints "Removed: ..." unconditionally after each delete attempt, so its on-screen summary is misleading — the deletions silently failed.

This is **not a data-loss risk** — it only means old snapshots are accumulating (currently 54, the oldest dating to April 5). To reclaim space, run the script directly on the Mac (double-click `rex-backup-goj.command`), where the prune will work, or delete old `GOJ_*` folders manually.

## Notes

- `~/.telegram_channel_cache.json` lives in the user's home directory, which is outside the folder this automated task can reach; it is skipped on sandboxed runs. It is captured normally when the script is run directly on the Mac.
- Minor documentation mismatch: the task description lists the output path as `~/Desktop/REX_GOJ_Backups/` and describes 4 backup categories. The script actually writes to `~/Desktop/REX/GOJ_Backups/` and backs up 5 categories (it also includes the Prompt Registry). The script behavior is internally consistent; only the task description text is slightly out of date.

## Bottom line

Today's GOJ backup completed and is verified intact. The only follow-up is housekeeping: old snapshots are no longer auto-pruning under the scheduled run — run the backup manually on the Mac periodically, or clear out old `GOJ_Backups/GOJ_*` folders by hand.
