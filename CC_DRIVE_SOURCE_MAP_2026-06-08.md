# GOJ Drive — Definitive Source Map
**Compiled 2026-06-08 — replaces the stale `WATCH_FOLDER_ID = '1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB'` (akhiger archive, last touched March)**

## The agent was watching the wrong folder

Until today, `CC_transition_drive_watcher.py` and `CC_transition_drive_hook.py` both pointed at the old `akhiger@gmail.com` GOJ Operations folder. That folder has been frozen since March (akhiger = Allen, departed). All current bookkeeper/staff work is in *new* files owned by Yelena Postolova, Naumka, Vlad Khiger, and Sweetlana — shared with `atigerclawai@gmail.com` directly (not via folder), which is why `parents:[]` and the agent saw nothing new.

## LIVE files (modified daily — must be the primary ingestion sources)

| File ID | Name | Owner | Schema |
|---------|------|-------|--------|
| `1ko7aVBhzLMngCuWmIZuCC5eT6WwvNEUiS8Q0vF92oy8` | **SIGN IN** | yelenapostolova@gmail.com | Master client roster — 27 tabs; the `sign in` tab has 414 client rows with columns `Name, plan, [V], TR/F, Table, change`. Day-tabs (M1/M2/T1/...) are stub cells. **DO NOT parse day tabs — parse `sign in` only.** |
| `1XQMusZ0-rPx50QDrpf92l1mgEZdHRvmnGwpB9-moSwQ` | **Attendance tracking** | yelenapostolova@gmail.com | Monthly absentee log — 7 tabs (Jun/May/Apr/Mar/Feb/Jan/Dec). Each row: `M/D Day, Nth shift минус` header followed by absent names + reasons (e.g. `Brodskaya Lidiya · sick Alisher`). This is the live attendance source. |
| `1giUlw82mlFFfMZOvcZWqBtyB5vNntKliAamQRWzV0IE` | **Calendar 2026** | naumka@gmail.com | Annual schedule calendar — populated through Dec 2026. |
| `1IfBJbKleeqA329FI3WeoFQp2xqmKYRJiy_I7RC2ZBcw` | **2026 First shift Menu.xlsx** | yelenapostolova@gmail.com | First shift daily menu — Excel format, weekly. |
| `18rs4xZHmdjt78za9tsh1bse94q-9Vn-pKXcnjID3ER0` | **2026 Second Shift Menu** | yelenapostolova@gmail.com | Second shift daily menu — Google Sheets. |

## LIVE folders (authorizations + employee records, modified weekly)

| Folder ID | Name | Owner | Contents |
|-----------|------|-------|----------|
| `14AVRfWJH9aAuvHec0dRoZ3DgP6MWNJJt` | **CARECENTA** | sweetlanagoj@gmail.com | Authorization PDFs uploaded by vkhiger — 20+ PDFs in last 2 weeks (DMITRIEVA, POLOVITSKAYA, YUSUPOV, KORMOV, PEREPELITSA, MELNYK, UMANSKAYA, KHOVAN, VARTANYAN, KRIVCHENOK, LURYE, KATERSKAYA, CHERNAYASELITSER, …). Files are name + expiry date + visit/transport type. |
| `1SZzHuL1PYI2M39gCxoEZrcDj6s8Be8A9` | **new auth** | sweetlanagoj@gmail.com | Newer authorizations (separate intake bucket). |
| `1BZTYJjoJH0tY8_BlGaRQXsVcjKNb4qGM` | **employee files** | vkhiger@gmail.com | 17 employee subfolders (Khiger Allen, larry lember, Aleev Ravil, Imomberdiev Alisher, Altman Natalie, Sturovska Olena, Tikhonov Oleg, Klimova Inessa, Zhuk Lyudmila, Ortomotsadze Valerian, Gugilov Gennadiy, sheremet andrey, Rozmetaniuk svitlana, kononenko vadim, EMPLOYEE DUE) + master HR docs. |

## STATIC / ARCHIVED (do not ingest as live — kept for forensics only)

| Folder ID | Name | Owner | Why |
|-----------|------|-------|-----|
| `1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB` | GOJ Operations | akhiger@gmail.com | Old bookkeeper's archive — frozen March 2026 |
| `1pqoHtLSiC_Zk492fd1BlUfvJq9Uetc5L` | medicals and cpr | akhiger@gmail.com | April archive, no new uploads |
| `18c5CcZDnykRJ7VjgaNXHdL0edFLcXNW8` | Khiger Vlad | vkhiger@gmail.com | Single-employee folder, last touched May |
| `1Le11D6p4OAa8UcHh15xUwHI7Ia6B5KKc` | Source | naumka@gmail.com | Code repo (Sign-AppScript, garden-of-joy-sign.github.io) — not data |

## What's NOT in Drive (must be sourced elsewhere)

- **Driver routes by day** — *generated* by `~/.hermes-cloud/scripts/goj_generate.py` (cron `ad2dea0e7ac8` at 2:30 PM) from `client_schedule` in `goj_proprietary.db`. Not maintained in Drive.
- **Kitchen counts by day** — also generated from `client_menus` + `client_schedule`.
- **Sign-in sheets PDF** — generated; the *input* is the SIGN IN spreadsheet above.

## Dashboard write targets

Ingestion writes into `~/Documents/goj files/dashboard/auth_tracker.db`:

| Source | Dashboard table | Mapping |
|--------|-----------------|---------|
| SIGN IN `sign in` tab | `clients` | Name → clients.name · plan → clients.plan_raw + plan_canonical · TR/F → clients.transportation |
| Attendance tracking monthly tabs | `attendance_log` | Parse `M/D Day, Nth shift минус` headers + absentee rows → rows with `log_date, shift, client_name, status='absent', reason` |
| 2026 First/Second Shift Menu | `client_menus` (column `main`, NOT `main_dish`) | Per day per shift → menu items |
| Calendar 2026 | `client_schedule` (in proprietary DB) | Cross-checks against existing Observer/Mirror cron output |
| CARECENTA + new auth PDFs | `authorization` | OCR PDFs → client_name, service_start_date, service_end_date, payer_raw, status |
