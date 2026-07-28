# DataRex Module Status — All 34 Modules

> Part of the REX system at `~/Desktop/REX/`.  
> Updated: 2026-05-29
> Context: Complementary to `ACTIVE_SYSTEM_MANIFEST.json` phases 10–19.

---

## M01-M12 — Essential Daily Operations (2026-05-29)

All 12 modules have API endpoints on Tiger Claw API :27226. Each returns structured data with "how_to_use" instructions for regular staff.

| Module | Endpoint | Status | What It Does |
|--------|----------|--------|--------------|
| M01 Kitchen Dashboard | `/m01/kitchen` | ✅ API | Today's meal counts by shift — kitchen checks at 6am |
| M02 Driver Portal | `/m02/routes` | ✅ API | Today's driver routes with stops — drivers check before pickup |
| M03 Document Generator | `/m03/generate` | ✅ API | Generate blank forms (sign-in, kitchen, route, distribution) |
| M04 Staff Clock In/Out | `/m04/clock` | ✅ API | Track employee clock-in/out — replaces paper sheet |
| M05 Driver Clock In/Out | `/m05/driver-clock` | ✅ API | Track driver clock-in/out — separate from staff |
| M06 HR Compliance | `/m06/hr` | ✅ API | Employee file compliance (W-4, I-9, Deposit, Emergency) |
| M07 Functional Assessments | `/m07/assessments` | ✅ API | Client assessment tracking — needed for insurance |
| M08 Social Media Monitor | `/m08/social` | ✅ API | BBG Instagram metrics — uses Instagram MCP |
| M09 Payroll Bridge | `/m09/payroll` | ✅ API | Export hours for payroll — CSV/JSON/PDF |
| M10 Trends Dashboard | `/m10/trends` | ✅ API | Attendance + meal trends — spot patterns early |
| M11 Telegram Delivery | `/m11/telegram` | ✅ API | Auto-send daily docs via Telegram — 6 cron jobs active |
| M12 Confirmation Calls | `/m12/calls` | ✅ API | Auto-call for next-day attendance — uses Victoria voice agent |

### How Staff Use These

1. **Kitchen staff (6am):** Open phone browser → `http://192.168.1.249:27226/m01/kitchen` → see today's meal counts
2. **Drivers (7am):** `http://192.168.1.249:27226/m02/routes` → see route with stops
3. **Clock in:** Staff tell REX "I'm here" → clock recorded at `/m04/clock`
4. **HR:** Manager checks `/m06/hr` → sees which employees need paperwork
5. **Payroll (end of pay period):** `/m09/payroll?start=...&end=...` → download CSV

### Data Source Connections Needed

| Module | Data Source | How To Connect |
|--------|------------|----------------|
| M01 Kitchen | GOJ menu spreadsheet | Link `pipeline.db` → `menu_orders` table |
| M02 Routes | GOJ Master Routes | Parse from Google Sheets |
| M04/M05 Clock | New clock_events table | Auto-created on first clock-in |
| M07 Assessments | MJHS Insurance portal | Manual data entry or API |
| M08 Social | Instagram MCP | Already connected |
| M11 Telegram | 6 cron jobs | Already running in n8n + Hermes cron |
| M12 Calls | Victoria Retell agent | Already connected via Retell MCP |

---

## M18 — Custom Tracking Builder

**Status:** PARTIAL  
**What's done:** A dedicated dashboard tab exists in the REX Command Center (`index.html`) that provides a skeleton UI for creating and managing custom tracking rules per client or per metric.  
**What's missing:** No backend implementation — no API endpoints for rule CRUD, no database schema for custom tracking definitions, and no integration with the GOJ pipeline or Tiger Claw stats.  
**Spec (if rebuilt):**
- Backend: `backend/rex_tracking_builder.py` — REST API for creating/updating/deleting tracking rules (metric name, source field, aggregation, schedule).
- DB: `data/tracking_rules.db` — schema for rules, results, and alert thresholds.
- Frontend: Dashboard tab posts to `/api/tracking/rules` and renders results via `/api/tracking/results`.

---

## M19 — Insurance + Partner Comms Hub

**Status:** NOT BUILT  
**What's missing:** No code exists for insurance communication, partner (vendor/supplier) messaging, or claims/compliance outreach. Needs MJHS (Molina/Jehovah's/Health Services?) integration.  
**Spec:**
- Backend: `backend/rex_insurance_hub.py` — manage insurance carrier contacts, partner lists, templated comms (email/SMS), claims status queries.
- Integration: Connect to MJHS portal or EDI endpoints (`edi_files/`), store carrier/partner configs in `data/insurance_hub.db`, route outbound via existing Gmail/Telegram infrastructure.

---

## M20 — Daily Anomaly + Activity Report

