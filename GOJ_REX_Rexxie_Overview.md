# REX & REXXIE: Intelligent Operations Platform
### Garden of Joy Adult Day Care — Brooklyn, NY
### Prepared April 2026

---

## What This Is

REX and Rexxie are a custom-built operational intelligence platform designed exclusively for Garden of Joy. Together they replace spreadsheets, group chats, and manual tracking with a fully automated, always-on brain that runs the day — every day — without anyone having to chase information or make redundant decisions.

They are not off-the-shelf software. They are purpose-built for GOJ's specific workflows, client population, staff structure, and compliance requirements.

---

## REX — The Backend Engine

REX is the data and intelligence core. It runs as a local server (FastAPI, port 8000) on-site, continuously managing and serving every piece of operational data the facility generates.

### What REX Knows

REX maintains a living, real-time database (SQLite, 28 tables) covering:

- **425 active clients** — demographics, schedules, routes, dietary preferences, attendance history
- **Authorization tracking** — Medicaid/insurance approval dates, expiration warnings, billing readiness per client
- **Staff compliance** — medical clearances, TB test and X-ray due dates, CPR/First Aid certifications, in-service training requirements
- **Menu submissions** — weekly client menu selections (scanned forms processed by 4-engine OCR pipeline)
- **Transportation** — route manifests, driver assignments, client pickup sequences, exception rules per client
- **Document storage** — scanned authorizations, sign-in sheets, medical records, staff documents

### What REX Does Automatically

REX is not passive storage — it actively processes and acts:

**Document Ingestion (4-Engine OCR Pipeline)**
Every document scanned and emailed to GOJ is automatically:
1. Pulled from Gmail by the scanner bot
2. Processed through four independent OCR engines (Tesseract, Google Drive Vision, Paperless-NGX, Claude Vision)
3. Voted on for accuracy — the consensus result is used
4. Categorized and saved (authorization scans → client record; menu forms → kitchen queue; sign-in sheets → attendance)

This eliminates manual data entry for incoming paperwork entirely.

**Compliance Monitoring**
REX continuously evaluates every staff member's compliance status:
- Flags overdue certifications immediately (e.g., CPR expired 70 days ago)
- Issues 30-day and 90-day advance warnings
- Generates color-coded compliance reports on demand

**Authorization Expiration Management**
REX watches 425 client authorization records and:
- Calculates days remaining to expiration per client
- Groups clients by urgency tier (expired / expiring in 7 / 30 / 90 days)
- Surfaces renewal batches so no authorization lapses silently

**Transportation Sheet Generation**
REX generates driver manifests and sign-in sheets automatically based on the day's scheduled attendees — accounting for individual client exceptions (e.g., Bogopolskiy is always on the second run, not wave 1).

**Menu Processing**
When weekly menu forms arrive (425 clients submit in Russian), REX:
- OCR-extracts selections from scanned forms
- Matches client names despite handwriting variation using fuzzy logic
- Aggregates selections into kitchen distribution sheets
- Tracks submission gaps and flags missing forms

---

## Rexxie — The Operator Interface

Rexxie is REX's Telegram-based interface. It is Kato's direct line to the system — available from any phone, anywhere, any time, without needing to open a dashboard or log into anything.

Rexxie is not a generic chatbot. It knows GOJ, knows the operational context, and speaks in plain language. It was built with a specific communication profile: direct, no fluff, operational focus first.

### Daily Automated Reports (Sent Automatically — No Action Required)

| Time | What Gets Sent |
|------|----------------|
| 7:30 AM | Morning briefing: expected attendance, menu data status, overnight Gmail scans processed |
| 10:00 AM | Kitchen + distribution sheets for next day |
| 3:00 PM | Sign-in sheet + driver list for next day |
| 9:00 PM | Actual attendance vs expected, drop-off confirmation, schedule changes, sign-in status |

The 9pm report has one target: end with "No decisions or actions necessary at this time." That sentence means the day closed clean.

### On-Demand Capabilities (Ask Rexxie Anytime)

Rexxie responds to plain-language queries:

