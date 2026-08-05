# SYSTEM_ARCHITECTURE.md — GOJ OCR Pipeline Architecture

> **Generated:** 2026-08-05 05:50 EDT  
> **Source:** Observed from running system, cron jobs, and code inspection  
> **Status:** As-is documentation, not a proposal  

---

## Execution Order

### Cron-Driven Schedule (typical weekday)

| Time | Job | Mode | Script/Target |
|------|-----|------|---------------|
| Every 3m | Email Intake | no_agent | Polls Gmail IMAP for new menu form PDFs |
| Every 2m | Folder Poll | no_agent | Watches intake folder for new files |
| Every 15m | Menu Sweep | no_agent | `CC_menu_sweep.py` — classifies new scans, runs OCR, quarantines failures |
| Every 10m | Surya Watchdog | no_agent | Monitors surya OCR health, restarts if needed |
| Every 10m | Consensus | no_agent | `consensus_hook.py` — multi-engine voting on dish reads |
| Every 10m | Review→TG | no_agent | `CC_ocr_review_queue.py` — escalates disagreements to Kato via Telegram |
| Every 30m | Active Learning | no_agent | `active_learning.py` — incorporates corrections into learning DB |
| Every 5m | DB Sync | no_agent | `sync_proprietary_db.py` — REX→Documents sync |
| 06:00 | Dashboard Daily Refresh | LLM | Syncs Carecenta roster to auth_tracker |
| 12:00 | Noon Refresh | LLM | Mid-day attendance + menu sync from Drive |
| 17:10 | Daily Documents | LLM | Generates next-day sign-in + kitchen sheets |
| 19:00 | Canon Guard | no_agent | `goj_canon_guard.py` — drift detection |
| 20:00 | Daily Package | LLM | Full next-day package: kitchen, distribution, sign-in, drivers |

### Manual Sequence (Kato-triggered)

```bash
# Full Friday pipeline (for next week's forms):
cd ~/Desktop/REX
python3 CC_drive_preflight.py YYYY-MM-DD        # Sync attendance from Drive
python3 CC_scan_to_docs.py --pipeline --drive-sync  # Generate 4 PDFs
python3 generate_distribution_sheet.py --date YYYY-MM-DD  # +2 PDFs
cd ~/Documents/goj\ files/dashboard/
python3 generate_tomorrow.py --day Monday --mode all --skip-preflight
```

---

## Dependency Graph

```
                    ┌──────────────────┐
                    │  Google Drive    │ (menu forms, sign-in tabs)
                    │  Gmail IMAP      │ (emailed forms)
                    └────┬─────────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
    CC_drive_preflight  Email Intake  Manual scan
         (810 lines)    (cron)        drop
              │          │
              ▼          ▼
         goj_proprietary.db (REX copy)
              │
              ▼
      sync_proprietary_db.py (every 5m)
              │
              ▼
         goj_proprietary.db (Documents copy) ←┐
              │                                │
    ┌─────────┼─────────┐                      │
    ▼         ▼         ▼                      │
  Surya    focr     MinerU                    │
  (primary) (hard)  (pre-process)             │
    │         │         │                      │
    └────┬────┴────┬────┘                      │
         ▼         ▼                          │
    consensus_hook.py                         │
         │                                     │
    ┌────┴────┐                                │
    ▼         ▼                                │
  Apply    Escalate                            │
  (auto)   (Telegram→Kato)                     │
    │                                           │
    ▼                                           │
  CC_menu_fill.py (151 lines)                  │
  • last_order_fallback                        │
  • house_standard                             │
  • day_shifted                                │
    │                                           │
    ▼                                           │
  write_blank_picks.py ────────────────────────┘
    │
    ▼
  pre_generation_gate.py
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  ▼
goj_kitchen_paired  generate_distribution  generate_tomorrow
(242 lines)         _sheet.py (330 lines)  (1,545 lines)
    │                  │                  │
    ▼                  ▼                  ▼
Kitchen_Wed_*.pdf  distribution_*.pdf   GOJ_*_signin.pdf
                                       GOJ_*_drivers.pdf

Key:
──► = data flow (writes to DB/file)
- -► = imports/calls (Python import)
```

### Caller/Callee Matrix

| Caller | Callee | Relationship |
|--------|--------|-------------|
| `CC_drive_preflight.py` | `goj_proprietary.db` (REX) | Writes menu data |
| `CC_drive_preflight.py` | `auth_tracker.db` | Writes `day_*_actual` |
| `CC_menu_sweep.py` | `CC_ocr_pipeline.py` | Imports OCR functions |
| `CC_menu_sweep.py` | `goj_proprietary.db` | Writes ocr_scan rows |
| `consensus_hook.py` | `focr_reader.py` | Calls focr for hard pages |
| `consensus_hook.py` | `surya_ocr` | Primary OCR engine |
| `active_learning.py` | `CC_menu_corrections` | Updates learning DB |
| `CC_menu_fill.py` | `goj_proprietary.db` (both copies) | Fills fallback rows |
| `goj_kitchen_paired.py` | `goj_proprietary.db` (Documents) | Reads menus |
| `goj_kitchen_paired.py` | `auth_tracker.db` | Reads `day_*_actual` |
| `generate_distribution_sheet.py` | `goj_proprietary.db` (Documents) | Reads menus |
| `generate_distribution_sheet.py` | `auth_tracker.db` | Reads attendance |
| `generate_tomorrow.py` | `auth_tracker.db` | Reads attendance + menus |
| `generate_tomorrow.py` | `GOJ_Menu_Orders.json` | Reads compiled orders |
| `CC_unified_sheets.py` | `ghs_schedule.db` (RETIRED) | **WRONG — uses stale DB** |

