# ⚖️ GOJ CANONICAL LAW — The July 31 Build Constitution

> **Status: SUPREME LAW of the GOJ meal-OCR system. Ratified 2026-08-03 by Kato.**
> This document is the single source of truth for how the Garden of Joy meal-ordering
> pipeline operates. Every agent, script, cron, and document generator is subordinate
> to it. Where any other file, memory, or skill conflicts with this law, THIS LAW WINS.
>
> **Read this first. Then `GOJ_WEEK31_HANDOFF.md` (operational state). Then the skill
> `goj-ocr-canonical-build` (implementation detail).**

---

## PREAMBLE — What the Build Is

The July 31 build is the **complete, proven, production pipeline** that takes scanned
menu forms from GOJ's ~422 elderly Russian-speaking clients and turns them into the
working files staff need: **sign-in sheets, kitchen prep orders, distribution sheets,
and driver routes** — with every client's meal correct, every plate accounted for, and
every client identified by a **permanent 4-digit ID + QR code** that never changes and
never mixes with another.

It was built through three weeks of incidents (each one cost a real operational failure)
and reached **99% own-food accuracy** (provenance audit, Friday July 31: 2 true gaps out
of ~230). It is finished. **It is not to be re-architected, re-laid-out, or "improved"
without a written, approved amendment.** The law exists so the build can never regress.

---

## ARTICLE I — THE CANONICAL STACK (Engine Ladder)

| Tier | Engine | Role | When |
|---|---|---|---|
| 0 | **MinerU 3.4.0** | PRE-PROCESS + classification input ONLY (never the reader) | every new doc, sweep step 1 |
| 1 | **surya** | Primary reader for blank checkbox forms (volume) | default extraction |
| 2 | **focr 0.7.2** (baidu/Unlimited-OCR) | Second opinion: handwriting + checkmarks | hard pages, recovery |
| 3 | **Cloud** (Anthropic haiku / Gemini flash) | LAST RESORT on dead pages | only when 1+2 fail |
| 4 | **DeepSeek** | Text arbiter — picks best answer | multi-engine disagreements |
| 5 | **DIRECT VISION** (Claude vision on page images) | THE most reliable reader for unreadable docs | blue-ink marks, hallucinated cloud output |

**Law 1.1 — Order is absolute.** surya → focr → cloud → vision. Never skip a tier.
**Law 1.2 — Cloud output is NEVER trusted unverified.** Cloud hallucinated names
("Логарифм") and categories. Cloud results apply only after roster cross-check + vision
verification. **Cloud NEVER supersedes primary extraction by file mtime.**
**Law 1.3 — Vision-verified is the gold standard.** Any pick that is new, changed, or
engine-disagreed requires direct-vision verification before writing as `ocr_scan`.

---

## ARTICLE II — THE INTAKE CHAIN (Crons — the "always-on" law)

| Cron | Name | Cadence | Role |
|---|---|---|---|
| `5035221135ce` | Email Intake | 3m | Gmail → attachments → intake dirs |
| `bec587307624` | Folder Poller | 2m | scans/ → pipeline |
| `9d5b6bcfdc70` | Menu Sweep | 15m | MinerU → classify → surya → apply |
| `3d84c4facde3` | Surya watchdog | 10m | self-healing relaunch |
| `7be4a65ac889` | Consensus hook | 10m | surya→focr→cloud, budget 3/run |
| `e89a6d1b2167` | Review queue → Telegram | 10m | unmatched → Kato |
| `61e7b59530b0` | Active learning | 30m | corrections → alias map |
| `391db3466288` | Surya progress | 30m | numbers-only report |
| `4132e4a0f3a6` | Promoter | 15m | extraction → ocr_scan (QR-first) |
| `76ee77ea251f` | Page Guard | 15m | census every doc, auto-recover |
| `6280548b2551` | Page census digest | daily 06:00 | all-pages-accounted proof |
| `55014efee464` | Sign-In Attendance Bridge | 15m | attendance after menus |

**Law 2.1 — The chain must be resumed each week.** Crons do NOT auto-resume between
food weeks. Paused = 75%+ fallback plates.
**Law 2.2 — Surya survival config is mandatory:**
`SURYA_INFERENCE_PARALLEL=1 SURYA_INFERENCE_CTX_SIZE=16384`. The default
(98K ctx × 8 parallel) jetsam-kills the Mac.
**Law 2.3 — Page guard is the "every page always is OCR'd" guarantee.** No scanned page
is ever silently dropped. pdfinfo pages ÷ 2 vs forms extracted; gaps flag → recover.

---

## ARTICLE III — THE GUARDS (Each caught a real incident)

