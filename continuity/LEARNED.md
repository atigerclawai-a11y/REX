# LEARNED
# GOJ Continuity Loop — permanent append-only record of durable learning.
# NEVER rewritten. New entries append at the bottom with a date heading.
# Rule: learning counts as carried only if it's encoded somewhere durable.
# A name ruling in a chat transcript is gone at midnight.

## 2026-08-03
- ENCODED: Canonical 4-digit client ID (0425-1304) = PERMANENT identity — auth_tracker.canonical_ids is the source of truth; QR payload carries the same ID; guard = scripts/canonical_id_guard.py (wired into page-guard chain step 3).
- ENCODED: Attendance truth = LIVE Carecenta portal ONLY (dashboard EXPECTED TODAY + sign-in page). ghs_schedule.db is the recurring TEMPLATE and overcounts (~110/55 vs live 82/71) — RETIRED as a source of truth. Only clients physically scheduled that day count.
- ENCODED: Sheet chain (one source, matching counts): CC_menu_fill.py <date> → plate_completion_pass.py → bridge_menu_orders.py <date> → generate_tomorrow.py --day X --mode all --skip-preflight (MUST use ~/Documents/goj files/dashboard/ copy — goj_corpus copy lacks the flag).
- ENCODED: Union roster REMOVED from generate_tomorrow.py — only day_*_actual (synced from live portal) clients print. Base-scheduled "considered-a-menu" union superseded 2026-08-03.
- ENCODED: QR placement FINAL — bottom-right footer, draw_qr(PAGE_W-MARGIN_X-2, MARGIN_BOTTOM+2, 36), row floor 22, reserve BOTTOM_Y+56. Top-right blocked ПТ header; 36pt decodes at 200dpi (30pt needs 300dpi).
- ENCODED: Blank menus are generated ONE PDF PER DAY+SHIFT (Menus_<Day>_<Date>_S1/S2_LIVE.pdf) — not a combined stack (Kato 2026-08-03).
- LOOSE: Carecenta sign-in page stores some client names ALL-LOWERCASE (gadilova nina, rukhlevich svetlana, solovyeva Svetlana). ANY name-counting regex must be case-insensitive or it silently undercounts — this bug made me report 71 instead of 72 (Mon PM) and miss clients twice today.
- LOOSE: Carecenta sign-in page lists MORE than the dashboard EXPECTED count — not-authorized clients (Marder Yakov Mon AM; Kramer Sofya + Magalnik Malvina Tue AM) appear on the sign-in list but NOT in EXPECTED. Dashboard EXPECTED = the truth. Cross-check not-authorized list (5 clients) when reconciling.
- LOOSE: plate_completion_pass.py referenced in the law does NOT exist on disk (~/Desktop/REX/scripts/) — CC_menu_fill.py's fallback chain covers empty plates (house_standard). Verify before trusting the law's step list.
- LOOSE: generate_tomorrow.py --mode kitchen is NOT a valid mode (modes: all|signin|drivers|distribution) — kitchen ships with --mode all.
- LOOSE: build_personalized_menus.py render_one_client(c, name, id, week) takes the canvas as FIRST arg and uses plain `import build_personalized_menus` (importlib exec breaks the module-global canvas).
- LOOSE: The 26pt row floor in build_personalized_menus pushed the food grid INTO the QR band — lowered to 22 + reserve BOTTOM_Y+56. Vision-verify QR clearance after any row-height change.

## 2026-08-03

## 2026-08-03
- ENCODED: Canonical ID permanence → auth_tracker.canonical_ids + canonical_id_guard.py (chain step 3)
- ENCODED: Live-Carecenta attendance truth → goj-signin-canonical-template skill
- ENCODED: Sheet chain (one source) → GOJ_CANONICAL_LAW.md Article IV
- ENCODED: QR bottom-right 36pt + row floor 22 → goj-ocr-canonical-build skill
- ENCODED: Shift-split menu generation → goj-ocr-canonical-build skill
- LOOSE: sync_proprietary_db.py compared TOTAL rows only — per-source_sheet compare now (Aug 6 drift caught by loop)
- LOOSE: Carecenta sign-in page has all-lowercase names — count case-insensitively
- LOOSE: Not-authorized clients appear on sign-in list but not in dashboard EXPECTED

## 2026-08-03
- ENCODED: Canonical ID permanence → auth_tracker.canonical_ids + canonical_id_guard.py (chain step 3)
- ENCODED: Live-Carecenta attendance truth → goj-signin-canonical-template skill
- ENCODED: Sheet chain (one source) → GOJ_CANONICAL_LAW.md Article IV
- ENCODED: QR bottom-right 36pt + row floor 22 → goj-ocr-canonical-build skill
- ENCODED: Shift-split menu generation → goj-ocr-canonical-build skill
- LOOSE: sync_proprietary_db.py compared TOTAL rows only — per-source_sheet compare now (Aug 6 drift caught by loop)
- LOOSE: Carecenta sign-in page has all-lowercase names — count case-insensitively
- LOOSE: Not-authorized clients appear on sign-in list but not in dashboard EXPECTED

## 2026-08-03
- ENCODED: 10 wiped scripts rebuilt 2026-08-03 from pyc/strings/skills — ALL verified against live data (see deleted-script-recovery skill table)
- ENCODED: scripts/ now git-tracked (commit d1f000f) + CC_daily_backup.sh fixed to include scripts/ subdir (was excluded by rsync whitelist → unrecoverable)
- LOOSE: focr CLI = `focr ocr --json <img>` (NO 'html' subcommand); marks = √ vs □; typos Винеррет/Квашеняя must map to catalog
- LOOSE: Time Machine verified dead-end — registered APFS dest unplugged (UUID DCB2BDEA not mounted), sparsebundle on cartoons = empty HFS relic (Jul 15), zero APFS snapshots
- LOOSE: consensus_apply.py = same script as consensus_hook.py (renamed) — rebuilt once as consensus_hook