---

## Cron Relationships & Startup Sequence

### Startup Dependencies
1. Hermes gateway must be running (Work GW :3022)
2. OCR engines must be installed (surya-venv, focr binary, mineru-venv)
3. Google Drive Service Account key must be present
4. auth_tracker.db must exist with active clients

### Cron Cascade (ordered by dependency)
```
Email Intake (3m) ──┐
Folder Poll (2m)  ──┤
                    ▼
              Menu Sweep (15m) ──► Surya Watchdog (10m)
                    │
                    ▼
              Consensus (10m) ──► Review→TG (10m)
                    │
                    ▼
              Active Learning (30m) ──► DB Sync (5m)
                    │
                    ▼
              [Manual: CC_menu_fill]
                    │
                    ▼
              Pre-Generation Gate
                    │
                    ▼
              Kitchen + Distribution + Sign-in + Drivers
```

### Context-From Dependencies (cron job chains)
**UNVERIFIED —** Specific `context_from` chains between cron jobs were not extracted from jobs.json during this session.

---

## Data Flow: Scanned Form → Kitchen Sheet

```
1. FORM ARRIVES
   Email → IMAP poll → saves PDF to ~/Desktop/REX/menu_intake/
   OR: Staff scans → saves to network folder → poller picks up

2. OCR EXTRACTION                           [AUTOMATED]
   PDF → page_census.py (count pages)
   → surya_ocr (primary, fast)              ~5-10s/page
   → focr (hard pages, handwritten names)   ~28s/page
   → MinerU (pre-process cleanup only)      ~varies
   → Cloud DeepSeek (last resort, budget-capped)

3. CONSENSUS                                [AUTOMATED]
   consensus_hook.py: multi-engine voting
   → Agreed picks → write to extraction.json
   → Disagreed → menu_review_queue → Telegram [PARTIAL — Kato must respond]

4. APPLY                                    [AUTOMATED]
   confirmed picks → write_blank_picks.py → goj_proprietary.db (both copies)
   → source_sheet = 'ocr_scan'

5. FILL CHAIN                               [AUTOMATED]
   CC_menu_fill.py:
   → Clients with ocr_scan → keep
   → Clients with no row → last_order_fallback (most recent complete order)
   → Clients with never ordered → house_standard (most common plate)
   → Component fill: empty cells → own nearest complete row

6. PRE-GENERATION GATE                      [AUTOMATED]
   pre_generation_gate.py: contract validation
   → All 4 dish cells non-null
   → shift ∈ {'1','2'}
   → client_name ∈ roster
   → Unique (client_name, menu_date, shift)

7. GENERATION                               [AUTOMATED]
   → goj_kitchen_paired.py → Kitchen_Wed_Aug05_S1.pdf
   → generate_distribution_sheet.py → distribution_shift1_2026-08-05.pdf
   → generate_tomorrow.py → signin + drivers PDFs

8. DISTRIBUTION                             [MANUAL]
   Staff member downloads emailed PDFs → prints → kitchen floor

9. ATTENDANCE TRACKING                      [PARTIAL]
   Sign-in sheets → staff marks checkboxes → returned to office
   Digital: Carecenta portal (live) → auth_tracker.db

10. BILLING                                 [MANUAL]
    UNVERIFIED — Billing pipeline not observed during this session.
    Carecenta shows: Last billed 7/27/2026 (ELDERSERVE $38,600, ANTHEM $570)

11. REPORTING                               [NOT BUILT]
    No automated weekly/monthly reporting pipeline was found.
    Daily Compound cron synthesizes wiki pages only.
```

---

## Workflow DAG Status

| Stage | Status | Notes |
|-------|--------|-------|
| OCR (scan→text) | **AUTOMATED** | 4-engine pipeline, cron-driven |
| Consensus (multi-engine) | **AUTOMATED** | Disagreements escalate to Kato |
| Escalation (Kato review) | **PARTIAL** | Kato must respond via Telegram |
| Apply (picks→DB) | **AUTOMATED** | Dual-DB write |
| Fill (fallback orders) | **AUTOMATED** | CC_menu_fill.py |
| Kitchen Sheets | **AUTOMATED** | goj_kitchen_paired.py |
| Distribution Sheets | **AUTOMATED** | generate_distribution_sheet.py |
| Sign-in Sheets | **AUTOMATED** | generate_tomorrow.py |
| Driver Routes | **PARTIAL** | Route data from ghs_schedule.db + manual overrides |
| Transportation | **MANUAL** | Drivers follow printed manifests |
| Attendance Recording | **PARTIAL** | Paper sign-in + Carecenta portal |
| Billing | **MANUAL** | Via Carecenta portal, last run 7/27/2026 |
| Reporting | **NOT BUILT** | No automated reporting pipeline |
| Auth Tracking | **PARTIAL** | auth_tracker.db, Carecenta sync unreliable |
| Menu Form Generation | **AUTOMATED** | build_personalized_menus.py (weekly) |
| Email Delivery | **AUTOMATED** | himalaya CLI via cron |
| Voice Agent (Victoria) | **AUTOMATED** | Retell API, daily attendance calls |
| Client Identity Resolution | **PARTIAL** | name_alias table, fuzzy matching gaps |
| Data Backup | **UNVERIFIED** | GDrive backup script status uncertain |
