# GOJ 3 PM Sign-In + Driver Run — Status Report

**Run timestamp:** 2026-05-12 (Tuesday) 3 PM
**Target business day:** Wednesday, May 13, 2026 (day code W)

## Generation — SUCCESS

Both sign-in sheets and driver lists generated cleanly using `generate_tomorrow.py`.

| File | Bytes | Notes |
|---|---|---|
| `GOJ_SignIn_Wednesday_2026-05-13_S1.pdf` | 12,440 | 90 clients, alphabetical |
| `GOJ_SignIn_Wednesday_2026-05-13_S2.pdf` | 14,967 | 90 clients, alphabetical (S2 sign-in includes all scheduled, even with no menu order) |
| `GOJ_Drivers_Wednesday_2026-05-13_S1.pdf` | 16,930 | 9 driver pages |
| `GOJ_Drivers_Wednesday_2026-05-13_S2.pdf` | 16,102 | 9 driver pages |

PDFs were copied to `~/Desktop/REX/` so they're accessible if Telegram delivery fails, and to `~/Desktop/REX/scheduled_handoffs/2026-05-12_signin_driver/` as the archived handoff bundle.

## Counts (used for Telegram summary)

- Clients expected (from `GOJ_Master_Routes.json` W1+W2, active only): **166** (Shift 1: 90 | Shift 2: 76)
- Drivers on duty: **7** (Alisher, Andrey, Gena, Oleg, Ravil, Vadik, Valera)
  - Combos `Andrey/Gena` and `Oleg/Vadik` split into individuals; `CAR_SERVICE` and `(unassigned)` excluded.

> Note: S2 sign-in PDF lists 90 clients because the generator reports all S2-scheduled clients on the sign-in (even those without a menu order). The route file W2 has 76 active route entries — that is the operational client count used for the Telegram summary above. If the operational definition should match the sign-in count, switch to the generator's emitted client count instead.

## Telegram delivery — FAILED (network block)

`api.telegram.org` is **not on the network allowlist** for this scheduled task's sandbox.
The egress proxy returned `403 Forbidden` (`X-Proxy-Error: blocked-by-allowlist`) for every attempt.

### To fix
Add `api.telegram.org` to **Settings → Capabilities → Network allowlist** so future 3 PM runs can deliver to Rexxie. Once added, the next scheduled run will succeed automatically. Same block was reported on the May 8 run report — this remains unresolved.

## Message that would have been sent

```
🚗 GOJ Sheets for Wednesday, 2026-05-13

👥 Clients expected: 166
  Shift 1: 90 | Shift 2: 76
🚌 Drivers on duty: 7

📋 Sign-in sheet and driver lists attached below.
```

Followed by 4 PDF uploads (S1 sign-in, S2 sign-in, S1 drivers, S2 drivers).

## What ran

1. Symlinked the canonical paths the script expects:
   - `~/Documents/goj files/dashboard` → `~/Desktop/REX/...mnt/dashboard` (for `auth_tracker.db` location)
   - `~/Documents/goj files/data` → dashboard/data (for `GOJ_Master_Routes.json` / `GOJ_Menu_Orders.json`)
   - Additionally created `<mnt>/data` symlink because `Path(__file__).resolve()` in this sandbox places `BASE_DIR` at `<mnt>/` (the script's parent.parent after resolving symlinks).
2. `cd ~/Documents/goj\ files/dashboard && python3 generate_tomorrow.py --day tomorrow --mode signin` → 2 PDFs
3. `cd ~/Documents/goj\ files/dashboard && python3 generate_tomorrow.py --day tomorrow --mode drivers` → 2 PDFs
4. Computed client + driver counts directly from `GOJ_Master_Routes.json` (W1 + W2).
5. Attempted Telegram delivery — blocked by allowlist (403). No fallback templates needed because populated PDFs generated successfully.
6. Copied all 4 PDFs to `~/Desktop/REX/` with date-stamped names AND to `~/Desktop/REX/scheduled_handoffs/2026-05-12_signin_driver/` with the generator's native names.

## Files dropped

- `~/Desktop/REX/GOJ_SignIn_Wednesday_2026-05-13_S1.pdf`
- `~/Desktop/REX/GOJ_SignIn_Wednesday_2026-05-13_S2.pdf`
- `~/Desktop/REX/GOJ_Drivers_Wednesday_2026-05-13_S1.pdf`
- `~/Desktop/REX/GOJ_Drivers_Wednesday_2026-05-13_S2.pdf`
- `~/Desktop/REX/scheduled_handoffs/2026-05-12_signin_driver/` (handoff bundle, generator-native filenames)

To send the queued sheets manually from your Mac:

```
cd ~/Desktop/REX
python3 send_signin_driver_3pm.py   # edit the file references to today's PDFs first
```

…or just drop the PDFs into your Telegram chat with Rexxie directly.

## Generator notes

- Both `--mode signin` and `--mode drivers` emitted clean PDFs.
- `--mode drivers` logged 4× "Unknown driver '(unassigned)' — consider adding to DRIVER_NAME_MAP". Non-fatal but indicates a few route rows on W1/W2 still have `driver: "(unassigned)"`.
- Generator logged many `[propagation] ... scheduled S2 2026-05-13 but no menu order` info messages for W2 — expected when menu data isn't loaded for tomorrow yet; these clients still appear on the sign-in (correct), and they're filtered off any future distribution/kitchen sheet (correct).