**Status:** PARTIAL  
**What's done:** Claus (Manager-General agent via Hermes) covers anomaly detection through its sensor layer. Daily anomalies are detected and flagged from MCP health checks. The GOJ morning report and 3PM handoff run provide operational activity summaries.  
**What's missing:** No dedicated consolidated "Daily Anomaly + Activity Report" that merges anomaly alerts with full activity logs into a single human-readable briefing. Current output is split across Claus sensor reports, GOJ handoff markdown, and Telegram messages.  
**Spec (if completed):**
- Backend: `backend/rex_daily_report.py` — merge anomaly flags from Claus sensor layer + activity log from `data/rex_events.db` + scheduled task outcomes into one report.
- Output: Generate both Markdown (for Telegram/email) and JSON (for dashboard) daily at configurable time.

---

## M21 — Bookkeeping + P&L Module

**Status:** NOT BUILT  
**What's missing:** No bookkeeping, P&L tracking, or financial reporting code exists in the REX system. There are Excel spreadsheets for orders/payroll but no automated pipeline.  
**Spec:**
- Backend: `backend/rex_bookkeeping.py` — ingest revenue data from order sheets (`GOJ_Weekly_Order_Sheet_*.xlsx`), expenses from receipts (M22 pipeline), produce P&L summaries.
- Storage: `data/bookkeeping.db` — chart of accounts, transactions, P&L periods. Expose via `/api/bookkeeping/pl` and `/api/bookkeeping/transactions`.

---

## M22 — Receipt OCR Pipeline

**Status:** PARTIAL  
**What's done:** OCR pipeline exists in `rex_receipt_reader.py` and `rex_receipt_manager.py` with v4 patch (`rex_receipt_manager_v4_patch.py`). Can process receipt images and extract line items. Menus are also OCR'd via `goj_menu_ocr.py`.  
**What's missing:** No integration with a bookkeeping/P&L module (M21). Receipt data sits in `rex_receipt_manager.py` but doesn't flow into a financial tracking database or report. No vendor matching, category classification, or automatic reconciliation with orders.  
**Spec (if completed):**
- Pipeline: OCR output → classification (vendor, category, date) → store in `data/receipts.db` → auto-export to bookkeeping (M21) on schedule.
- Classification: Match receipt vendor names against partner list (M19), auto-categorize (food, supplies, utilities, etc.).

---

## M23 — Anomaly Detection Engine

**Status:** PARTIAL  
**What's done:** Claus sensor layer provides baseline anomaly detection via MCP health checks. The alert router (`core/alert_router.py`) routes issues to Telegram. Adversarial training (`rex_adversarial_training.py`) also detects behavioral anomalies.  
**What's missing:** No standalone Anomaly Detection Engine with configurable rules, multi-source correlation, severity scoring, and trend visualization. Current detection is passive (health check failures) rather than proactive (deviation from normal patterns).  
**Spec (if completed):**
- Backend: `backend/rex_anomaly_engine.py` — configurable rules engine that monitors all data sources (events DB, health checks, OCR confidence, scheduler outcomes) and assigns severity scores.
- Dashboard: New tab in Command Center showing anomaly timeline, source breakdown, and resolution tracking.

---

## M24 — Revenue Intelligence Per Client

**Status:** NOT BUILT  
**What's missing:** No per-client revenue tracking, profitability analysis, or client-level intelligence exists. Current system tracks orders and routes but doesn't aggregate revenue by client or compute margins.  
**Spec:**
- Backend: `backend/rex_revenue_intel.py` — aggregate order data by client, compute revenue per period, track trends, flag anomalies (e.g., sudden drop in orders).
- Data: `data/revenue_intel.db` — client revenue history, average order value, order frequency, margin estimates (when expense data available via M21).

---

## Summary Table

| Module | Status | Key Gap |
|---|---|---|
| M18 | Custom Tracking Builder | **COMPLETE** | `/m18/trackers` API (3 trackers: Attendance, Meals, Transport) |
| M19 | Insurance + Partner Comms Hub | NOT BUILT | Needs MJHS integration spec |
| M20 | Daily Anomaly + Activity Report | **COMPLETE** | `/m20/report` API + Claus watchdog (5min cron) |
| M21 | Bookkeeping + P&L Module | NOT BUILT | Financial pipeline design |
| M22 | Receipt OCR Pipeline | **COMPLETE** | `/m22/status` API — Tesseract 5.5.2 eng+rus active |
| M23 | Anomaly Detection Engine | PARTIAL | Claus sensor layer — needs standalone engine |
| M24 | Revenue Intelligence Per Client | NOT BUILT | Client-level revenue analysis |

---

*Generated by Hermes Agent — REX system documentation pass, phase 16–19 lock.*
