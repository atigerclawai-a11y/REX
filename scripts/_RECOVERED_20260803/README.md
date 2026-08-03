# RECOVERED REFERENCE MATERIAL — REX/scripts/ deletion 2026-08-03 (~05:01 EDT)

**READ THIS FIRST.** These files are REFERENCE ONLY. They are NOT deployed and
NOT drop-in replacements. Do NOT copy any `.strings.txt` content into a live
script without Kato's review.

## What happened
`~/Desktop/REX/scripts/` was emptied on 2026-08-03 between ~05:01 and 05:30 EDT
(scripts dir mtime 05:01; Active Learning cron last successful run 05:00:49,
first failure 05:30:54). 11 `.py` files deleted, only `__pycache__/` survived.
No source copy exists anywhere: not in git (files were untracked), not in
`~/Desktop/REX_Backups/CC_daily_*` (last snapshot Jul 20, no scripts/ dir), not
in `~/CC_archive/`, Trash, Time Machine, or the Office Mac. Culprit process
unidentified (05:01 also created empty `GOJ_Backups/GOJ_2026-05-*` skeleton
dirs, `REX/REX_Backups/`, `CC_backups/`, `.omh/`, `_archive/old_logs`).

## Files here
- `*.pyc` — original bytecode copies from `scripts/__pycache__/` (cpython-311),
  preserved for future decompiler tooling.
- `*.strings.txt` — docstring + string constants extracted from each pyc via
  Python `marshal` (the only reliable extraction; pycdc/pycdas fail on 3.11
  opcode 221 `POP_JUMP_FORWARD_IF_NOT_NONE`).

## Deleted scripts (from pycache manifest) + purpose (from docstrings)
| Script | Purpose (docstring) | Impact |
|--------|--------------------|--------|
| active_learning.py | (no pyc — never cached; ran 05:00:49) | Cron 61e7b59530b0 PAUSED by Blue #191 |
| kitchen_pm_log.py | Morning +/- log vs yesterday's sheets + dish deltas; emails Kato | Cron 2399d5f0322f PAUSED by Blue #191 |
| write_blank_picks.py | Write BLANK-form extractions into client_menus ('write-in' picks) | ⚠️ subprocess'd by 6 pipeline scripts (CC_menu_sweep, CC_surya_completion_chain, CC_week30_finalize, CC_tuesday_finalize, CC_week30_completion_chain, completion_chain) — LATENT breakage |
| focr_recover_quarantine.py | focr recovery for quarantined menu docs (doc006808/809), page-count throttle | Runner PID 43161 alive from memory; future runs blocked |
| cloud_menu_read.py | Cloud vision menu reader — selective escalation for cost control | Consensus pipeline (surya vs cloud) |
| consensus_apply.py | Consensus layer: surya vs cloud agree->auto-accept, disagree->review | Consensus pipeline |
| drain_quarantine.py | Drain menu_quarantine: re-validate with fixed contracts, canonicalize | Quarantine pipeline |
| focr_reader.py | focr (Unlimited-OCR) local second-opinion reader for consensus | Consensus pipeline |
| menu_contracts.py | Write-time contract gate for client_menus | Menu writes |
| pre_generation_gate.py | PRE-GENERATION GATE before menu-sheet generation | Menu generation |
| test_focr_throttle.py | Synthetic proof: focr_recover_quarantine page-count throttle (OBJ-024) | Test only |

## Restored (NOT from this dir)
- `~/Desktop/REX/CC_carecenta_auth_sync.py` — restored 2026-08-03 08:45 EDT from
  `~/.hermes/scripts/CC_carecenta_auth_sync.py` (byte-identical, sha256
  `3f7eb88a...`). Fixes work cron 678426d4d2c8 (Carecenta Auth Sync nightly).

— Blue Team cycle #191, 2026-08-03
