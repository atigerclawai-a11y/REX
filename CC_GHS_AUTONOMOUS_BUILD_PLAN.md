# CC_GHS_AUTONOMOUS_BUILD_PLAN.md
# Gold Health Systems — Autonomous Operations Platform
# Tiger Claw Platform: Full Independence Roadmap
# Version 1.0 · June 4, 2026 · Confidential — Chairman Eyes Only

---

## EXECUTIVE SUMMARY

### Vision

Gold Health Systems will own its entire operational stack by Q1 2028. No Carecenta. No GeoTab. No ADP. No third-party software extracting margin from operations we built, for clients we serve, on infrastructure we run. Every dollar saved is a dollar retained. Every workflow we own is a workflow we can sell.

The platform we are building — **Tiger Claw Platform (TCP)** — is not a side project. It is the core infrastructure of a second business: a B2B SaaS company that sells purpose-built adult day care management software to the 4,600+ programs across the United States that are currently paying legacy vendors for mediocre software that was never designed for operators like us.

### The Opportunity in One Sentence

We are already building this for ourselves. Selling it to others is the profitable accident.

### Current State

Garden of Joy (GOJ) Adult Day Care, Brooklyn NY, operates with:

- **425 active Medicaid clients**, Mon–Sat attendance, complex authorization tracking
- **15 employees**, multi-shift scheduling, driver routes across Brooklyn
- **Partially-built proprietary infrastructure**: REX FastAPI backend, GOJ Dashboard (Flask/port 8080), auth_tracker.db, Hermes AI gateway, 6-step daily automation pipeline via n8n and Telegram bots, Cloudflare tunnel, Google OAuth, live Clover POS integration
- **Third-party dependency cost**: Carecenta (~$800–1,500/mo), GeoTab (~$300–600/mo), ADP (~$400–800/mo), clock-in system (~$50–200/mo) = **$1,550–3,100/month or ~$37,200/year at midpoint**

### What This Plan Delivers

By Month 18, Tiger Claw Platform will have replaced all four third-party systems, with GOJ running 100% on owned infrastructure. By Month 24, TCP will be licensed to the first external adult day care client. By Year 3, 50 clients at $500–2,000/month = $600K–$1.2M ARR on a platform that cost us less than $50K to build.

### Financial Summary

| Milestone | Timeline | Investment | Annual Savings/Revenue |
|---|---|---|---|
| ZK Biometric + Attendance | Month 3 | ~$2,500 | ~$10,000/yr (Carecenta partial) |
| Billing + Auth Module live | Month 6 | ~$5,000 | ~$20,000/yr (Carecenta full) |
| GeoTab replacement | Month 9 | ~$500 | ~$4,800/yr |
| Payroll module (Gusto bridge) | Month 12 | ~$2,000 | ~$7,200/yr |
| First external client | Month 18 | ~$0 | ~$12,000/yr |
| 50 external clients | Month 36 | ~$15,000 (infra scale) | ~$600K–1.2M/yr |

**Phase 1–3 Total Investment: ~$10,000**
**5-Year ROI: 40:1 at conservative estimates**

---

## SECTION 1: PLATFORM ARCHITECTURE — "TIGER CLAW PLATFORM"

### 1.1 Platform Identity

**Name:** Tiger Claw Platform (TCP)
**Tagline:** *Built by operators. For operators.*
**Core principle:** Every line of code that runs GOJ is also a line of code that can run someone else's adult day care. We build once, sell many.

TCP is not a rewrite from scratch. It is a structured extension of what already exists:

- **REX FastAPI backend** (`~/Desktop/REX/backend/main.py`, 3,976 lines) becomes the TCP application server
- **auth_tracker.db** (426 clients, authorization, menus, attendance) becomes the reference schema for TCP's PostgreSQL migration
- **GOJ Dashboard** (Flask, port 8080) becomes the TCP operator dashboard (React frontend replacing Flask templates)
- **Hermes AI gateway** becomes the TCP Intelligence Layer
- **n8n** (6 live workflows) becomes the TCP automation engine
- **Cloudflare tunnel** (`hermestigerclaw.com`) becomes the TCP external-access layer

### 1.2 Core Modules

```
Tiger Claw Platform
├── Module 1: Client Management
│   ├── Demographics & contacts
│   ├── Authorization tracking (extends auth_tracker.db)
│   ├── Medical profiles (diagnoses, allergies, preferences)
│   ├── Document vault (auth letters, physician orders)
│   └── Client portal (future)
│
├── Module 2: Billing & Authorization
│   ├── Medicaid/managed care claim generation (837P/837I)
│   ├── Eligibility verification (270/271 transactions)
│   ├── Remittance processing (835 ERAs)
│   ├── Authorization expiry tracking (already in auth_tracker.db)
│   ├── Clearinghouse integration (Availity, Change Healthcare)
│   └── Denial management workflow
│
├── Module 3: Scheduling
│   ├── Client schedule (day assignments, Mon–Sat)
│   ├── Atomic schedule change cascade (7 downstream updates)
│   ├── Absence/sick day handling
│   ├── Recurring vs. one-time schedule logic
│   └── Schedule conflict detection
│
├── Module 4: Attendance (ZK Biometric)
│   ├── ZK BioTime 8.0 API integration
│   ├── Fingerprint + face ID dual-mode
│   ├── iPad kiosk fallback (face ID via camera)
│   ├── Manual override with audit trail
│   ├── Real-time attendance dashboard
│   └── Automated sign-in sheet generation (replacing manual PDFs)
│
├── Module 5: Driver & Fleet
│   ├── Route sheet generation (extends existing automation)
│   ├── Real-time GPS tracking (GeoTab SDK layer)
│   ├── Route optimization engine
│   ├── Driver clock-in/out (ZK mobile)
│   └── Drop-off confirmation logging
│
├── Module 6: HR & Payroll
│   ├── Employee records (extends employees table, 15 rows → full profiles)
│   ├── Biometric time & attendance for staff
│   ├── Overtime alerts and schedule compliance
│   ├── PTO/sick time accrual
│   ├── NY state tax compliance
│   ├── Direct deposit (Plaid/Stripe Payroll API)
│   └── W-2/1099 generation
│
├── Module 7: Menu & Nutrition
│   ├── Russian 2-page form intake (OCR pipeline already built)
│   ├── 425-client menu tracking (client_menus table, `main` column)
│   ├── Weekly menu cycle management
│   ├── Kitchen list generation (10:30 AM automation already live)
│   ├── Nutrition compliance reports
│   └── Dietary restriction enforcement
│
└── Module 8: AI Intelligence Layer (Hermes)
    ├── Natural language operations queries
    ├── Anomaly detection (billing, attendance, auth expiry)
    ├── Automated Medicaid billing review
    ├── Client communication (Retell voice AI)
    ├── Daily automation orchestration (n8n)
    └── Cross-module insight reports
```

### 1.3 Technology Stack

| Layer | Current | TCP Target | Rationale |
|---|---|---|---|
| Application server | FastAPI (REX) | FastAPI (extended) | Already built, no rewrite |
| Frontend | Flask templates | React + Tailwind | SaaS-grade UI, component reuse |
| Database | SQLite (auth_tracker.db) | PostgreSQL 16 | Multi-tenant, concurrent writes, JSONB |
| Caching / queues | None | Redis 7 | Job queuing, real-time features |
| Automation | n8n (6 workflows) | n8n (extended) | Already running, no change |
| AI gateway | Hermes (port 3002) | Hermes (extended) | Already live |
| Auth | JWT device pairing | JWT + RBAC (existing rex_role_auth.py) | Already built |
| Infrastructure | Mac Mini M4 24GB | Mac Mini M4 + VPS for SaaS | Scale when needed |
| Tunnel | Cloudflare (hermestigerclaw.com) | Cloudflare + custom domain per client | Already live |
| Payments | Clover POS (integrated) | Clover + Stripe | Already integrated |

