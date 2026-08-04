# DEAD
# GOJ Continuity Loop — append-only record of paths proven NOT to work, with reasons.
# Re-walking a proven dead end is the most expensive thing this loop prevents.

## 2026-08-03
- ghs_schedule.db as attendance truth — the recurring schedule TEMPLATE overcounts (~110/55 vs live 82/71). Only the live Carecenta portal counts. DO NOT retry.
- Union roster in generate_tomorrow.py (base-scheduled "considered-a-menu" add) — printed clients NOT on the live list. Removed. DO NOT retry.
- QR top-right placement — blocked the ПТ (Friday) column header and margin. Bottom-right footer only.
- 30pt QR at bottom-right — failed 200dpi decode (needs 300dpi). 36pt is the floor.
- plate_completion_pass.py as a separate script — does not exist; CC_menu_fill.py covers empty plates. Don't hunt for it.
- generate_tomorrow.py --mode kitchen — not a valid mode (all|signin|drivers|distribution). Kitchen ships with --mode all.
- importlib exec of build_personalized_menus.py — breaks the module-global canvas (NoneType). Use plain `import` with sys.path.
- 26pt row floor in build_personalized_menus — pushed food grid into the QR band. Floor is 22.
- Monday kitchen sheets from goj_kitchen_paired.py as the sheet of record — different query, different counts from generate_tomorrow.py. One source only (generate_tomorrow --mode all).
- cloud_menu_read / Anthropic haiku for marks — hallucinated names (Логарифм) and categories. Direct vision is the reliable last resort.
- CC_unified_sheets.py for sign-in — wrong format. Use the landscape 7-col template.
