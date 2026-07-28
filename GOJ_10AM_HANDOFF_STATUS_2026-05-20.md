# GOJ 10 AM Handoff — Status for Wednesday, May 20, 2026

Run time: 2026-05-19 14:00 UTC (scheduled-task `goj-10am-next-day-handoff`)

## Headline

**No kitchen or distribution PDFs were generated, and the Telegram summary could not be delivered.**

- `generate_tomorrow.py --day tomorrow --mode all` ran successfully but emitted only sign-in and driver PDFs because **`GOJ_Menu_Orders.json` is empty** (`{}`) for 2026-05-20. Per the script's own logic, kitchen + distribution sheets are only drawn when `menu_clients` is non-empty (lines 1245 / 1252 of `generate_tomorrow.py`).
- The Telegram summary was not delivered because **`api.telegram.org` is unreachable from this sandbox** — the HTTP proxy returns 403 on CONNECT and the SOCKS5 paths reject the connection.

## What the data shows

Wednesday 2026-05-20 schedule (from `generate_tomorrow.py` propagation):

- **Shift 1:** 76 scheduled, 0 menu orders
- **Shift 2:** 90 scheduled, 0 menu orders
- **Total:** 166 expected clients

Menu data on file (`auth_tracker.db` → `clients.dietary_notes`):

- ✅ With dietary notes: **0**
- ❌ Missing: **166**

Menus for tomorrow should have arrived 6–14 days ago (i.e. between May 5 and May 13). No scanned menus have been ingested into `GOJ_Menu_Orders.json` for that window.

## What was produced anyway

The "all" mode generated these into `~/Documents/goj files/output_docs/`:

- `GOJ_W_S1_Wednesday_signin.pdf` (12 KB)
- `GOJ_W_S1_Wednesday_drivers.pdf` (17 KB)
- `GOJ_W_S2_Wednesday_signin.pdf` (15 KB)
- `GOJ_W_S2_Wednesday_drivers.pdf` (16 KB)

Per the 10 AM task's own constraints, these are **not** sent at 10 AM — sign-in and driver sheets are scheduled for the 3 PM handoff.

## Suggested message body (if you want to forward to Telegram manually)

```
🍽 GOJ Kitchen & Distribution Sheets — Wednesday, May 20, 2026

Clients expected: 166 (Shift 1: 76 | Shift 2: 90)
✅ Menu data on file: 0 | ❌ Missing: 166

⚠️ No kitchen or distribution PDFs produced.
GOJ_Menu_Orders.json has no entries for 2026-05-20, so the
generator emitted only sign-in + driver sheets (held back per
3 PM schedule).

Menus for tomorrow should have arrived ~6–14 days ago — please
confirm scans were processed.

ℹ️ Sign-in + driver sheets will follow at 3 PM.
```

## Action items

1. **Check menu intake for the week of May 13–18.** Either the menu PDFs were never emailed, never OCR'd, or `GOJ_Menu_Orders.json` was reset and not repopulated.
2. **Telegram delivery from scheduled tasks.** The sandbox the scheduled task runs in cannot reach `api.telegram.org`. Either the task needs to run on the host directly (e.g. via the dashboard scripts as a cron), or the bot endpoint needs to be added to the sandbox proxy allowlist, or Telegram delivery needs to move to a connected MCP.
3. **Path patch (cosmetic).** `generate_tomorrow.py` resolves `CANONICAL_DB_PATH` from `Path.home()` and `BASE_DIR` from `__file__`. In the sandbox those resolved to `/sessions/optimistic-sweet-hopper/...` and didn't match the on-disk layout until symlinks were added (`~/Documents/goj files/dashboard → ~/mnt/dashboard`, `~/mnt/data → ~/mnt/dashboard/data`). On the real Mac this is fine, but worth knowing if you ever invoke it from a non-home cwd.
