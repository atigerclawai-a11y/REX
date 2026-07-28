# Attendance Log Audit — 2026-06-08

**Summary (one line):** Drive ingest of 2,015 `absent` rows created 45 cross-source conflicts (mostly absent-vs-scheduled inside the 2026-04-01..04-09 window) plus 19 pure same-status duplicates — manageable, but the parser also escaped 25 "минус" header-row artifacts and ~15 ALL-CAPS name dupes that need cleanup before any dedup runs.

## Headline numbers

| Metric | Value |
|---|---|
| Total rows | 10,848 |
| Distinct dates | 152 (2026-01-02 → 2026-12-31) |
| Distinct clients (raw) | 502 |
| Duplicate (date, client) pairs | 62 (45 cross-status + 19 same-status; pair count) |
| Orphan client_names (not in `clients`) | 73 distinct / 156 rows |
| New-ingest rows (`source=system`, `status=absent`) | 2,015 |
| New-ingest rows landing AFTER old pipeline cutoff (>2026-04-26) | 952 (forward-scheduled, no overlap risk) |
| New-ingest rows landing INSIDE old-pipeline era (≤2026-04-26) | 1,063 (this is the overlap surface) |

## Source distribution

| source | rows | first_date | last_date |
|---|---|---|---|
| calendar_2026_xlsx | 8,122 | 2026-01-02 | 2026-04-09 |
| system (new Drive ingest) | 2,015 | 2026-01-02 | 2026-12-31 |
| ocr_signin | 662 | 2026-03-31 | 2026-04-03 |
| telegram | 22 | 2026-03-25 | 2026-03-30 |
| registry_signin | 15 | 2026-04-24 | 2026-04-24 |
| manual_review | 4 | 2026-04-24 | 2026-04-24 |
| manual | 4 | 2026-04-23 | 2026-04-26 |
| backfill JSON | 4 | 2026-03-20 | 2026-03-20 |

## Per-date histogram (2026-04-20 → 2026-05-05)

| log_date | rows | statuses | sources |
|---|---|---|---|
| 2026-04-20 | 25 | absent | system |
| 2026-04-22 | 14 | absent | system |
| 2026-04-23 | 16 | absent | manual, system |
| 2026-04-24 | 37 | attended, absent | registry_signin, manual_review, system |
| 2026-04-26 | 3 | absent | manual |
| 2026-04-27 | 19 | absent | system |
| 2026-04-28 | 7 | absent | system |
| 2026-04-29 | 21 | absent | system |
| 2026-04-30 | 14 | absent | system |
| 2026-05-01 | 18 | absent | system |
| 2026-05-04 | 17 | absent | system |
| 2026-05-05 | 20 | absent | system |

**Reading:** Only 2026-04-23 and 2026-04-24 actually see the old+new pipelines overlap. From 2026-04-27 onward, only the new `system` ingest writes — clean territory.

## Dedup candidates — cross-status conflicts (45 pairs)

Sample (all in the 2026-04-01..04-03 window where `calendar_2026_xlsx` + `ocr_signin` overlap with new `system` absents):

| log_date | client_name | new_status | old_status | new_source | old_source |
|---|---|---|---|---|---|
| 2026-04-01 | Gritshevsky Yosef | absent | scheduled | system | ocr_signin |
| 2026-04-01 | Minogina Ninel | absent | scheduled | system | ocr_signin |
| 2026-04-01 | Shteyman Faina | absent | scheduled | system | ocr_signin |
| 2026-04-02 | Bekerman Alla | absent | scheduled | system | ocr_signin |
| 2026-04-02 | Likhtenshteyn Milya | absent | scheduled | system | ocr_signin |
| 2026-04-03 | Zlotsky Yulia | absent | attended | ocr_signin | calendar_2026_xlsx |
| 2026-04-03 | Khazenfus Rima | absent | scheduled | calendar_2026_xlsx | ocr_signin |
| 2026-04-24 | Matanseva Ofelia | attended | absent | registry_signin | system |

Breakdown of the 45 cross-status pairs:
- `scheduled` (old) vs `absent` (new): 22
- `attended` (old) vs `absent` (new): 21
- `absent` (old) vs `attended` (new): 2

## Same-status duplicates (19 pairs)

Both rows = `absent`, both `source=system`. These are pure duplicates from the Drive ingest itself (re-runs / repeated rows in the spreadsheet). Examples:

| log_date | client_name | n |
|---|---|---|
| 2026-12-26 | Zlotsky Yulia | 2 |
| 2026-12-26 | Stepankovskaya Maya | 2 |
| 2026-12-19 | Stepankovskaya Maya | 2 |
| 2026-12-12 | Stepankovskaya Maya | 2 |
| 2026-05-08 | Ratner Alla | 2 |
| 2026-04-10 | Minogina Ninel | 2 |

## Anomalies

### Parser artifact — date-header rows captured as client_name (25 distinct, 27 rows)

Russian word "минус" (= "minus"). These are spreadsheet header/total rows the parser misread as people:

```
"5/10  Sunday минус", "4/21Tuesday, 1st shift минус",
"12/14  Sunday минус", "3/15   Sunday минус", ...
```

All are `status=absent`, `source=system`. **Parser fix did NOT catch these.**

### ALL-CAPS name dupes (~15)

Same person, two casings (both will appear as separate clients in reports):
`BELOTSERKOVSKIY ROMA` / `Belotserkovsky Roma`, `CONIGLIO VERA` / `Coniglio Vera`, `MATANSEVA OFELIA` / `Matanseva Ofelia`, `SHIFRINA MARGARITA`, `STARIKOV YEVGENIY`, `VERBITSKAYA SVETLANA`, etc. Eight have an exact case-folded match in `clients`; the rest are orphans entirely (`YAKOBSON LYUSA`, `ZAKRZHEVSKAYA GALYNA`, `KUTSENKO LARISA`, `GRITSHEVSKIY`, `ZOLOTAREV`, `RYABKOVA`).

### Reason-as-name escapees (parser fix DID NOT fully work)

These rows have a free-text reason sitting in `client_name`:

- `"I have 68 at the list new system has 63"`
- `"Misha said that just h/attendant came"`
- `"added"`, `"to be added"`, `"kharats"`

### Single-name orphans (likely truncated)

`Borshevskaya`, `Krasnik`, `Krol`, `Rodova`, `GRITSHEVSKIY`, `ZOLOTAREV`, `RYABKOVA`, `yarina` — first-name-only or last-name-only entries, no match in `clients`.

## Recommended SQL (DO NOT execute — for Kato review)

All read-only counts above. Two policy choices below; pick one before running anything.

### Policy A — "Old wins on conflict, dedup new same-status"

The old pipeline saw real sign-ins; the Drive absent list is a cross-check, not an override.

```sql
-- A1. Cross-status: when same (log_date, client_name) has an absent + present/attended/scheduled,
--     DELETE the absent (only when sources differ — protect manual entries).
DELETE FROM attendance_log
WHERE id IN (
  SELECT a.id
  FROM attendance_log a
  JOIN attendance_log o
    ON a.log_date = o.log_date AND a.client_name = o.client_name AND a.id != o.id
  WHERE a.status = 'absent'
    AND a.source = 'system'
    AND o.status IN ('attended','present','scheduled')
);

-- A2. Same-status dupes: both 'absent', both source=system. Keep MIN(id), drop rest.
DELETE FROM attendance_log
WHERE id IN (
  SELECT a.id FROM attendance_log a
  JOIN attendance_log o
    ON a.log_date = o.log_date AND a.client_name = o.client_name AND a.id > o.id
  WHERE a.status = o.status AND a.source = 'system' AND o.source = 'system'
);
```

### Policy B — "Drive absent always wins" (NOT recommended)

Only if Yelena's spreadsheet is now the source of truth retroactively. Mirror A1 but delete the `attended`/`scheduled` side instead. Risky — would erase real `ocr_signin` evidence.

### Anomaly cleanup (independent of policy)

```sql
-- B1. Drop "минус" header artifacts (27 rows total).
DELETE FROM attendance_log
WHERE client_name LIKE '%минус%';

-- B2. Drop reason-as-name escapees.
DELETE FROM attendance_log
WHERE client_name IN (
  'I have 68 at the list new system has 63',
  'Misha said that just h/attendant came',
  'added', 'to be added', 'kharats'
);

-- B3. ALL-CAPS dedup — collapse to canonical case from `clients`. Run a SELECT first
--     to preview the mapping before any UPDATE.
SELECT a.client_name AS bad, c.name AS canonical, COUNT(*) AS rows_to_update
FROM attendance_log a
JOIN clients c ON LOWER(a.client_name) = LOWER(c.name) AND a.client_name != c.name
GROUP BY a.client_name, c.name;
```

Order to run (when Kato approves): B1 → B2 → B3-preview → A1 → A2.
