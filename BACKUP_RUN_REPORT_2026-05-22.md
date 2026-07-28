# REX Daily Backup — Scheduled Run Report

**Run timestamp:** 2026-05-22 07:03
**Task:** `rex-daily-backup` (automated, unattended)
**Outcome:** ❌ FAILED — no backup snapshot was created.

---

## Summary

The scheduled backup did **not** complete. No new dated folder was created, and
`~/Desktop/REX/.last_backup` was **not** updated. It still reads `2026-04-20_07-42`
— meaning the last *successful* backup was **32 days ago**. Backups have been
silently failing for over a month.

Two separate problems are responsible. One is an environment limitation of this
scheduled run; the other is a stale task definition. Neither was fixed
automatically, because fixing either one safely requires a human decision.

---

## What happened (exact results)

| Attempt | Command | Exit code | Result |
|---|---|---|---|
| 1 | `bash ~/Desktop/REX/rex-backup.command` (literal, as the task specifies) | `127` | Script file not found — see Problem A |
| 2 | Script run from its real location, unmodified | `1` | "REX source not found" — see Problem A |
| 3 | Script run with the source path corrected (simulating the Mac) | `2` | "Cartoons external drive is NOT mounted" — see Problem B |

The success criterion (`exit code 0` + a new folder in a backups directory) was
not met under any condition.

---

## Problem A — This scheduled job runs in a sandbox, not on the Mac

The scheduled task executes `bash ~/Desktop/REX/rex-backup.command` inside an
isolated Linux environment. In that environment `~` is **not** your Mac home
folder, and there is **no `/Volumes`**, so the external drive can never be seen.

The REX folder itself is reachable (it is mounted), but the script is a macOS
`.command` file that expects to run on the Mac with the external drive attached.
**As currently wired, this scheduled job can never perform the backup**, even if
the drive is plugged in.

➡️ The backup job needs to run *on the Mac itself* (e.g. a `launchd` agent or
`cron` entry on macOS), not through this sandboxed scheduled task.

## Problem B — The task description no longer matches the script

The task definition says the script:

> "Backs up ~/Desktop/REX to ~/Desktop/REX_Backups/… Keeps the 14 most recent
> backups…"

The **actual** script on disk is the *"Cartoons external drive edition"*. It:

- Backs up to **`/Volumes/Cartoons/REX_Backups/`** — the external drive, **not**
  `~/Desktop/REX_Backups/`.
- **Hard-fails with exit code 2** if the Cartoons drive is not mounted. This is
  deliberate — the script header states: *"NO silent fallback to Desktop.
  Missed runs are better than quietly re-polluting the Desktop."*

This change appears intentional and is documented in
`BACKUP_DECOUPLE_REPORT_2026-04-18.md` in this folder. The scheduled task's
description and success criterion (*"a new dated folder appears in
`~/Desktop/REX_Backups/`"*) were never updated to match. **That folder will
never be written to by this script — by design.**

> Note: I did **not** redirect the backup to `~/Desktop/REX_Backups/` to satisfy
> the stale description. Doing so would directly undo the documented operator
> decision to keep backups off the Desktop. The script was also left unmodified.

---

## What you need to do

1. **Plug in the Cartoons external drive.** When it is unmounted, the script is
   designed to fail rather than back up anywhere else. The drive has likely been
   disconnected since around 2026-04-20, which is why backups stopped.
2. **Move the schedule onto the Mac.** This sandboxed scheduled task cannot reach
   `/Volumes/Cartoons`. Re-create the daily job as a macOS `launchd`/`cron` entry
   so it runs locally with the drive attached.
3. **Fix the task definition.** Update the `rex-daily-backup` task description and
   success criteria to reflect the real target (`/Volumes/Cartoons/REX_Backups/`)
   so future runs are not judged against an impossible criterion.
4. **Investigate the 32-day gap.** `.last_backup` = `2026-04-20_07-42`. Confirm
   no snapshots were missed that you cannot afford to lose, and run the script
   manually once (right-click → Open) with the drive connected to catch up.

---

## What was NOT changed

No files in REX were modified. The backup script was not edited. No backup
folder was created anywhere. `.last_backup` was left untouched. This run was
read-only apart from writing this report.
