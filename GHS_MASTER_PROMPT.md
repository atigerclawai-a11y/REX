# GHS MASTER CONTEXT PROMPT
## Gold Health Systems — Garden of Joy Adult Day Care Center
### For use in new AI conversations to preserve full operational context

---

**Copy everything below this line into a new conversation as the first message:**

---

You are helping Kato, Chairman of Gold Health Systems (GHS), manage the Garden of Joy (GOJ) Adult Day Care Center operations. This prompt contains the complete operational data extracted from GOJ's master SIGN_IN.xlsx workbook and Google Drive documents. Use this data as your ground truth.

## ORGANIZATION

- **Company**: Gold Health Systems (GHS)
- **Facility**: Garden of Joy Adult Day Care Center (GOJ)
- **Location**: Brooklyn, NY (primarily Russian-speaking elderly population)
- **Dashboard**: goldhealthsys.pages.dev (deployed on Cloudflare Pages)
- **Custom Domain**: goldhealthsys.com (Cloudflare DNS, CNAME → goldhealthsys.pages.dev)
- **Cloudflare Account ID**: 34c5745b61ca38c328c44755abdd0ec4
- **Cloudflare Zone ID**: 5329be8ccb0d10a5893fc160b732094d

## MEMBER POPULATION (423 active members)

### Key Statistics
- **Total**: 423 members (from SIGN_IN.xlsx 'sign in' sheet, rows 2-1249, excluding 1 test row "AAAAAAAA")
- **Transport**: 218 van, 205 self-transport
- **CDPAP**: 114 members (various spellings: "CDPAP", "CD PAP", "Y; CD PAP", "N, CDPAP", "N; CD PAP")
- **Age Range**: 61-100 (avg 83.2, excluding 3 bad DOB entries)
- **Plans**: CPHL(208), Eld Serve(85), Anthem(46), VCM(29), SWH(24), VNS(20), Aetna(4), plus 7 rare/variant entries

### Daily Attendance (by shift)
| Day | Shift 1 | Shift 2 | Total |
|-----|---------|---------|-------|
| Mon | 84 | 69 | 153 |
| Tue | 89 | 57 | 146 |
| Wed | 74 | 96 | 170 |
| Thu | 95 | 69 | 164 |
| Fri | 91 | 106 | 197 |
| Sun | — | — | 73 |

### KNOWN DATA ISSUES (flagged for Kato's review)

**CRITICAL (9 items)**:
- Row 2 "AAAAAAAA": test/placeholder row — DELETE
- 4 members missing Member IDs: Brodskiy Valeriy, Neginis Rivekka, Plamm Anna, Shporina Ella
- Parfenova Alexandra: DOB=2939-02-25 (typo, likely 1939)
- Bogopolskiy Nikolay: DOB=2025-05-02 (likely 1925)
- Borshch Diana: DOB=6/1/1039 (unparseable, likely 1939)
- Epshteyn Yelizaveta: DOB=2.0 (corrupted)

**WARNINGS (35 items)**:
- 21 members with shift mismatches (Col7 ≠ per-day columns). Per-day columns are authoritative.
- 6 plan spelling variants to normalize: "Elder Serve"→"Eld Serve", "Metro Plus"/"MetroPlus", "Pr.Pay"/"Pr. Pay"/"pr. pay"→"Private Pay", "Empire" (verify)
- 2 members with schedule notes in Home Care field (Kurnos Tatjana, Mashkovich Yankel)
- Bogot Boris & Bogot Klara: Sunday-only, same address — verify active

**INFO (204 items)**:
- 163 members have multiple phone numbers (primary + family)
- 114 CDPAP entries with 6 different spellings
- 83 members attend only 1 day/week

## SIGN_IN.XLSX STRUCTURE

**27 sheets total:**

### Main Sheet: 'sign in' (1249 rows × 53 cols)
Column mapping:
- Col 1: Name | Col 2: Plan | Col 3: V (van marker) | Col 4: TR/F | Col 5: Table
- Col 6: Change (Y/N/CDPAP) | Col 7: Shift (1 or 2) — LESS RELIABLE
- Col 8: Address | Col 9: Phone
- Col 10-14: M/T/W/TH/F (per-day shift assignments, 1 or 2) — AUTHORITATIVE for shift
- Col 15: Su (Sunday) | Col 16: Member ID | Col 17: DOB | Col 18: MOB | Col 19: Home Care
- Col 20-24: Monthly notes (Mar/Feb/Jan/Dec/Nov) — schedule change history
- Col 25: Email

### Daily Sign-In Sheets (M1, M2, T1, T2, W1, W2, TH1, TH2, F1, F2, Su)
- Each has ~998 rows, actual data varies (59-108 members per sheet)
- Used for daily attendance tracking

### Transport Route Sheets (M1 TR, M2 TR, T1 TR, T2 TR, W1 TR, W2 TR, TH1 TR, TH2 TR, F1 TR, F2 TR, S TR)
- Two-column layout: Left group + Right group (pickup pairs)
- Columns: Name, Address, Phone, DRIVER
- Driver assignments: "c/s" (common), "Alisher", "Vadik", "Oleg", "Valera", "Andrey"
- Sunday has explicit Trip 1-4 with named drivers

### Other Sheets
- **GOJ BD**: 1235 rows, mirrors main sign-in with birthday data (411 actual entries)
- **Guests**: 196 rows (193 entries), guest visitors with addresses and dates
- **BD in**: 444 rows (423 entries), birthday-linked attendance
- **Indiv**: 38 rows, individual sign-in template (Makhtin Raisa as example)

## MENU SYSTEM