- "Who's coming tomorrow?" → pulls tomorrow's schedule
- "Is [client name]'s authorization current?" → checks expiration status instantly
- "What's the menu this week for [client]?" → retrieves their submission
- "Who hasn't submitted a menu yet?" → surfaces the gap list
- "Send me the driver sheet for Friday" → generates and delivers the PDF
- "MENU BLAST" → triggers the OCR pipeline on all pending unprocessed menu scans
- "What compliance docs are expiring?" → delivers the staff compliance summary

### Memory and Learning

Rexxie maintains a persistent memory layer — every interaction, preference, correction, and exception gets stored and referenced going forward. It learns GOJ's patterns over time and adjusts its behavior accordingly. It does not start from scratch with every message.

---

## The Architecture Chain: How It All Works Together

```
SCANNER / EMAIL
     ↓
Gmail Inbox (scanner@goj-facility.com)
     ↓
Automatic Attachment Pull (DOWNLOAD_ALL_SCANS.command / scheduled bot)
     ↓
4-Engine OCR Pipeline
(Tesseract → Google Drive → Paperless-NGX → Claude Vision → Consensus Vote)
     ↓
Categorized Document Storage + Database Update
(auth_tracker.db — 28 tables, SQLite, local)
     ↓
REX Backend (FastAPI, port 8000) — Serves data to all consumers
     ↓
┌─────────────────────────────────────────────────────┐
│                                                     │
▼                                                     ▼
GOJ Dashboard (Flask, port 8080)              Rexxie (Telegram Bot)
Staff-facing web UI                           Chairman's mobile interface
Client profiles, auth tracker,                Daily reports, on-demand queries,
compliance view, upload tools                 emergency escalation, PDF delivery
│                                                     │
└─────────────────────┬───────────────────────────────┘
                      ▼
             OUTPUT DOCUMENTS
         (Signed by launchd — auto-restarts if system reboots)
         Kitchen sheets / Driver manifests / Sign-in PDFs
         Compliance reports / Auth renewal batches
```

The entire chain runs on-site on a Mac Mini. No external servers are required for core operations. launchd (macOS) keeps REX and the dashboard running continuously, auto-restarting after any reboot or crash.

---

## Current Operational Scale

| Category | Count / Status |
|----------|---------------|
| Active clients | 425 |
| Menu forms processed (OCR pipeline) | 17+ (pipeline live) |
| Staff compliance records tracked | 15 staff, 57 document records |
| Authorization records monitored | 425 clients, ongoing |
| Scanned documents ingested | Continuous via Gmail |
| Automated daily reports | 4 per weekday (fully scheduled) |
| OCR engines in consensus pipeline | 4 |
| Database tables | 28 |

---

## Why This Matters

Adult day care facilities run on margin. Compliance failures, lapsed authorizations, missed documentation — these are not just administrative problems, they are billing failures, audit risks, and in serious cases, regulatory violations.

REX and Rexxie exist to make sure none of that happens silently.

The system was built on three root causes of operational failure at GOJ:
1. Lack of communication between staff
2. Unforeseen circumstances with no documented response plan
3. No central database to quickly check live status

REX solves item 3 directly and enables solutions for 1 and 2 through Rexxie's real-time alerting and reporting.

The goal is not automation for its own sake. The goal is that every night at 9pm, the message ends: **"No decisions or actions necessary at this time."**

---

## What's Built vs. What's Coming

### Live and Operational
- GOJ Dashboard (client profiles, auth tracking, compliance view)
- REX backend API (full data layer)
- Rexxie Telegram bot (daily reports, on-demand queries)
- 4-engine OCR pipeline (menu processing live)
- Staff compliance tracking (57 records loaded)
- Gmail scanner integration (document ingestion live)
- launchd persistence (auto-restart on crash/reboot)

### In Active Development
- Authorization renewal workflow (46 clients expiring April 30 — urgent)
- Care plan upload + OCR extraction
- Carecenta schedule CSV import
- SWH compliance document parsing
- iOS Shortcut integration (quick mobile actions)
- Multi-user access (Vlad, front desk, kitchen — role-based)

---

*Built and maintained by Kato — Garden of Joy, Brooklyn NY*
*System operational as of April 2026*