### 1.4 Multi-Tenancy Design

TCP is built single-tenant for GOJ and refactored for multi-tenancy in Phase 5. The key principle: every table that is currently implicit single-tenant gets a `facility_id` column added. Auth, clients, schedules, billing — all scoped to facility. GOJ's `facility_id = 1`. Client 2's facility is `facility_id = 2`. No data bleed.

The FastAPI router structure already supports this via prefix-based routing. Multi-tenancy is a schema migration + middleware layer, not an architectural rewrite.

---

## SECTION 2: REPLACE CARECENTA

### 2.1 What Carecenta Does Today

Carecenta is an adult day care management platform. At GOJ it handles:

| Carecenta Function | Current Status at GOJ |
|---|---|
| Client demographics | Partially in auth_tracker.db clients table |
| Authorization tracking | Built in auth_tracker.db authorization table |
| Attendance (manual sign-in) | Manual sheets + partial digital |
| Medicaid billing (837P claims) | Carecenta handles this entirely |
| Eligibility checks (270/271) | Carecenta |
| Remittance processing (835 ERAs) | Carecenta |
| Scheduling | Carecenta + manual overlap |
| Reports (daily census, billing summaries) | Carecenta |
| Driver/transport notes | Carecenta partial |

**Monthly cost:** ~$800–1,500/month depending on plan tier and client count.
**Annual cost:** ~$9,600–18,000/year.
**What we are paying for:** A database, a billing EDI layer, and some PDF exports. We own a better database. We can build the EDI layer. The PDFs are already automated.

### 2.2 Feature-for-Feature Replacement Map

| Carecenta Feature | TCP Module | Build Status | Timeline |
|---|---|---|---|
| Client demographics | Client Management | 40% built (auth_tracker.db) | Month 2 |
| Authorization tracking | Billing & Auth | 70% built (authorization table) | Month 2 |
| Auth expiry alerts | Billing & Auth / AI Layer | 80% built (Hermes alerts exist) | Month 1 |
| Attendance (paper sign-in) | Attendance + ZK Biometric | 0% (hardware needed) | Month 3 |
| Medicaid 837P claim gen | Billing Module | 0% | Month 5 |
| 270/271 eligibility checks | Billing Module | 0% | Month 4 |
| 835 ERA remittance | Billing Module | 0% | Month 6 |
| Daily census report | Dashboard | 60% built (GOJ Dashboard) | Month 2 |
| Scheduling | Scheduling Module | 20% built (pending_schedule_changes table) | Month 3 |
| Driver/transport notes | Driver & Fleet | 30% built (driver sheets automation) | Month 4 |
| Managed care portals (MCO billing) | Billing Module | 0% | Month 6 |
| HIPAA-compliant document storage | Client Management | 50% built (rex_vault, EncryptedStorage) | Month 3 |

### 2.3 ZK Biometric Attendance — Hardware Specification

**Primary recommendation: ZK BioTime 8.0 series**

The ZK BioTime 8.0 is the industry-standard biometric time-and-attendance device used across healthcare, schools, and government facilities. It supports fingerprint and face ID in a single unit, has a documented REST API, and runs on a local network with no mandatory cloud subscription.

**Recommended units:**

| Device | Best Use | Price Est. | Notes |
|---|---|---|---|
| ZK F22 Face ID Terminal | Main entrance, client check-in | ~$350–450/unit | Face ID + fingerprint, 10" touchscreen |
| ZK MB460 Multi-Bio | Staff clock-in, secondary entrance | ~$300–400/unit | Fingerprint + card, API-ready |
| ZK UA760 Face Recognition | Admin area, manager override station | ~$400–500/unit | High-accuracy face ID, HTTPS API |

**GOJ deployment:**

