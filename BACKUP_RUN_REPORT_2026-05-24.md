# REX Daily Backup — Scheduled Run Report

**Run timestamp:** 2026-05-24 07:02
**Task:** `rex-daily-backup` (automated, unattended)
**Outcome:** ❌ FAILED — no backup snapshot was created.

---

## Summary

The scheduled backup did **not** complete. No new dated folder was created, and
`.last_backup` was **not** updated — it still reads `2026-04-20_07-42`. The last
*successful* backup was **34 days ago**.

This is the **third consecutive documented failure**, identical to those in
`BACKUP_RUN_REPORT_2026-05-22.md` and `BACKUP_RUN_REPORT_2026-05-23.md`. The two
root causes described in those reports remain unfixed, so the job failed again
for exactly the same reasons. Backups have now been failing every day for over a
month, and none of the four recommended human actions from the previous two
reports appear to have been carried out.

Nothing was changed automatically. Fixing either root cause safely requires a
human decision (see "What you need to do").

---

## What happened (exact results)

| Attempt | Command | Exit code | Result |
|---|---|---|---|
| 1 | `bash ~/Desktop/REX/rex-backup.command` (literal, as the task specifies) | `127` | Script file not found — see Problem A |
| 2 | Same script, run from its real mounted location | `1` | "REX source not found" — see Problem A |
| 3 | Same script, source path corrected to simulate running on the Mac | `2` | "Cartoons external drive is NOT mounted" — see Problem B |

The success criterion (`exit code 0` + a new dated backup folder) was not met
under any condition.

---

## Problem A — This scheduled job runs in a sandbox, not on the Mac

The scheduled task executes `bash ~/Desktop/REX/rex-backup.command` inside an
isolated Linux environment. In that environment:

- `~` is **not** the Mac home folder. `~/Desktop/REX` resolves to a sandbox path
  that does not exist, so the script exits `127`/`1` at its first sanity check.
- There is **no `/Volumes`** at all, so the external Cartoons drive can never be
  detected — even after correcting the source path, the script exits `2`.

The REX folder itself *is* reachable (it is mounted into the sandbox), but the
script is a macOS `.command` file that must run **on the Mac**, with the external
drive attached. **As currently wired, this sandboxed scheduled job can never
perform the backup**, regardless of whether the drive is plugged in.

Running it on the Mac directly was not possible for this run either: that path
requires interactive desktop access the user must approve, and this is an
unattended scheduled run with no one present to grant it.

➡️ The backup must run *on the Mac itself* — e.g. a `launchd` agent or a `cron`
entry — not through this sandboxed scheduled task.

## Problem B — The task description no longer matches the script

The `rex-daily-backup` task definition still says the script "Backs up
~/Desktop/REX to ~/Desktop/REX_Backups/… Keeps the 14 most recent backups…" and
lists `dist/` among the exclusions.

The **actual** script on disk is the *"Cartoons external drive edition"*. It:

- Backs up to **`/Volumes/Cartoons/REX_Backups/`** — the external drive, **not**
  `~/Desktop/REX_Backups/`. That Desktop folder will never be written to by this
  script, by design.
- **Hard-fails with exit code 2** if the Cartoons drive is not mounted. The
  script header is explicit: *"NO silent fallback to Desktop. Missed runs are
  better than quietly re-polluting the Desktop."*
- Prunes by **age** (`find … -mtime +14`, snapshots older than 14 days), not by
  "keep the 14 most recent."
- Also backs up `~/.rex/` memory and verifies "governed assets" — neither is
  mentioned in the task description.
- Does **not** exclude `dist/`, despite the task description saying it does.

This change appears intentional and is documented in
`BACKUP_DECOUPLE_REPORT_2026-04-18.md`. The scheduled task's description and its
success criterion ("a new dated folder appears in `~/Desktop/REX_Backups/`")
were never updated to match, so this job is being judged against an impossible
criterion.

> The backup was **not** redirected to `~/Desktop/REX_Backups/` to satisfy the
> stale description. Doing so would directly undo the documented operator
> decision to keep backups off the Desktop. The script was left unmodified.

---

## What you need to do

These are unchanged from the 2026-05-22 and 2026-05-23 reports and are now
**34 days** overdue:

1. **Plug in the Cartoons external drive.** When it is unmounted, the script is
   designed to fail rather than back up anywhere else. The drive has likely been
   disconnected since around 2026-04-20 — the date of the last successful
   backup — which is why backups stopped.
2. **Move the schedule onto the Mac.** This sandboxed scheduled task cannot reach
   `/Volumes/Cartoons`. Re-create the daily job as a macOS `launchd`/`cron`
   entry so it runs locally with the drive attached, then run the `.command`
   file once manually (right-click → Open) to confirm it works.
3. **Fix (or retire) the `rex-daily-backup` task definition.** Update its
   description and success criteria to reflect the real target
   (`/Volumes/Cartoons/REX_Backups/`), or remove this sandboxed task entirely
   once the macOS-local job is in place, so it stops failing every night and
   generating duplicate reports.
4. **Investigate the 34-day gap.** `.last_backup` = `2026-04-20_07-42`. Confirm
   no snapshots were missed that you cannot afford to lose, and run the script
   manually once with the drive connected to catch up. The longer this runs
   unbacked-up, the larger the data-loss exposure if the Mac's internal disk
   fails.

---

## What was NOT changed

No files in REX were modified. The backup script was not edited. No backup
folder was created anywhere. `.last_backup` was left untouched
(`2026-04-20_07-42`). This run was read-only apart from writing this report.
