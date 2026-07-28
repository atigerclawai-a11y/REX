# 837 Claim Generator — Kato Activation Checklist

**Status (2026-07-27):** Generator COMPLETE, selftest passes, payer layer fully configured
from the HHAX e-billing export. Dry-run July 2026: **5,273 claims / $320,590 / 339 clients**.
**Only 2 values remain — both from Kato.**

**File:** `CC_medicaid_837_generator.py`
**Env file:** `~Desktop/REX/.env.837`

---

## ✅ Configured (14 values — incl. 6 filled 2026-07-27 from CC_billing_payers.py ground truth)

| Env Var | Value | Source |
|---------|-------|--------|
| `CC837_NPI` | 1124475900 | ✅ Kato |
| `CC837_STATE` / `CC837_CITY` | NY / BROOKLYN | ✅ Kato |
| `CC837_TAXONOMY` | **251E00000X** | ✅ Fixed 2026-07-27 (was 363A00000X — Physician Assistant, WRONG) |
| `CC837_PAYER_NAME` / receiver IDs | NYS MEDICAID / AVAILITY | ✅ Kato |
| `CC837_LEGAL_NAME` | GOJ INC DBA GARDEN OF JOY SADC | ✅ GOJ_IDENTITY |
| `CC837_ADDR1` / `CC837_ZIP` | 4120 OCEAN AVE / 11235 | ✅ GOJ_IDENTITY |
| `CC837_SUBMITTER_ETIN` / `CC837_ISA_SENDER_ID` / `CC837_GS_SENDER` | 725850 / AV09311993 / 725850 | ✅ AVAILITY_BASE (were listed as "Kato must supply" — already in code) |

## ✅ Payer layer (fixed 2026-07-27 from auth_tracker.insurance_payers HHAX export)

| Fix | Detail |
|-----|--------|
| Elderserve payer_id | `05178` + **routing corrected to MDOn-Line** (was Availity — would have rejected) |
| VNS payer_id | `77073` |
| SWH + SWH_Tele payer_id | `SWHNY` |
| Centers_Plan payer_id | `45302` (CPHL folded into Anthem Mar 2026) |
| MetroPlus routing | **Corrected to MDOn-Line** (payer_id still needed — not in export) |
| 5 aliases added | 'VillageCare' (27 auths), 'ElderServe — Riverspring Health' (87 clients), 'MetroPlus Health', 'Empire BlueCross BlueShield', 'village care' |

## ❌ Kato Must Supply (only 2 left)

| # | Env Var | What It Is | Where To Find It |
|---|---------|-----------|------------------|
| 1 | `CC837_TAX_ID` | GOJ's EIN (XX-XXXXXXX) | IRS EIN letter or W-9 — **this one value unblocks all 12 payers** |
| 2 | `CC837_BILLING_PHONE` | GOJ billing/office phone | Office |

(`CC837_PAYER_ID` env default optional — real payer IDs are per-plan in CC_billing_payers.py.)

## Remaining flags (from July dry-run warnings)
- **MetroPlus payer_id** — not in HHAX export; check e-billing screen (2 auths affected)
- **Molina** (5 auths) — no payer config; confirm whether Molina bills via SWH (SWHNY) or separately
- **Aetna Better Health payer_id** — e-billing not configured in HHAX (3 clients)
- Clients with `UNKNOWN`/NULL plans (4) — data quality, needs plan assignment

## How To Activate
1. Fill the 2 values in `.env.837`
2. Run selftest: `python3 CC_medicaid_837_generator.py --selftest`
3. Preview any month in the 💳 Billing tab on http://localhost:8200/billing (dry-run, never submits)
4. Real claim generation unlocks when EIN is set

---

## ✅ Already Configured

| Env Var | Value | Status |
|---------|-------|--------|
| `CC837_NPI` | Real NPI | ✅ Set |
| `CC837_STATE` | NY | ✅ |
| `CC837_CITY` | BROOKLYN | ✅ |
| `CC837_TAXONOMY` | 363A00000X | ✅ |
| `CC837_PAYER_NAME` | NEW YORK STATE MEDICAID | ✅ |
| `CC837_RECEIVER_ID` | AVAILITY | ✅ |
| `CC837_ISA_RECEIVER_ID` | AVAILITY | ✅ |
| `CC837_GS_RECEIVER` | AVAILITY | ✅ |

---

## ❌ Kato Must Supply

Edit `~/Desktop/REX/.env.837` and fill in:

| # | Env Var | What It Is | Example | Where To Find It |
|---|---------|-----------|---------|-----------------|
| 1 | `CC837_LEGAL_NAME` | GOJ's legal business name | `GARDEN OF JOY ADULT DAY CARE LLC` | Business registration docs |
| 2 | `CC837_TAX_ID` | GOJ's Tax ID / EIN | `XX-XXXXXXX` | IRS EIN letter or W-9 |
| 3 | `CC837_ADDR1` | GOJ's service address | `123 MAIN ST` | Physical location |
| 4 | `CC837_ZIP` | GOJ ZIP code | `112XX` | Physical location |
| 5 | `CC837_BILLING_PHONE` | GOJ billing phone | `718XXXXXXX` | Office phone |
| 6 | `CC837_SUBMITTER_ETIN` | Availity submitter ID | Assigned by Availity | Availity portal → account settings |
| 7 | `CC837_ISA_SENDER_ID` | ISA interchange sender ID | Assigned by Availity | Availity EDI enrollment docs |
| 8 | `CC837_GS_SENDER` | GS application sender code | Assigned by Availity | Availity EDI enrollment docs |

---

## Insurance Payers — Mark Complete

9 payers exist in `auth_tracker.db.insurance_payers`. All have `complete=0` (blocked from claim generation). For each MLTC/Medicaid plan that's active:

```sql
UPDATE insurance_payers SET complete = 1 WHERE plan_name = 'VillageCare MAX';
```

**Current payers and status:**

| Payer | Complete? | Billable? | Active? |
|-------|-----------|-----------|---------|
| Anthem | ❌ 0 | ✅ | ✅ |
| VillageCare MAX | ❌ 0 | ✅ | ✅ |
| ElderServe — Riverspring Health | ❌ 0 | ✅ | ✅ |
| Senior Whole Health | ❌ 0 | ✅ | ✅ |
| Aetna Better Health | ❌ 0 | ✅ | ✅ |
| VNS Health | ❌ 0 | ✅ | ✅ |
| MetroPlus Health | ❌ 0 | ✅ | ✅ |
| Private Pay | ❌ 0 | ❌ | ✅ |
| Empire BlueCross BlueShield | ❌ 0 | ✅ | ✅ |

---

## How To Activate

1. Fill in the 8 missing env vars in `.env.837`
2. Mark active payers as `complete = 1` in the DB
3. Run selftest to confirm: `python3 CC_medicaid_837_generator.py --selftest`
4. Test with synthetic data first: `python3 CC_medicaid_837_generator.py --test-edi`
5. Once all env vars are set, real claim generation is unlocked

---

## What Happens After

1. G3 Pro biometric punch → `attendance_log`
2. `authorization` validates the client is authorized for that day
3. `CC_medicaid_837_generator.py` creates an 837P claim from the attendance + authorization data
4. Claim is written to `claims_837` table
5. `CC_rex_edi.py` validates the X12 format
6. Claim is submitted to Availity clearinghouse
7. `payments_835` receives remittance (payment/denial) back
8. Vlad's dashboard shows live: Submitted → Paid → Denied pipeline