- **2× ZK F22** at main entrance for client check-in (face ID — clients don't need to touch a surface)
- **1× ZK MB460** in staff area for employee clock-in
- **1× iPad (existing or new, ~$329 refurb)** as fallback kiosk for clients who cannot use biometric

**Total hardware: ~$1,400–1,700 for primary deployment**

**ZK BioTime 8.0 API integration:**

ZK devices expose a local HTTP/HTTPS API on port 80/443. The API supports:

```python
# ZK BioTime 8.0 API — attendance pull (runs in TCP every 60 seconds)
GET http://{zk_device_ip}/iclock/cdata?SN={serial}&table=ATTLOG
POST http://{zk_device_ip}/iclock/devicecmd   # push commands

# TCP will run a background poller (FastAPI BackgroundTasks):
# Every 60s → pull attendance logs → write to PostgreSQL → update dashboard
```

The ZK SDK is available as a Python wrapper (`pyzk` library). TCP's `backend/zk_attendance.py` module will handle device polling, deduplication (same person clocking in twice), and dashboard updates.

**iPad kiosk fallback:**

For clients who cannot use fingerprint (some elderly clients have worn fingerprints) or prefer not to use face ID, a mounted iPad running a TCP web app will display a simple photo-confirmation check-in screen. Staff taps the client's photo, confirms, system logs attendance. No separate app — just a TCP web route optimized for touch.

### 2.4 Medicaid Billing Integration

This is the most complex and highest-stakes component. Getting billing wrong means denied claims, cash flow disruption, and potential compliance violations. The approach is: **run parallel for 90 days before cutting Carecenta off.**

**EDI transaction set for adult day care Medicaid billing:**

| Transaction | Purpose | Format | Clearinghouse |
|---|---|---|---|
| 837P | Professional claim submission | X12 5010 | Availity or Change Healthcare |
| 270 | Eligibility inquiry | X12 5010 | Availity |
| 271 | Eligibility response | X12 5010 | Availity |
| 835 | Electronic remittance advice | X12 5010 | Availity |
| 277 | Claim status | X12 5010 | Availity |

**Clearinghouse recommendation: Availity**

Availity offers a REST API wrapper around EDI transactions, which is significantly easier to integrate than raw X12 EDI. Their API supports:

- Real-time eligibility checks (critical — check every client every morning before they arrive)
- Claim submission with real-time acknowledgment
- ERA download and auto-posting

Availity charges per transaction (~$0.10–0.30 per claim) but has no monthly minimums. For 425 clients with ~20 billing days/month, this is roughly 8,500 claims/month = ~$850–2,550/month in transaction fees vs. Carecenta's flat license. The cost comparison favors Carecenta for pure volume — but TCP eliminates the license fee entirely once billing is internal, and the transaction fees go directly to the clearinghouse with no markup.

**Alternative: Change Healthcare (Optum)**

Change Healthcare (now Optum) is the dominant clearinghouse for NY Medicaid. They have a direct API and many managed care organizations (MCOs) in NYC have established EDI relationships with them. TCP should support both — Availity for real-time eligibility, Change Healthcare for claim submission — because different MCOs have different clearinghouse preferences.

**Billing module build plan:**

```
Month 4: Eligibility check integration (270/271 via Availity REST API)
Month 5: 837P claim generation from attendance records
          - Input: ZK attendance log + authorization table + client demographics
          - Output: X12 5010 837P file → submit to clearinghouse
Month 6: 835 ERA parsing and auto-posting
          - Download remittance → match to claims → mark paid/denied
          - Denied claims → alert queue → AI review → resubmission workflow
```

**Authorization pre-billing check (already 70% built):**

The authorization table in auth_tracker.db tracks `service_end_date`, `status` (ACTIVE/EXPIRED/PENDING RENEWAL), and client-service mappings. TCP will add a daily pre-billing sweep:

- Every billing day: query all clients with attendance → check auth status → flag any client with EXPIRED auth who attended → hold claim → alert Kato
- This prevents billing for services with no valid authorization — a common Medicaid audit trigger

### 2.5 Data Migration from Carecenta

Carecenta supports data export (CSV) for client demographics, authorization history, and billing history. Migration plan:

1. Export all client data from Carecenta → CSV
2. Map fields to TCP schema (demographics → clients table, auths → authorization table)
3. Run validation script: compare record counts, flag missing fields
4. Import to TCP PostgreSQL (dev environment first)
5. Run 30-day parallel operation: both systems receive same inputs, compare outputs
6. Reconcile billing: Carecenta submits claims, TCP generates shadow claims → compare
7. Cutover when shadow claim accuracy reaches 99%+ for 30 consecutive days

**GOJ already has a head start:** auth_tracker.db contains 426 client records, authorization data, and menus. The migration is a database upgrade, not a ground-up import.

### 2.6 Build Timeline: Carecenta Replacement

```
Month 1: Auth expiry alerts fully automated (already 80% done)
          Client demographics module (extend existing DB schema)

Month 2: Daily census and scheduling dashboard
          Atomic schedule change cascade (7-table update) fully built and tested

Month 3: ZK biometric devices ordered, installed, integrated
          Attendance module live — replace manual sign-in sheets
          iPad fallback kiosk deployed

Month 4: Eligibility verification module (270/271)
          Document vault (HIPAA-compliant storage, extends rex_vault.py)

Month 5: 837P claim generation (shadow mode — Carecenta still primary)
          Managed care billing rules library (each MCO has quirks)

Month 6: 835 ERA parsing and auto-posting
          90-day parallel billing validation begins
          Denial management workflow

Month 9: Carecenta cutover — TCP is primary billing system
          Carecenta license cancelled
```

### 2.7 Cost Analysis: Carecenta vs. TCP

| Cost Category | Carecenta | TCP |
|---|---|---|
| Monthly license | $800–1,500 | $0 |
| Clearinghouse (Availity/CH) | Included | ~$850–2,550/mo (transaction fees) |
| Development cost (one-time) | $0 | ~$15,000 (Kato's time valued at market rate) |
| Hardware (ZK devices) | $0 | ~$1,700 (one-time) |
| Maintenance | Vendor-handled | Internal (~5 hrs/month) |
| **Annual total** | **$9,600–18,000** | **$10,200–30,600 (clearinghouse variable)** |

**Note on clearinghouse costs:** Transaction fees are inherent to Medicaid billing regardless of software vendor. Carecenta includes them in the license price, which means you are paying them whether you submit 100 claims or 10,000. At GOJ's volume, Carecenta's bundled pricing may actually be competitive on pure billing cost — but TCP provides full data ownership, custom workflow automation, and the SaaS business case, which changes the calculus entirely.

**The real financial case is not Carecenta savings alone — it is TCP as a revenue-generating asset.**

---

## SECTION 3: REPLACE GEOTAB

### 3.1 Current GeoTab Setup

GeoTab provides GPS fleet tracking for GOJ's transport vans. The hardware (GO9 or similar OBD-II dongles) is already installed in the vehicles and paid for. The monthly cost is the software subscription — the GeoTab cloud platform that processes GPS data and provides the web dashboard.

**Current cost:** ~$25–50/vehicle/month. At 3–5 vans: ~$75–250/month = ~$900–3,000/year.
**Hardware status:** Owned by GOJ, plug-and-play in vehicle OBD-II port.
**What we are paying for:** A web dashboard and data processing layer. We can build both.

### 3.2 GeoTab SDK Integration

GeoTab provides a full SDK (MyGeotab SDK) that allows direct data access from their cloud API. This is the bridge: **keep the GeoTab hardware, replace the GeoTab software.**

```python
# GeoTab SDK — direct API access (Python)
from mygeotab import API

api = API(username='kato@goldhealth.com', password='...', database='GoldHealth')
api.authenticate()

# Pull live vehicle locations
vehicles = api.get('Device')
positions = api.get('DeviceStatusInfo', search={'deviceSearch': {'id': vehicle_id}})

# Pull trip history
trips = api.get('Trip', search={
    'deviceSearch': {'id': vehicle_id},
    'fromDate': datetime.now() - timedelta(hours=24)
})
```

TCP's `backend/fleet_tracker.py` will poll GeoTab every 60 seconds during operating hours (6 AM–7 PM) and write position data to PostgreSQL. The GOJ Dashboard will display real-time van locations on a map (Leaflet.js — open source, no API fees).

**Alternative (no GeoTab dependency at all):** If GOJ wants to eliminate GeoTab entirely, the hardware can be swapped for a raw OBD-II GPS tracker (Teltonika FMB920, ~$80/unit) that sends GPS data directly to TCP via MQTT. This eliminates the GeoTab subscription entirely and gives full data ownership. Timeline: 1 additional month for hardware swap.

### 3.3 TCP Fleet Module Features

| Feature | GeoTab Current | TCP Target | Timeline |
|---|---|---|---|
| Real-time van location | GeoTab dashboard | GOJ Dashboard (Leaflet map) | Month 7 |
| Trip history | GeoTab reports | PostgreSQL + TCP reports | Month 7 |
| Driver assignment | Manual | TCP scheduling → driver module | Month 8 |
| Route sheet integration | Manual | Auto-generate from schedule | Month 8 |
| Drop-off confirmation | None | Driver mobile app (TCP web app) | Month 9 |
| Geofence alerts | GeoTab | TCP geofence engine | Month 9 |
| Mileage reports | GeoTab | TCP auto-generated (billing use) | Month 8 |

### 3.4 Route Optimization

GOJ already generates driver sheets as part of the 3:15 PM automation. TCP will enhance this with:

- Client pickup/drop-off addresses → optimize route order (Google Maps Distance Matrix API or open-source OSRM)
- Multiple van assignments — TCP assigns clients to vans based on proximity clusters
- Real-time route updates when a client calls sick (schedule change cascade already handles the attendance side; TCP adds the route recalculation)

### 3.5 Driver Mobile Check-In

Drivers clock in and out via the ZK mobile-compatible web app on their phone (Tailscale-connected). Same ZK backend, phone-based instead of physical device. GPS location logged at clock-in/out for verification.

### 3.6 Build Timeline: GeoTab Replacement

```
Month 6: GeoTab SDK integration → pull vehicle positions → store in PostgreSQL
Month 7: Real-time map in GOJ Dashboard (Leaflet.js)
          Trip history and mileage reports
Month 8: Route optimization engine
          Driver assignment from scheduling module
Month 9: Drop-off confirmation mobile flow
          Geofence alerts (van arrived at facility, van at client address)
          GeoTab subscription cancelled
```

**Total investment:** ~$500 (dev time, no new hardware required unless swapping to raw OBD-II devices)
**Annual savings:** ~$900–3,000/year

---

## SECTION 4: REPLACE EMPLOYEE CLOCK IN / OUT

### 4.1 Current System

GOJ currently uses WiFi-based clock-in, a standalone system that tracks employee hours for payroll processing. This data then flows into ADP manually or via export.

**Current cost:** ~$50–200/month depending on vendor.
**What we are replacing it with:** The same ZK biometric hardware deployed for client attendance, configured with a separate employee mode.

### 4.2 ZK Staff Deployment

The ZK MB460 Multi-Bio device (already recommended in Section 2.3) handles both fingerprint and RFID card. For GOJ's 15 employees:

- **Enrollment:** Each employee registers fingerprint (primary) and is issued an RFID card (backup)
- **Clock-in:** Touch fingerprint or tap card at MB460 → TCP records timestamp, employee ID, location
- **Clock-out:** Same gesture → TCP calculates shift duration → feeds payroll module
- **Break tracking:** Optional — second tap can mark break start/end

**ZK staff configuration is separate from client attendance.** The same device network supports both use cases via ZK BioTime's department-based access control. Staff appear in the "Employees" department; clients in the "Clients" department. TCP queries both data streams but processes them through different pipelines.

### 4.3 Remote and Driver Clock-In

Drivers and any remote staff use **TCP Mobile Clock-In**, a Progressive Web App (PWA) accessible at `app.hermestigerclaw.com/clockin`:

- Tailscale-connected for security (only accessible on the GOJ VPN)
- PIN + GPS verification — must be within 500m of route start point to clock in (prevents buddy punching)
- Falls back to supervisory approval if GPS check fails
- Works on any smartphone, no app store installation required

### 4.4 Overtime and Compliance Alerts

TCP HR module will monitor:

- **Daily overtime alert:** Any employee approaching 8 hours in a day → Hermes sends Telegram alert to Kato
- **Weekly overtime alert:** Any employee approaching 40 hours → alert at 36 hours
- **NY state meal break compliance:** NYC requires 30-min meal break for shifts >6 hours — TCP logs and flags violations
- **Schedule vs. actual comparison:** If an employee was scheduled 9 AM–5 PM and clocked in at 9:47 AM, TCP flags the 47-minute late arrival in the daily report

### 4.5 Build Timeline: Clock-In Replacement

```
Month 1: ZK MB460 device ordered and installed (concurrent with client ZK deployment)
Month 2: Employee enrollment (15 staff, ~2 hours total)
          TCP clock-in backend live (extends ZK attendance module)
Month 3: Mobile PWA for drivers deployed
          Overtime alerts active
          Old WiFi clock-in system cancelled
```

**Total investment:** ~$400 (ZK MB460 unit, already counted in Section 2.3 hardware budget)
**Annual savings:** ~$600–2,400/year

---

## SECTION 5: REPLACE ADP

### 5.1 Why ADP Is the Hardest Replacement

Payroll is not a feature. Payroll is a regulated financial function with:

- Federal tax obligations (FICA, FUTA, income tax withholding)
- New York State tax obligations (NYSIT, NYC tax, NY SDI, NY PFL)
- NYC-specific requirements (Paid Safe and Sick Leave law, ESSTA)
- Direct deposit via ACH banking networks
- W-2 issuance by January 31 each year
- Quarterly payroll tax filings (941, NYS-45)

Getting any of this wrong results in IRS penalties, state agency notices, and potential personal liability for the Chairman. **The rule here is: do not cut ADP until TCP payroll has been validated for at least two full calendar quarters.**

### 5.2 Gusto as the Bridge

Rather than building raw payroll processing from scratch (which would take 12+ months to do safely), TCP will integrate **Gusto's Payroll API** as the bridge layer:

- Hours come from ZK biometric attendance → TCP calculates gross pay
- TCP sends payroll run data to Gusto API → Gusto handles tax calculations, direct deposit, filings
- ADP is turned off; Gusto costs ~$40/mo base + $6/employee/mo = ~$130/mo for 15 employees
- **ADP current cost:** ~$400–800/month → Gusto saves ~$270–670/month immediately
- TCP owns the time-tracking data; Gusto owns the regulatory compliance layer
- As TCP payroll matures, Gusto can be replaced with direct ACH (Plaid) + tax filing (TaxJar/Avalara) — but this is a Year 2 decision

**This is not a compromise. It is the correct architecture.** Gusto is an API-first payroll provider specifically designed to be a backend for custom software. They are the payroll layer; TCP is the workflow and intelligence layer above it.

### 5.3 TCP Payroll Module Architecture

```
ZK Biometric → attendance logs
       ↓
TCP HR Module
  - Hours calculation (regular, overtime, holiday)
  - PTO/sick time deduction
  - Pay period summary (bi-weekly)
  - Shift differential (if applicable)
       ↓
Payroll Review (Kato approves each run — one click in dashboard)
       ↓
Gusto API (POST /payroll/runs)
  - Tax calculation
  - Direct deposit ACH
  - Pay stubs generated
  - Tax filings (941, NYS-45)
       ↓
QuickBooks sync (payroll journal entry via QBO API)
  - Labor cost by department
  - Benefits accruals
```

### 5.4 Feature Mapping: ADP → TCP + Gusto

| ADP Feature | TCP + Gusto Equivalent | Status |
|---|---|---|
| Time tracking | ZK biometric → TCP HR Module | Month 3 (hardware) |
| Hours approval | TCP dashboard (Kato one-click approve) | Month 4 |
| Gross pay calculation | TCP HR Module | Month 4 |
| Tax calculation | Gusto API | Month 5 (Gusto integration) |
| Direct deposit | Gusto API → ACH | Month 5 |
| Pay stubs | Gusto-generated PDF | Month 5 |
| PTO tracking | TCP HR Module | Month 4 |
| W-2 / 1099 | Gusto (annual) | Year 1 |
| 941 / NYS-45 filings | Gusto (quarterly) | Year 1 |
| NY Paid Sick Leave compliance | TCP HR Module + Gusto | Month 5 |
| QuickBooks sync | TCP → QBO API | Month 6 |
| HR document storage | TCP Client Management (staff profile vault) | Month 4 |

### 5.5 Build Timeline: ADP Replacement

```
Month 3:  ZK staff clock-in live (Section 4)
Month 4:  TCP HR Module — hours calculation, PTO tracking, pay period summaries
Month 5:  Gusto API integration — first payroll run through TCP → Gusto
          Parallel run: ADP and TCP both process same payroll → compare outputs
Month 6:  QuickBooks sync live (payroll journal entries)
Month 9:  ADP subscription cancelled — Gusto is primary payroll processor
Month 18: Evaluate replacing Gusto with direct ACH + tax filing (optional — only
          if the savings justify the compliance engineering effort)
```

**Annual savings:** ADP ~$400–800/month → Gusto ~$130/month = **~$3,240–8,040/year saved**

### 5.6 NY State Compliance Checklist (Non-Negotiable Before ADP Cutoff)

- [ ] NY State Withholding Tax (IT-2104) on file for all 15 employees
- [ ] NY SDI (State Disability Insurance) enrollment via Gusto
- [ ] NY PFL (Paid Family Leave) enrollment via Gusto
- [ ] NYC Safe and Sick Leave policy documented and tracked in TCP
- [ ] ESSTA (Earned Safe and Sick Time Act) — hourly accrual tracking live
- [ ] Direct deposit authorization forms signed by all employees
- [ ] Two full quarterly filings (941, NYS-45) processed via Gusto before ADP cutoff
- [ ] TCP payroll outputs match ADP outputs for 2 consecutive pay periods (reconciliation audit)

---

## SECTION 6: THE AI LAYER

### 6.1 Hermes as the Intelligence Backbone

Hermes is not a chatbot. Hermes is the operations brain. Every module in TCP generates data; Hermes is the system that reads across all of it, surfaces what matters, and acts on what can be automated.

Hermes routes to: DeepSeek-v4-pro (primary) → claude-sonnet-4-6 (fallback) → gemini-2.0-flash (fallback). High-stakes decisions route to claude-opus-4-6. All PHI is de-identified via Presidio before reaching any cloud model — Gate 1 compliance (akc_tokenizer.py) is a hard prerequisite for any PHI cloud routing.

### 6.2 AI Functions by Module

**Client Management + Billing:**
- Daily authorization expiry sweep → alert for clients with auth expiring in 30/14/7 days
- Pre-billing review: cross-check attendance against authorizations before claim submission
- Denial pattern analysis: if the same claim keeps getting denied, flag the root cause (wrong diagnosis code, wrong modifier, MCO-specific rule)
- Eligibility monitoring: check 270/271 for all active clients every Monday morning

**Scheduling:**
- Conflict detection: client scheduled on a day their authorization doesn't cover → flag before the day arrives
- Census forecasting: based on historical patterns, predict next week's attendance for kitchen planning
- Absence pattern detection: client has missed 3+ consecutive days without contact → flag for follow-up call

**Attendance:**
- Anomaly detection: client clocked in but not on today's schedule → verify manually
- Biometric failure alerts: ZK device offline → switch to manual mode, alert staff
- Real-time census dashboard: live count of clients currently in the facility

**Driver & Fleet:**
- Late van alerts: van has not left the facility by expected departure time → alert
- Route deviation alerts: van significantly off planned route → alert (geofence via GeoTab SDK)
- Drop-off confirmation: driver marks each drop-off complete on mobile → Hermes compiles nightly drop-off report (9 PM automation, already live in concept)

**HR & Payroll:**
- Overtime risk: 4 days into a week, employee projected to hit 40 hours by Friday → alert Kato Wednesday
- Schedule gap alerts: shift scheduled but no employee assigned → alert 48 hours before
- Payroll anomaly detection: this week's payroll is 15% higher than last week's average → flag for review before submission

**Menu & Nutrition:**
- Missing menu alerts: Friday 8:30 PM automation (already live) — clients without menus for next week → list + alert
- Nutrition compliance: flag clients whose selected menu items conflict with documented dietary restrictions
- OCR confidence monitoring: if scan confidence score drops below threshold → request re-scan

### 6.3 Victoria — Client Communication Layer

Victoria is TCP's outbound client communication agent, powered by Retell AI (voice) and direct SMS/Telegram integration:

- **Appointment reminders:** Automated call or SMS to clients the day before their scheduled day
- **Absence follow-up:** Client not in attendance by 10 AM → automated wellness check call
- **Authorization renewal reminders:** Client auth expiring → call to caregiver/family to initiate renewal
- **Menu reminder calls:** Clients who haven't submitted weekly menu → automated reminder

Victoria operates within HIPAA Safe Harbor — no PHI in the outbound message content, only scheduling and administrative communications. All calls logged in TCP audit trail.

### 6.4 Rexxie — Financial Monitoring

Rexxie (private lane, local-only, zero GOJ data crossover) monitors GOJ financials at the summary level:

- Weekly billing summary: total claims submitted, total collected, A/R aging
- Monthly P&L snapshot: revenue vs. labor cost vs. overhead
- Cash flow forecast: projected Medicaid reimbursements based on claim pipeline
- Anomaly alerts: collections significantly below projection → flag for Kato review

Rexxie never sees PHI. It sees financial aggregates only. The separation is enforced architecturally — Rexxie reads from a financial summary table, never from the client or billing tables directly.

---

## SECTION 7: MARKET OPPORTUNITY

### 7.1 The Industry

Adult day care (ADC) in the United States is a $4.5 billion industry serving approximately 280,000 adults daily across an estimated 4,600–5,000 programs (National Adult Day Services Association, 2024 data). The industry is:

- **Growing:** Aging population, preference for community-based vs. institutional care, Medicaid HCBS (Home and Community-Based Services) expansion under the ARP Act
- **Underserved by software:** The dominant players (Carecenta, Therap, CareVoyant, AlayaCare) are legacy systems built 10–15 years ago with minimal AI integration
- **Regulation-driven:** Medicaid billing compliance requirements mean operators cannot "just use a spreadsheet" — they need software, and they are captive to whatever works
- **Operationally complex:** Like GOJ — bilingual staff, diverse client populations, complex scheduling, transport coordination, nutrition tracking — none of the current SaaS offerings handle all of this natively

### 7.2 New York City Specifically

NYC has approximately 300+ licensed adult day care programs, concentrated in the Bronx, Brooklyn, Queens, and Staten Island. The market characteristics:

- High concentration of Russian/Eastern European, Chinese, Caribbean, and Spanish-speaking clients (same demographics as GOJ)
- Medicaid managed care is dominant — billing must handle MCO relationships (MetroPlus, Healthfirst, Fidelis, Centers Plan, etc.)
- NY state is the highest-Medicaid-spend state per capita — ADC programs are well-funded but tightly regulated
- Most programs in the 200–600 client range are on Carecenta or similar legacy software
- Most program operators are clinicians or social workers who became administrators — they are not technology buyers, but they are deeply frustrated with their current software

**TCP's sales pitch to a NYC ADC operator:** "We run a 425-client facility in Brooklyn on this platform. We built it because we were tired of paying $1,500/month for software that couldn't handle our clients' language needs, our billing complexity, or our routing logic. Now we're making it available to facilities like yours."

That is a sales pitch that works.

### 7.3 Competitive Landscape

| Competitor | Est. Price/Month | AI-Native | Medicaid Billing | Biometric Attendance | ADC-Specific |
|---|---|---|---|---|---|
| Carecenta | $800–1,500 | No | Yes | No | Yes |
| Therap | $500–2,000 | No | Limited | No | Partial |
| CareVoyant | $1,000–3,000 | No | Yes | No | Yes |
| AlayaCare | $1,500–5,000 | Partial | Yes | No | Partial |
| **Tiger Claw Platform** | **$500–2,000** | **Yes** | **Yes** | **Yes (ZK biometric)** | **Yes** |

TCP's differentiation:
1. **AI-native:** Hermes intelligence layer is baked in, not bolted on. No competitor offers real-time anomaly detection, natural language operations queries, or automated pre-billing review.
2. **Built by operators:** Every feature was first built to solve a real problem at GOJ. No theoretical feature design.
3. **Biometric-first attendance:** No competitor includes ZK biometric integration as a native module. It is always a third-party add-on.
4. **Multilingual-ready:** GOJ's Russian menu system is a template for multi-language client communication.
5. **Price-competitive:** TCP targets the same price range as Carecenta but delivers 3–5x more functionality.

### 7.4 Pricing Model

**TCP SaaS Pricing (Year 2+):**

| Tier | Clients | Monthly Price | Annual Price | Target |
|---|---|---|---|---|
| Starter | Up to 100 clients | $500/mo | $5,400/yr | Small ADC programs |
| Growth | 101–300 clients | $1,000/mo | $10,800/yr | Mid-size programs |
| Operator | 301–600 clients | $1,500/mo | $16,200/yr | Programs like GOJ |
| Enterprise | 600+ clients | $2,000+/mo | $24,000+/yr | Large multi-site programs |

**Add-on modules (priced separately):**
- ZK Biometric Setup & Support: $500 one-time + $50/month
- AI Compliance Suite (billing review, auth monitoring): $300/month
- Victoria Voice (Retell AI client calls): $200/month + per-minute usage
- Driver & Fleet Module: $200/month

### 7.5 Revenue Projections

| Year | External Clients | ARPU/Month | MRR | ARR |
|---|---|---|---|---|
| Year 1 (GOJ only) | 0 | — | $0 | $0 |
| Year 2 (first external) | 3 | $1,000 | $3,000 | $36,000 |
| Year 3 | 20 | $1,200 | $24,000 | $288,000 |
| Year 4 | 50 | $1,400 | $70,000 | $840,000 |
| Year 5 | 100 | $1,500 | $150,000 | $1,800,000 |

**These projections assume zero paid marketing.** GOJ + Kato's network in the NYC ADC community is the initial sales channel. ADC operators talk to each other at NY State DOH licensing meetings, provider association events, and Medicaid managed care coordination meetings. A working, live product running at GOJ is the demo.

---

## SECTION 8: BUILD PHASES AND TIMELINE

### Overview

```
Phase 1: Q3 2026 (Months 1–3)   — Hardware + Biometric Attendance
Phase 2: Q4 2026 (Months 4–6)   — Billing Module + Medicaid Integration
Phase 3: Q1 2027 (Months 7–9)   — GeoTab Replacement + Fleet Module
Phase 4: Q2 2027 (Months 10–12) — Payroll Module (Gusto bridge) + ADP cutoff
Phase 5: Q3–Q4 2027 (Months 13–18) — Platform hardening + first external client
Phase 6: 2028 (Months 19–24)    — SaaS launch, multi-tenant, sales motion
```

### Phase 1: Q3 2026 — Hardware + Biometric Attendance (Months 1–3)

**Goal:** Replace manual sign-in sheets with ZK biometric. This is the most visible daily improvement and the foundation for every other module.

| Week | Task | Owner | Verify |
|---|---|---|---|
| Week 1–2 | Order ZK F22 (×2), ZK MB460 (×1), test iPad | Kato | Devices received |
| Week 3–4 | Network setup: ZK devices on GOJ LAN, static IPs | Kato/Hermes | Devices respond on LAN |
| Week 5–6 | TCP `zk_attendance.py` module — poll devices every 60s | Hermes | Attendance logs in PostgreSQL |
| Week 7–8 | Client enrollment — register 425 client face IDs | Staff | 95%+ enrollment rate |
| Week 9–10 | Dashboard — real-time attendance in GOJ Dashboard | Hermes | Live attendance count visible |
| Week 10–12 | iPad fallback kiosk deployed, staff trained | Kato | Manual sign-in sheets retired |

**Deliverables:**
- ZK biometric attendance live for all 425 clients
- Employee clock-in/out via ZK (15 staff)
- Real-time attendance dashboard in GOJ Dashboard
- Old WiFi clock-in system cancelled ($600–2,400/year saved)

### Phase 2: Q4 2026 — Billing Module + Medicaid Integration (Months 4–6)

**Goal:** Shadow billing alongside Carecenta. Prove claim accuracy. Prepare for Carecenta cutoff.

| Month | Task | Verify |
|---|---|---|
| Month 4 | Availity API integration — 270/271 eligibility checks | Eligibility check for 10 test clients matches Carecenta |
| Month 4 | Client demographics module complete — full profile | All 426 records migrated from auth_tracker.db to PostgreSQL |
| Month 5 | 837P claim generation — shadow mode | TCP claims match Carecenta claims for 50 test clients |
| Month 5 | Authorization pre-billing sweep — flag expired auths | Zero claims generated for clients with EXPIRED auth |
| Month 6 | 835 ERA parsing and auto-posting | Remittance data populating correctly |
| Month 6 | 90-day parallel billing begins | Both systems running; daily reconciliation report |

**Deliverables:**
- TCP billing module generating shadow claims
- 90-day parallel period begins (Carecenta still primary)
- Authorization tracking fully automated with daily sweeps
- Target Carecenta cutoff: Month 9

### Phase 3: Q1 2027 — GeoTab Replacement (Months 7–9)

**Goal:** Build custom fleet tracking dashboard, retire GeoTab subscription.

| Month | Task | Verify |
|---|---|---|
| Month 7 | GeoTab SDK integration — pull positions to PostgreSQL | Live vehicle positions in DB |
| Month 7 | Leaflet.js map in GOJ Dashboard — real-time van locations | Map visible in dashboard |
| Month 8 | Route optimization engine — OSRM integration | Driver sheets include optimized route order |
| Month 8 | Driver assignment from scheduling module | Schedule → route sheet automated |
| Month 9 | Drop-off confirmation mobile PWA | Drivers marking each drop-off via phone |
| Month 9 | GeoTab subscription cancelled | ~$900–3,000/year saved |

**Deliverables:**
- Real-time fleet tracking in GOJ Dashboard
- Automated route optimization
- Drop-off confirmation logging
- GeoTab software subscription cancelled

### Phase 4: Q2 2027 — Payroll Module + ADP Cutoff (Months 10–12)

**Goal:** Connect biometric hours to Gusto, run two full payroll quarters, cut ADP.

| Month | Task | Verify |
|---|---|---|
| Month 10 | TCP HR Module — hours → gross pay calculation | Hours match ZK attendance logs |
| Month 10 | PTO/sick time tracking live | Accruals match NY legal requirements |
| Month 11 | Gusto API integration — first payroll run | TCP payroll matches ADP parallel run |
| Month 11 | QuickBooks sync — payroll journal entries | QBO labor entries match payroll |
| Month 12 | Second parallel payroll run → reconciliation audit | Two consecutive matches |
| Month 12 | ADP subscription cancelled | ~$3,240–8,040/year saved |

**Deliverables:**
- Payroll running through TCP → Gusto
- ADP cancelled (major cost reduction)
- QuickBooks payroll sync live
- NY compliance checklist 100% complete

### Phase 5: Q3–Q4 2027 — Platform Hardening + First External Client (Months 13–18)

**Goal:** Stabilize GOJ on full TCP stack. Onboard first external client.

| Month | Task |
|---|---|
| Month 13 | Carecenta fully offline (90-day parallel ends) — TCP is sole billing system |
| Month 13–14 | Platform hardening: load testing, error handling, backup/recovery |
| Month 14–15 | Multi-tenancy schema migration: add `facility_id` to all tables |
| Month 15 | TCP Operator Dashboard — white-labeled React frontend |
| Month 16 | Documentation: TCP admin guide, setup guide, API reference |
| Month 17 | First external client identified (NYC ADC referral network) |
| Month 18 | First external client onboarded — all modules live |

**Deliverables:**
- GOJ running 100% on TCP — zero third-party operational software
- First paying TCP client ($1,000–1,500/month MRR)
- Platform documentation complete
- Multi-tenant architecture live

### Phase 6: 2028 — SaaS Launch (Months 19–24)

**Goal:** 3–5 external clients, repeatable sales motion, clear growth trajectory.

| Quarter | Target | Milestone |
|---|---|---|
| Q1 2028 | 3 external clients | $3,000–4,500 MRR |
| Q2 2028 | 6 external clients | $6,000–9,000 MRR |
| Q3 2028 | 12 external clients | $14,000–18,000 MRR |
| Q4 2028 | 20 external clients | $24,000–30,000 MRR |

Sales strategy: NYC ADC provider associations (NYADSA), Medicaid managed care MCO relationships, direct outreach to programs on Carecenta (they are the warm lead — they know the pain), word-of-mouth from the first clients.

---

## SECTION 9: INVESTMENT REQUIRED

### 9.1 Hardware Budget (Phase 1)

| Item | Qty | Unit Cost | Total |
|---|---|---|---|
| ZK F22 Face ID Terminal | 2 | $400 | $800 |
| ZK MB460 Multi-Bio (Staff) | 1 | $350 | $350 |
| Network PoE switch (if needed) | 1 | $150 | $150 |
| iPad (refurbished, fallback kiosk) | 1 | $329 | $329 |
| Wall mounting hardware | 3 | $30 | $90 |
| **Hardware Total** | | | **~$1,719** |

*Optional Phase 3 (if replacing GeoTab hardware):*

| Item | Qty | Unit Cost | Total |
|---|---|---|---|
| Teltonika FMB920 OBD-II GPS | 4 | $85 | $340 |
| SIM cards (IoT data plan) | 4 | $10/mo | $480/yr |

### 9.2 Development Investment (Phases 1–4)

Development is performed by Kato using the existing GHS technology stack (REX FastAPI, Hermes AI, n8n). No external developers are required for Phases 1–4.

| Phase | Hours Est. | Valued At ($150/hr) | Actual Cash Cost |
|---|---|---|---|
| Phase 1: Biometric + Attendance | 80 hrs | $12,000 | $0 (internal) |
| Phase 2: Billing + Medicaid | 200 hrs | $30,000 | ~$2,000 (Availity setup, legal review) |
| Phase 3: Fleet Module | 60 hrs | $9,000 | $0 |
| Phase 4: Payroll + Gusto | 120 hrs | $18,000 | ~$1,000 (Gusto API access, testing) |
| **Totals** | **460 hrs** | **$69,000** | **~$3,000 cash** |

### 9.3 Infrastructure and Compliance

| Item | Cost | Frequency |
|---|---|---|
| Mac Mini M4 24GB (existing) | $0 | Owned |
| Cloudflare tunnel (existing) | $0 | Free tier |
| PostgreSQL (runs on Mac Mini) | $0 | Open source |
| Availity clearinghouse setup | ~$500–1,000 | One-time |
| HIPAA BAA with cloud providers | $0 | Free (AWS, Anthropic offer this) |
| Medicaid billing compliance review (healthcare attorney) | ~$2,000 | One-time |
| NY state labor law compliance review (for payroll module) | ~$1,500 | One-time |
| **Compliance Total** | **~$5,000** | |

### 9.4 Total Investment Summary

| Category | Cost |
|---|---|
| Hardware (Phase 1) | ~$1,719 |
| Development (cash only — no external devs) | ~$3,000 |
| Compliance and legal | ~$5,000 |
| Contingency (10%) | ~$1,000 |
| **Total Phase 1–4 Cash Investment** | **~$10,719** |

**Annual savings once all third-party software is replaced:**

| System Replaced | Annual Savings |
|---|---|
| Carecenta | ~$9,600–18,000 |
| GeoTab | ~$900–3,000 |
| WiFi Clock-In | ~$600–2,400 |
| ADP → Gusto | ~$3,240–8,040 |
| **Total Annual Savings** | **~$14,340–31,440** |

**Payback period:** 4–9 months depending on current spend levels.

---

## SECTION 10: RISK ANALYSIS

### 10.1 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Medicaid billing disruption during cutover | Medium | Critical | 90-day parallel run; Carecenta not cancelled until 30 consecutive days of matching claims |
| Biometric enrollment failure (elderly clients) | Medium | Medium | iPad fallback kiosk always available; manual override with audit trail; staff-assisted enrollment |
| ZK device hardware failure | Low | High | Spare ZK MB460 on hand as backup; manual sign-in sheets available within 60 seconds |
| Data migration errors (Carecenta → TCP) | Medium | High | Row-by-row reconciliation script; human review of all 426 client records post-migration |
| NY DOH compliance audit | Low | High | Document everything; TCP audit trail on every transaction; run compliance review before Phase 2 launch |
| Gusto API changes or pricing increase | Low | Medium | Payroll data owned by TCP; migrating to another provider is a 1-month integration task |
| GeoTab SDK access revocation | Low | Low | OBD-II hardware can be swapped to Teltonika in 1 week; fleet data is secondary |
| Hermes AI gateway downtime | Medium | Medium | Fallback models configured; all critical automations have manual trigger fallbacks |
| External client data breach | Low | Critical | Multi-tenant data isolation by `facility_id`; HIPAA BAA required; Presidio de-ID on all PHI paths; SQLCipher encryption on sensitive tables |
| Kato sole developer risk | High | High | Document all architecture in MASTER.md and this plan; modular design allows future developer onboarding; n8n workflows are low-code and maintainable by non-engineers |

### 10.2 Mitigation Detail: Medicaid Billing

The single highest-stakes risk is billing disruption. GOJ's cash flow depends entirely on Medicaid reimbursements. A 30-day billing failure would be catastrophic.

Mitigation protocol:
1. **TCP never touches live billing until Phase 2 shadow mode is running for 60 days**
2. **Carecenta is not cancelled until TCP shadow claims match at 99% accuracy for 30 consecutive business days**
3. **A "kill switch" is built into TCP billing module** — one command disables TCP claim submission and re-routes all billing back to Carecenta manual entry. This kill switch is tested before any live billing begins.
4. **Kato personally reviews the first 3 months of TCP-generated claims** before they are submitted, even in shadow mode
5. **Legal review of claim formats by a Medicaid billing compliance specialist** before any claims are submitted via TCP

### 10.3 Mitigation Detail: Biometric Failure

Biometric devices will occasionally fail — network issues, firmware bugs, power outages. The fallback hierarchy:

1. **ZK device unreachable:** iPad kiosk automatically activates as primary check-in method
2. **iPad kiosk fails:** Staff uses paper sign-in sheet (always available at front desk)
3. **Paper sign-in:** Manually entered into TCP at end of day by administrator
4. **Audit trail:** Every manual entry logged with who entered it and when

This hierarchy ensures attendance is never lost — the question is only how automated the capture is.

### 10.4 Mitigation Detail: Regulatory Compliance

NY DOH licenses and regulates adult day care programs. Key compliance areas:

- **Attendance documentation:** NY regulation requires contemporaneous attendance records. TCP's ZK biometric log with timestamps satisfies this requirement; the audit trail provides the contemporaneous record.
- **Authorization billing:** NY Medicaid requires a valid prior authorization before billing for ADC services. TCP's authorization pre-billing sweep directly addresses this.
- **HIPAA:** TCP extends the existing HIPAA-compliant architecture (Presidio de-ID, AES-256-GCM storage, audit logs, RBAC). HIPAA BAA will be in place with all cloud providers before Phase 2.
- **NY DOH inspection readiness:** TCP's reporting module will include a "DOH Inspection Pack" — one-click export of all documentation a DOH inspector would request (census, authorization status, attendance records, billing summaries).

### 10.5 Mitigation Detail: Single Developer Risk

Kato is the sole developer, architect, and operator of this platform. This is simultaneously TCP's greatest strength (no coordination overhead, architectural consistency) and its greatest risk (bus factor = 1).

Mitigations:
- **CLAUDE.md and MASTER.md** maintain complete system documentation. Any competent FastAPI developer can be onboarded in 1–2 weeks.
- **n8n workflows** are visual and maintainable by non-engineers. The daily automation does not require developer intervention to operate.
- **Modular architecture** means each module (billing, attendance, fleet) can be maintained independently. A failure in one does not cascade to others.
- **Phase 5 target:** By Month 18, if TCP has its first external client, hiring one part-time developer becomes justifiable and funded.

---

## APPENDIX A: TECHNOLOGY REFERENCE

### ZK BioTime 8.0 API Quick Reference

```python
# Device discovery and health check
import requests

ZK_IP = "192.168.1.100"  # Static IP on GOJ LAN
ZK_PORT = 80

def zk_health_check():
    r = requests.get(f"http://{ZK_IP}:{ZK_PORT}/iclock/cdata")
    return r.status_code == 200

# Pull attendance logs (run every 60 seconds)
def pull_attendance_logs(serial_number: str, from_timestamp: str):
    params = {
        "SN": serial_number,
        "table": "ATTLOG",
        "Stamp": from_timestamp  # ISO 8601
    }
    r = requests.get(f"http://{ZK_IP}:{ZK_PORT}/iclock/cdata", params=params)
    return parse_attlog(r.text)

# Parsed format: employee_id, timestamp, verify_type, status
# verify_type: 1=fingerprint, 4=face, 15=manual
```

### PostgreSQL Migration from SQLite

```sql
-- Core schema additions for TCP (extending auth_tracker.db)
ALTER TABLE clients ADD COLUMN facility_id INTEGER DEFAULT 1;
ALTER TABLE authorization ADD COLUMN facility_id INTEGER DEFAULT 1;
ALTER TABLE menus ADD COLUMN facility_id INTEGER DEFAULT 1;

-- New tables for TCP
CREATE TABLE attendance_biometric (
    id SERIAL PRIMARY KEY,
    facility_id INTEGER NOT NULL,
    client_id INTEGER REFERENCES clients(id),
    employee_id INTEGER REFERENCES employees(id),
    zk_device_id VARCHAR(50),
    verify_type SMALLINT,  -- 1=fingerprint, 4=face, 15=manual
    clock_in TIMESTAMPTZ,
    clock_out TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE payroll_periods (
    id SERIAL PRIMARY KEY,
    facility_id INTEGER NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    gusto_run_id VARCHAR(100),
    status VARCHAR(20),  -- pending, submitted, processed
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE fleet_positions (
    id SERIAL PRIMARY KEY,
    facility_id INTEGER NOT NULL,
    vehicle_id VARCHAR(50),
    geotab_device_id VARCHAR(50),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    speed_kmh DECIMAL(5, 1),
    recorded_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE claims (
    id SERIAL PRIMARY KEY,
    facility_id INTEGER NOT NULL,
    client_id INTEGER REFERENCES clients(id),
    service_date DATE NOT NULL,
    claim_type VARCHAR(10),  -- 837P, 837I
    status VARCHAR(20),      -- draft, submitted, accepted, denied, paid
    clearinghouse VARCHAR(50),
    claim_reference VARCHAR(100),
    amount_billed DECIMAL(10, 2),
    amount_paid DECIMAL(10, 2),
    denial_reason TEXT,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Gusto Payroll API Quick Reference

```python
import httpx

GUSTO_BASE = "https://api.gusto.com/v1"
GUSTO_TOKEN = "..."  # OAuth2 access token, stored in macOS Keychain

async def create_payroll_run(company_id: str, period_start: str, period_end: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GUSTO_BASE}/companies/{company_id}/payrolls",
            headers={"Authorization": f"Bearer {GUSTO_TOKEN}"},
            json={
                "pay_schedule_id": "...",
                "start_date": period_start,
                "end_date": period_end
            }
        )
        return r.json()

async def submit_hours(payroll_id: str, employee_id: str, hours: float):
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{GUSTO_BASE}/payrolls/{payroll_id}/employees/{employee_id}",
            headers={"Authorization": f"Bearer {GUSTO_TOKEN}"},
            json={"hours": hours}
        )
        return r.json()
