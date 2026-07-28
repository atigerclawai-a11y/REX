# GOJ Next-Day Handoff — Scheduled Run Report

**Run:** Friday, May 22, 2026, 10:00 AM (scheduled task `goj-10am-next-day-handoff`)
**Target operating day:** Monday, May 25, 2026 (next business day — Fri → Monday rule)

## Outcome: Kitchen & distribution sheets NOT produced — no menu data

The sheet generator ran successfully (exit code 0) but produced **only sign-in and
driver sheets**. Kitchen and distribution sheets require menu orders, and the system
has **0 menu orders on file for the week of May 25**.

## What ran

- Command: `python3 generate_tomorrow.py --day Monday --mode all`
  (Used `--day Monday`, not `--day tomorrow`: on a Friday the script's "tomorrow"
  resolves to Sunday May 24 because it only skips Saturday. The task's next-business-day
  rule is Fri → Monday, so Monday May 25 was generated.)
- Generated: `GOJ_M_S1_Monday_signin.pdf`, `GOJ_M_S1_Monday_drivers.pdf`,
  `GOJ_M_S2_Monday_signin.pdf`, `GOJ_M_S2_Monday_drivers.pdf`
- NOT generated: kitchen + distribution PDFs (no menu orders)
- The database was copied for the run; the live `auth_tracker.db` was not modified.

## Monday May 25 clients

- Shift 1: 81 scheduled | Shift 2: 69 scheduled | **Total: 150**
- Menu orders on file: **0 of 150**
- `dietary_notes` field: empty for all 395 active clients (unused column — not a
  usable menu-data indicator)

## Root cause

The menu OCR pipeline is broken. Every `ocr_jobs` run since May 19 fails with
`'str' object has no attribute 'name'`. The last menu week ingested into
`client_menus` was the week of May 4 — weeks of May 11, 18, and 25 are all missing.
`GOJ_Menu_Orders.json` (which the generator reads) is empty `{}`.

## The menu data exists — it just was not processed

Filled-out menus arrived by email. Allen Khiger forwarded "Filled out menus for week
of may 18-25" on May 19, with two scanned PDFs (originally scanned May 15):
- `doc00410720260515113734.pdf`
- `doc00414820260515152241.pdf`

## To produce Monday's kitchen/distribution sheets

1. Fix the menu OCR worker (`'str' object has no attribute 'name'`).
2. Ingest the two menu PDFs into `client_menus` / `GOJ_Menu_Orders.json`.
3. Re-run: `cd ~/Documents/goj files/dashboard && python3 generate_tomorrow.py --day Monday --mode all`

## Notification

A Telegram alert with the above summary was sent to the owner chat (Rexxie/Hermie
bot, chat 5587703834) — delivered OK, message_id 7449. No PDF attachments were sent
(none of the kitchen/distribution sheets exist). Sign-in + driver sheets were not
sent, per the task (those go out at 3 PM).
