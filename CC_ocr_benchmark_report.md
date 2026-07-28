# GOJ Menu OCR Pipeline — QC Benchmark Report
**Date:** 2026-06-18 (updated ~18:40 by Hermes autonomous QC pass)  
**Prior automated report:** 16:19 — 0 comparisons found (no ground_truth pairs matched)  
**This report:** Manual QC findings from live OCR run + DB analysis

---

## Executive Summary

The pipeline is **operational and inserting correctly**. Four bugs were found and fixed in this pass. Two of four engines are currently down due to external issues (Google Drive OAuth scope mismatch, Paperless Tailscale unreachable). The 39-PDF backlog has been enqueued and the worker is running in background.

**Bottom line:** DB match rate 92.9%, high-confidence rows 88.4%, 4 bugs fixed, backlog processing.

---

## Database State (2026-06-18 ~18:30)

| Metric | Value |
|--------|-------|
| Total rows in client_menus | **6,983** |
| Matched (client_id IS NOT NULL) | **6,484** — 92.9% |
| Unmatched (no client match) | **499** — 7.1% |
| Weeks covered | **16** |
| Distinct PDFs in DB | **66** |

### Confidence Distribution

| Tier | Count | % |
|------|-------|---|
| High (≥0.75) | 6,171 | 88.4% |
| Medium (0.50–0.75) | 131 | 1.9% |
| Low (<0.50) | 681 | 9.8% |

### Recent Weeks

| Week Start | Rows |
|-----------|------|
| 2026-06-22 | 184 (current) |
| 2026-06-15 | 1,115 |
| 2026-06-08 | 917 |
| 2026-06-01 | 1,092 |

---

## Live OCR Test (Step 1 — DB Insert Verification)

PDF tested: `menu_ocr_0515520d.pdf`

| Metric | Result |
|--------|--------|
| Page pairs processed | 29 |
| Rows inserted | **+20** (69%) |
| Rows flagged (client_id NULL) | 9 (31%) |
| Engines active | tesseract_structured + claude_vision |
| Engines down | google_drive (403), paperless (Tailscale) |
| Runtime | 241.7 s (4.03 min/PDF) |
| DB delta | 6,963 → 6,983 |

The 9 flagged rows had valid OCR output but `match_client()` returned NULL due to name-order mismatch (see Fix 4). Fix applied — next runs should see higher insert rate.

---

## Bugs Found and Fixed

### Fix 1 · CC_ocr_live_watcher.py — Facility name in fallback extraction
**Problem:** Fallback name-extractor grabbed "GARDEN OF JOY ADULT DAYCARE" as a client name (163 rows in DB from `ocr_watcher_tesseract` source).  
**Fix:** Added `_HEADER_TOKENS` guard to skip facility/section-header lines before accepting a name.

### Fix 2 · CC_ocr_live_watcher.py — write_to_db() skip guard
**Problem:** Facility-name rows could still reach the DB INSERT even if Fix 1 was applied (e.g., from pre-queued jobs).  
**Fix:** Pre-check in `write_to_db()` skips any entry whose `client_name` contains facility keywords.

### Fix 3 · goj_menu_consensus_ocr.py — Google Drive OAuth scope
**Problem:** Script requested `drive` (full) scope; `reauth_google_full.py` grants only `drive.file`. Mismatch → 403 on every upload attempt.  
**Fix:** Aligned `SCOPES` to `['drive.file', 'drive.readonly', 'documents']`. **Still needs Kato to re-auth via browser.**

### Fix 4 · goj_menu_consensus_ocr.py — Name-order flip in match_client()
**Problem:** OCR outputs "First Last" (e.g., "Alexander Vayman") but DB stores "Last First" (e.g., "Vayman Alexander"). SequenceMatcher score < 0.6 → NULL result for valid clients.  
**Fix:** `match_client()` now tries both orderings and takes the best score. ~6 lines added.

---

## Engine Status

| Engine | Status | Notes |
|--------|--------|-------|
| 1 — Tesseract structured | ✅ Active | Local, page-pair aware, fast |
| 2 — Google Drive OCR | ❌ 403 | Token scope mismatch — scope fix applied, re-auth needed from Kato |
| 3 — Paperless-NGX | ❌ Unreachable | Tailscale LAN at 100.99.86.60:8000 — Kato to verify |
| 4 — Claude Vision | ✅ Active | Cloud; Kato-approved 2026-06-18; primary accuracy engine |

---

## Learning Store (`goj_menu_learning.json`)

| Metric | Value |
|--------|-------|
| client_name_map entries | 5 |
| item_corrections | 0 (no corrections confirmed yet) |
| Total runs tracked | 34 |
| Total flagged | 34 |
| Last run | 2026-06-18 18:29 |

Engine stats track only claude_vision (correct:3, wrong:5) because other engines use different stat paths — pre-existing, not a regression from this pass.

---

## Backlog Status

| Metric | Value |
|--------|-------|
| Total PDFs in gdrive_mirror/Menus/ | 40 |
| In DB before this pass | 1 |
| Newly enqueued | 29 |
| Previously queued (pending) | 10 |
| Worker status | ✅ Running — PID 89821 |
| Est. completion | ~2.5 hrs at 4 min/PDF (2 engines active) |
| Worker log | `~/Desktop/REX/logs/backlog_worker_20260618.log` |

---

## Open Issues for Kato

| Priority | Issue | Action Required |
|----------|-------|-----------------|
| 🔴 High | Google Drive engine 2 down | Run: `source ~/debate-chamber/.venv/bin/activate && cd ~/Desktop/REX && python3 reauth_google_full.py` — approve Gmail + Drive in browser |
| 🔴 High | 163 facility-header rows in DB | Soft-delete: `UPDATE client_menus SET deleted=1 WHERE client_name LIKE 'GARDEN%' AND source='ocr_watcher_tesseract';` (verify `deleted` column exists first) |
| 🟡 Medium | Paperless engine 3 unreachable | Check `tailscale status` and confirm Paperless at 100.99.86.60:8000 |
| 🟡 Medium | Cyrillic names don't match Latin DB | Future build: add transliteration in `match_client()` (~50+ lines — flagged, not auto-implemented) |
| 🟡 Medium | 1 row with `week_start='2028-03-27'` | OCR date parsing error (single row). Safe to soft-delete or correct manually. |

---

*QC pass completed by Hermes · Gold Health Systems · 2026-06-18*  
*Automated benchmark (CC_ocr_benchmark.py 16:19): 0 comparisons — ground_truth pairs not matched to test PDFs*