```

---

## APPENDIX B: DECISION LOG

| Date | Decision | Rationale |
|---|---|---|
| June 2026 | Use Gusto API as payroll bridge (not build raw payroll) | Tax compliance complexity requires 2+ years to build safely; Gusto API-first design is built for this exact use case |
| June 2026 | Keep GeoTab hardware, replace software layer | GeoTab GO9 devices are already installed and owned; replacing software is 6 weeks of work; replacing hardware requires vehicle downtime |
| June 2026 | Use Availity for 270/271 eligibility, Change Healthcare for claim submission | Different MCOs prefer different clearinghouses; supporting both ensures broadest compatibility |
| June 2026 | 90-day parallel billing before Carecenta cutoff | GOJ cannot afford a billing failure; 90 days of shadow claims provides statistical confidence before cutover |
| June 2026 | ZK F22 (face ID) for clients, ZK MB460 (fingerprint+card) for staff | Elderly clients prefer touch-free; staff need speed and backup card option |
| June 2026 | Multi-tenancy via `facility_id` column, not separate databases | Schema-level isolation is simpler to build, easier to query across; separate databases create operational complexity at scale |

---

## APPENDIX C: KEY CONTACTS AND VENDOR ACCOUNTS

| Vendor | Account Type | Contact / URL | Status |
|---|---|---|---|
| Carecenta | Active license | support@carecenta.com | Cancel Month 9 |
| GeoTab | Active subscription | fleet.geotab.com | Cancel Month 9 |
| ADP | Active payroll | adp.com/admin | Cancel Month 12 |
| Availity | Clearinghouse API | availity.com/developer | To set up Month 4 |
| Change Healthcare | Clearinghouse | changehealthcare.com | To evaluate Month 4 |
| Gusto | Payroll API | gusto.com/developer | To set up Month 10 |
| ZK Technologies | Hardware vendor | zkteco.us | Order Month 1 |
| Plaid | ACH/Banking API | plaid.com | Evaluate Month 11 |
| Retell AI | Voice AI (Victoria) | retellai.com | Evaluate Phase 5 |

---

## DOCUMENT CONTROL

| Field | Value |
|---|---|
| Document ID | CC_GHS_AUTONOMOUS_BUILD_PLAN.md |
| Version | 1.0 |
| Created | June 4, 2026 |
| Author | Hermes (Kato, Chairman) |
| Classification | Confidential — Internal Only |
| Next Review | September 1, 2026 (Phase 1 completion) |
| Source of Truth | ~/Desktop/Gold_Health_Systems/BRAIN/MASTER.md |

---

*Tiger Claw Platform is a Gold Health Systems proprietary build. All architectures, timelines, and financial projections are internal documents. Not for distribution outside GHS leadership.*

---
**END OF DOCUMENT**
*CC_GHS_AUTONOMOUS_BUILD_PLAN.md · v1.0 · 1,127 lines*
