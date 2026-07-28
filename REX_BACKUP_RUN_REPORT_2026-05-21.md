# REX Daily Backup — Run Report

- **Date:** 2026-05-21 07:02
- **Trigger:** Scheduled task `rex-daily-backup`
- **Result:** FAILED — script exited with code `2` (no backup created)

## Summary

The scheduled REX daily backup did not complete. The script `rex-backup.command`
exited with code `2` because its required destination — the external **"Cartoons"**
drive (`/Volumes/Cartoons`) — was not reachable. No snapshot was created, no files
were modified, and `.last_backup` was not updated.

## What happened

- Ran: `bash ~/Desktop/REX/rex-backup.command`
- Exit code: `2`
- Script output:
  > ✗ Cartoons external drive is NOT mounted.
  > Looked for: /Volumes/Cartoons and /Volumes/cartoons
  > Plug in the drive and re-run. No fallback to Desktop — by design.

The script hard-fails (by its own design) when the Cartoons drive is absent,
rather than falling back to the Desktop.

## Two root causes

**1. Environment mismatch.** This scheduled task runs in an isolated environment
that has the `REX` folder mounted but no access to macOS external drives —
`/Volumes` does not exist here. So even with the Cartoons drive physically plugged
into the Mac, this automated run cannot see it and the script cannot succeed.

**2. Stale task definition.** The scheduled-task description says the script
"backs up ~/Desktop/REX to ~/Desktop/REX_Backups/". That is no longer accurate.
The current script (header: *"Cartoons external drive edition"*) was deliberately
rewritten — see `BACKUP_DECOUPLE_REPORT_2026-04-18.md` — to back up **only** to
`/Volumes/Cartoons/REX_Backups/`, with no Desktop fallback. The task's success
criterion ("a new dated folder appears in ~/Desktop/REX_Backups/") can therefore
never be met by the current script.

## Also worth noting

`.last_backup` currently reads **`2026-04-20_07-42`** — the last *successful*
backup was 31 days ago. Backups have not been completing for about a month.

## Recommendations

1. **Run this backup natively on the Mac.** Because the script depends on a
   physical external drive, it should be scheduled with macOS `launchd` (or cron)
   on the Mac itself, not as a sandboxed Cowork scheduled task. You already use
   launchd — see `CC_fix_all_launchd.command`.
2. **Plug in the Cartoons drive and run `rex-backup.command` manually now** to
   confirm it works and capture a fresh snapshot — backups are a month stale.
3. **Update or retire this Cowork scheduled task.** Its description and success
   criteria reference the old Desktop destination and will always report failure
   in this environment.
4. **The script itself is sound** — rsync with sensible excludes, 14-snapshot
   pruning scoped to the backup folder, a `DO_NOT_USE_AS_SOURCE.txt` marker, and
   governed-asset verification. No changes to the script logic are needed.

The script was **not modified** and **no fallback backup was created** — consistent
with its stated design principle: *"Missed runs are better than quietly
re-polluting the Desktop."*
