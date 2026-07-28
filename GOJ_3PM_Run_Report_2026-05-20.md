# GOJ 3 PM Sign-In + Driver Run — Status Report

**Run timestamp:** 2026-05-20 (Wednesday) 3 PM
**Target business day:** Thursday, May 21, 2026 (day code TH)

## Generation — SUCCESS

Both sign-in sheets and driver lists generated cleanly with `generate_tomorrow.py` (`--day tomorrow`, modes `signin` and `drivers`). All four PDFs verified — valid `%PDF` headers and expected page counts.

| File | Bytes | Pages | Notes |
|---|---|---|---|
| `GOJ_SignIn_Thursday_2026-05-21_S1.pdf` | 15,064 | 9 | 89 clients, alphabetical by last name |
| `GOJ_SignIn_Thursday_2026-05-21_S2.pdf` | 10,930 | 6 | 66 clients, alphabetical by last name |
| `GOJ_Drivers_Thursday_2026-05-21_S1.pdf` | 17,071 | 9 | 9 route pages |
| `GOJ_Drivers_Thursday_2026-05-21_S2.pdf` | 14,486 | 9 | 9 route pages |

PDFs copied to `~/Desktop/REX/` with date-stamped names, and to `~/Desktop/REX/scheduled_handoffs/2026-05-20_signin_driver/` (generator-native filenames) as an archived handoff bundle.

## Counts (for Telegram summary)

- **Clients expected: 155** — Shift 1: 89 | Shift 2: 66
  - These are the generator-emitted scheduled counts (the totals printed on the actual sign-in PDFs). This follows the convention adopted on the 2026-05-15 run, where the summary uses scheduled counts because they match the attached sheets.
  - For reference, the raw route-file counts (`GOJ_Master_Routes.json` TH1+TH2, active entries) are **145** (TH1: 90 | TH2: 55). The routes file is a transport list and runs slightly different from full scheduled attendance.
- **Drivers on duty: 7** — Alisher, Andrey, Gena, Oleg, Ravil, Vadik, Valera.
  - `CAR SERVICE` and `(UNASSIGNED)` route groups are excluded from the driver headcount. Each driver pickup is split into individuals where the route file lists combos.

## Telegram delivery — FAILED (network block)

`api.telegram.org` is **not on the network allowlist** for this scheduled task's sandbox. The egress proxy returned `403 Forbidden` (`Tunnel connection failed: 403 Forbidden`) on the connectivity check, so no message or document could be sent to Rexxie. This is the **same block reported on the 2026-05-08, 05-12, and 05-15 runs** — still unresolved.

### To fix
Add `api.telegram.org` to **Settings → Capabilities → Network allowlist**. Once added, the next scheduled 3 PM run will deliver automatically with no other changes needed.

## Message that would have been sent

```
🚗 GOJ Sheets for Thursday, May 21, 2026

👥 Clients expected: 155
  Shift 1: 89 | Shift 2: 66
🚌 Drivers on duty: 7

📋 Sign-in sheet and driver lists attached below.
```

Followed by 2 PDF uploads (sign-in, then driver lists).

## What ran

1. Determined next business day: Wednesday → Thursday, May 21, 2026.
2. Rebuilt the directory layout the generator expects inside a sandbox working dir (`HOME/Documents/goj files/dashboard/`), using a **copy** of `auth_tracker.db` (+ `-wal`/`-shm`) so database access stayed strictly read-only against the canonical file. Routes copied from `dashboard/GOJ_Master_Routes.json`.
3. `python3 generate_tomorrow.py --day tomorrow --mode signin` → 2 sign-in PDFs.
4. `python3 generate_tomorrow.py --day tomorrow --mode drivers` → 2 driver PDFs.
5. Computed client and driver counts from `GOJ_Master_Routes.json` (TH1+TH2) and the generator's emitted scheduled counts.
6. Attempted Telegram delivery — blocked by the allowlist (403). Populated PDFs generated successfully, so the blank fallback templates (`TEMPLATE_signin.pdf` / `TEMPLATE_driver.pdf`) were **not** needed.
7. Copied all 4 PDFs to `~/Desktop/REX/` with date-stamped names and to the dated handoff bundle folder.

## Files dropped

- `~/Desktop/REX/GOJ_SignIn_Thursday_2026-05-21_S1.pdf`
- `~/Desktop/REX/GOJ_SignIn_Thursday_2026-05-21_S2.pdf`
- `~/Desktop/REX/GOJ_Drivers_Thursday_2026-05-21_S1.pdf`
- `~/Desktop/REX/GOJ_Drivers_Thursday_2026-05-21_S2.pdf`
- `~/Desktop/REX/scheduled_handoffs/2026-05-20_signin_driver/` (handoff bundle, generator-native filenames)

To deliver to Rexxie manually from your Mac (which has unrestricted Telegram access), drop the four `~/Desktop/REX/GOJ_*Thursday_2026-05-21*.pdf` files straight into the Telegram chat, or run a small `sendDocument` script from the Mac.

## Generator notes

- Fonts: DejaVu TTFs are not present in the sandbox layout, so the generator fell back to Helvetica. PDFs render correctly; only the typeface differs.
- `GOJ_Menu_Orders.json` is empty, so every scheduled client logged a `[propagation] scheduled but no menu order` info line. This does not affect sign-in or driver sheets (they rely on attendance + routes only) — but kitchen/distribution sheets will be blank at the 10 AM run unless menu data is ingested first.
- `--mode drivers` logged repeated `Unknown driver '(unassigned)'` warnings: 14 rows on TH1 and 8 on TH2 still have no driver assigned in `GOJ_Master_Routes.json`. They are grouped onto an `(UNASSIGNED)` route page on each shift's driver PDF — worth assigning a driver before Thursday.