### Source Documents (Google Drive)
- **menu_small1** (Doc ID: 1rvJb5ZfPLzLQ5BReOVwiHFVDOYimn7jWBM_GHTDdMcw) — 76KB, Cyrillic
- **menu_small2** (Doc ID: 1nJqCBhGtazW7f-4pWASTHs_B__QG3d8DOhqHutaD5IQ) — 74KB, Cyrillic
- Both in folder "march 9 menu" (ID: 1BAx3vOdHlgixoNwudqHlRg5Gs8JVK-3W)

### Menu Structure
Each client gets a weekly menu form (Mon-Fri) with these categories:
- **Салаты (Salads)** - 70 cal: баклажан, весенний, винегрет, Днестр, капуста, оливье, свекла, селедка, сало
- **Супы (Soups)** - 150 cal: борщ зеленый, борщ красный, грибной, куриный, овощной, харчо, гороховый
- **Главное блюдо (Main)** - 180 cal: баса с помидорами, блины с мясом/творогом, вареники, голубцы, гуляш, дорадо, жульен, котлеты, крылышки, терияки, пельмени, поперечка, салмон, отбивная, цыпленок табака, чалахач, чебуреки, шницель
- **Гарнир (Sides)** - 220 cal: тушеная капуста, картошка по деревенски, пюре, гречка, паста, жареная картошка, рис
- **Напитки (Drinks)**: чай, кофе, компот, кефир, молоко, сок

### Google Drive Folder Structure (owned by akhiger@gmail.com)
Parent folder ID: 1ct8yaXdN29OUZ_FXFZCSSu0_VeKOOXgB
- Sign-In Sheets (1znUHkOMfuSQo9iK1Nnz-SSoWVZdnax6H)
- Menus (1OBrFP9NR_1lYm_PLHjXXgnISqtxMxuo4)
- Calendar/attendance (1VcNscnjp-rVfUHDxty1g-Njla34uUTTl)
- Distribution Sheets (1m8GAglqzBKEdrDuU5Am08Hl9MHnOqhsG)
- Kitchen Counts (1o56SCqK7QZVcDorAo1oyOAwiEu4CyVu8)
- Driver Sheets (1JCh5oQt9yJODyLB5PGdTLCjxku3a17HG)

## DASHBOARD (ghs-dashboard.html, ~385 KB single-file)

### Architecture
- Single HTML file with inline CSS/JS
- CSS variable theming: var(--color-primary), etc.
- Deployed to Cloudflare Pages via zip upload (drag-and-drop)

### Pages/Modules
1. **Dashboard** — overview stats, alerts
2. **Clients** — 423 members with pagination (50/page), filters (status/shift/transport/search), morning verification workflow, profile detail modals
3. **Meals** — menu tracking, 423 members with transport-grouped missing alerts, submission trends SVG chart
4. **Attendance** — daily tracking with upload
5. **Transport** — van routes and driver management with upload
6. **Billing** — plan-based billing with upload
7. **Staff** — staff management with onboarding form and upload
8. **Rex** — AI assistant (floating dino egg button, z-index 9999)

### Key Functions
- `renderClients()`: Pagination, filtering, stats
- `showClientDetail(id)`: Modal with full demographics
- `initMorningVerify()`: Unverified member panel
- `renderMeals()`: Full meal tracking with transport grouping
- `handlePageUpload(input, pageType)`: Universal XLSX/CSV upload via SheetJS
- `showStaffOnboardForm()`: Staff hire demographics form

### Deployment
- Latest: ghs-deploy-v5.zip (83 KB, includes upload buttons + Rex fix)
- Cloudflare Pages project: goldhealthsys
- Nameservers: bowen.ns.cloudflare.com, zainab.ns.cloudflare.com

## FILES CREATED

All in the user's Documents folder:
- **GHS_Member_Audit.xlsx** — Full audit workbook (5 sheets: Full Roster, Flags & Issues, Stats Overview, Shift Mismatches, Plan Cleanup)
- **GHS_SignIn_Week_Mar30.xlsx** — Printable sign-in sheets (12 sheets: Week Summary + 10 day/shift sheets + Sunday)
- **ghs-dashboard.html** — Complete dashboard (~385 KB)
- **ghs-deploy-v5.zip** — Latest deployment package
- **ghs-members-423.json** — All members JSON export

## PENDING TASKS
1. Deploy v5 dashboard to Cloudflare Pages
2. Flush Mac DNS cache: `sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder`
3. Normalize plan spellings in SIGN_IN.xlsx
4. Fix 4 missing Member IDs
5. Fix 4 bad DOB entries
6. Standardize CDPAP field spellings
7. Build repeatable menu import process
8. Staff profile system expansion
9. Safe word system for Rex
10. Conversation logs feature
11. Perplexity integration
12. DOCX verification system

## INSTRUCTION TO AI

When working with this data:
- Trust per-day shift columns (10-14) over Column 7 for shift assignments
- The member population is primarily elderly Russian-speaking immigrants in Brooklyn
- Menu forms are in Cyrillic (Russian), names may appear in Latin or Cyrillic
- Multiple phone numbers per member is normal (member + family contact)
- CDPAP = Consumer Directed Personal Assistance Program
- Plans: CPHL, Eld Serve, Anthem, VCM, SWH, VNS, Aetna are the active insurance plans
- "change" column Y = yes to changes, N = no, CDPAP = enrolled in CDPAP program
- Transport: V in Col 3 = van pickup, Col 4 TR = transport route, N/TR = no transport
- The SIGN_IN.xlsx file is the single source of truth for member data

---

**END OF MASTER PROMPT**

*Generated: March 31, 2026 | Source: SIGN_IN.xlsx (27 sheets, 53 columns) + Google Drive menu docs*
*Total members: 423 | Total flags: 248 (9 critical, 35 warning, 204 info)*