| Guard | Script | When | Incident it caught |
|---|---|---|---|
| **Page census** | `page_census.py` | every intake | 24 never-read end-of-batch pages |
| **Plate completion** | `plate_completion_pass.py` | **MANDATORY before EVERY generation** | clients printed with NO food |
| **Provenance audit** | `provenance_audit.py` | the scorecard | quote class E (TRUE GAP), never raw fallback |
| **Multi-engine** | `multi_engine_read.py` | every problem page | engine disagreements |
| **Canonical ID guard** | `canonical_id_guard.py` | 15-min cron + after any ID change | duplicate/mixed IDs |

**Law 3.1 — Never generate sheets without plate completion.** It fills empty cells from
own history → house standard. Zero empty plates is a hard invariant.
**Law 3.2 — The scorecard is provenance.** ≥95% own-food is the bar. Quote class E
(no form, no history) — never the raw fallback count. Kato's facility numbers are
calibration truth: if he says "should be ~945," hunt what the pipeline missed. Never
defend the system's count.

---

## ARTICLE IV — THE SHEET LAW (One source, matching counts)

**The one-source chain (proven Friday July 31):**
```
CC_menu_fill.py <date>          → fallbacks, 100% coverage (ocr→day_shifted→last_order→house)
plate_completion_pass.py        → zero empty plates
bridge_menu_orders.py <date>    → writes ~/Documents/goj files/data/GOJ_Menu_Orders.json
generate_tomorrow.py --day X --mode all --skip-preflight   → ALL sheets from ONE source
```

**Law 4.1 — One generator, one source.** Sign-in, kitchen, distribution, drivers must
come from the SAME `generate_tomorrow.py --mode all` run. Building sheets from different
generators/sources produces mismatched counts (the Aug 3 failure: 83/71 vs 99/52 vs 111/55).
**Law 4.2 — The generator copy.** Use `~/Documents/goj files/dashboard/generate_tomorrow.py`
(has `--skip-preflight` + `canonical_id_for()`). The goj_corpus copy lacks both — NEVER use it.
**Law 4.3 — Day names, not ISO.** `--day Monday|Tuesday|...` — NOT `--day 2026-08-03`.
**Law 4.4 — Templates NEVER re-laid-out.** Kitchen = SALADS→SOUPS→MAIN+SIDE COMBOS, no
row caps, overflow paginates. Sign-in keeps Time Out column. Three rejected rebuilds
stand as precedent.
**Law 4.5 — Every client has a plate.** If a client has no menu order, use their fallback
(last real order → house standard). Never drop a client from the sheets.

---

## ARTICLE V — THE PERMANENT 4-DIGIT ID + QR (Identity Law)

**The 4-digit client ID is each member's PERMANENT identifier — it never changes, never
alters, never mixes with another.**

**Law 5.1 — Source of truth:** `auth_tracker.db canonical_ids` (canonical_id TEXT PK,
name, auth_id, prop_id). 422 active clients, IDs **0425–1304**, 0 duplicates, 0 gaps.
**Law 5.2 — QR payload = same ID:** `goj:cid=0425|w=<ISO>|n=<name>`. QR and printed
`[ID 0425]` MUST agree. When a returned form's QR decodes, the ID is authoritative —
**no name matching, no unmatched queue.**
**Law 5.3 — Printed on EVERY attendance touchpoint:**
- Blank menus: QR (bottom-right footer, 36pt, 200dpi-decodable) + `Name [ID]` in footer
- Sign-in sheets: `Name [ID]` · Distribution: `Name [ID]` · Driver routes: `Name [ID]`
**Law 5.4 — Zero mixing is audited.** Every printed name↔ID pair must match the canonical
table. Verified 830/830 pairs (2026-08-03). The guard (`canonical_id_guard.py`) fails
loud on any duplicate/missing/mismatch.
**Law 5.5 — QR placement is fixed law:** bottom-right corner within margins,
`draw_qr(c, payload, PAGE_W - MARGIN_X - 2, MARGIN_BOTTOM + 2, 36)`. Top-right placement
blocked the ПТ column header — rejected.

---

## ARTICLE VI — THE NON-NEGOTIABLE RULES (each cost a real incident)

1. **DUAL-DB WRITES**: write to BOTH `/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db`
   AND `/Users/mainsobhelper/Desktop/REX/goj_proprietary.db`. The REX→Documents sync cron
   (5m) clobbers single-DB writes (real rollback 7/29).
2. **Unmatched names → Kato immediately. Never silent fuzzy.** (Pako Mayya, Streltsova
   Nadiia, Hohal Raisa — all real clients with picks.)
3. **Never quote DB numbers without verifying LIVE — and NEVER use ghs_schedule.db as source of truth (Kato 2026-08-03, permanent).** `ghs_schedule.db` holds the full recurring schedule TEMPLATE (110/55) — it overcounts by ~28 in S1 because it lists everyone scheduled *any* Monday, not who's physically scheduled TODAY. **The ONLY attendance truth is the LIVE Carecenta portal** (`https://goj.daycenta.com/`): the dashboard's EXPECTED TODAY (MORNING/AFTERNOON) and the CLIENT SIGNATURE SIGN-IN page (per-client lists). **Only clients physically scheduled for that day are counted.** Canonical sources, in order: (1) LIVE Carecenta portal — dashboard + sign-in page, (2) Google Drive sheets (SA key), (3) goj_proprietary `ocr_scan` rows, (4) auth_tracker `day_*_actual` (only after Carecenta sync). ghs_schedule.db = reference-only template, NEVER quoted for counts.
4. **Google auth law**: Gmail = IMAP ONLY (`~/.rex_gmail_imap.json`). Drive/Sheets =
   Service Account (`~/.rex_drive_service_account.json`). NEVER OAuth for Drive/Sheets.
5. **Kato's dish rule**: mains = курица/мясо/рыба only. Generic OCR words map to specific
   dishes. Unmatched → ask immediately.
6. **focr category-fix**: Гречка/Пюре/Паста/Картошка фри are SIDES — reclassify out of
   `main` on write.
7. **Mis-filed names**: the name-read is authoritative — apply to the READ name's roster
   entry, never the position's.
8. **Double-mark alternating rule**: two dishes in one category/day on multiple attended
   days → alternate A/B across weekday-sorted days. Single-day pair → serve choice A.
9. **Union roster** on all sheets: Carecenta-active ∪ base-scheduled ∪ menu-history.
   Attendance truth = `auth_tracker.db` actuals. Shift from `day_*_actual`, not `clients.shift`.
10. **Fallback chain only derives from REAL orders**: `source_sheet IN
    ('ocr_scan','drive_sync','day_shifted')` — never chain fallback onto fallback
    (the 128/154 stale-Monday incident).
11. **Week attribution from the printed footer ONLY.** Intake filename date = target week
    (+7) for emailed/handwritten. Blank forms' printed "Week N" = food week (NO +7).
    Never default a week.
12. **Terminal flaky → script files, not heredocs; cron one-shots.** pypdf reinstall
    after any venv rebuild.

---

## ARTICLE VII — AMENDMENT PROTOCOL (how the law changes)

The law is not frozen — it is governed.

1. **Any proposed change** to the stack, chain, guards, sheet law, or ID law must be
   presented to Kato **before** building (he decides, and may require a Blue Team eval).
2. **Proven fixes** (data-loss bugs, documented incidents) are ratified by patch to this
   document + the skill `goj-ocr-canonical-build` + `Hermes Perpetual Memory.md` + log.md,
   in the SAME session they land.
3. **Never "improve" what worked last week** without Kato's explicit approval. The bar
   for touching working code is a demonstrated data-loss bug — not aesthetics.
4. **/learn protocol**: after any session that overcomes an error or discovers a workflow,
   patch this law + skill the same session. Nothing rediscovered, nothing re-broken.

---

## ARTICLE VIII — VERIFICATION (proof before success)

Before claiming any day is done:
1. `page_census.py` — pages accounted, 0 orphans
2. `provenance_audit.py` — ≥95% own-food, quote class E (TRUE GAP)
3. DB parity: `SELECT source_sheet, COUNT(*) FROM client_menus WHERE menu_date BETWEEN
   '<wk>' AND '<wk>' GROUP BY 1` in BOTH DB copies
4. Spot-verify 2-3 known-truth clients (canary: Gumarova = Свекла+Борщ зеленый+Котлеты
   куриные+Жареная картошка)
5. `canonical_id_guard.py` — 0 duplicates, 0 mismatches
6. Sheet counts match across types (sign-in = kitchen = distribution ±1 union edge)
7. Cron chain enabled (Article II table)

---

## SIGNED

**Ratified by Kato (Alejandro) — 2026-08-03**
**Author: Hermes Agent (work profile)**
**Copies: this file · `~/GHS-Vault/GOJ Canonical Law.md` · Obsidian vault · GitHub (REX repo) · Perpetual Memory**

*"The build we worked so hard to complete by July 31 is law. Every page always is
OCR'd. Every client always has their order. Every ID is permanent and never mixes.
Nothing re-discovered. Nothing re-broken."*
