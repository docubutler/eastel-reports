# Query Notes — report-generation-postgres

Living reference for writing report queries. **Append new findings as they are
discovered** — add to the relevant section and drop a line in the Change log at
the bottom. Do not rewrite history; correct it in place and note the correction.

Last updated: 2026-09-11

---

## 1. Confirmed tables & key columns

| Table | Role | Key columns |
|---|---|---|
| `iot_portal_tb_usage_log` | Usage-level records | `usage_log_id` (PK), `msisdn`, `sim_service_plan_id`, `last_grant_sim_service_plan_id`, `rat_type`, `roaming_destination_id`, `roaming_mccmnc`, `usage_unit`, `act_usage_unit`, `usage_start_time`, `last_grant_sim_service_plan_detail_id`, `last_grant_sim_service_plan_bucket_id` |
| `iot_portal_tb_request_log` | CDR-level records | `request_log_id`, `req_type`, `req_time`, `msisdn`, `sim_service_plan_id`, `rat_type`, `roaming_destination_id`, `update_used_volume`, `act_update_used_volume`, `rating_group` |
| `iot_portal_tb_sim_service_plan` | **SIM service plan instance** — this is where the package name lives | `sim_service_plan_id` (**PK**), `service_plan_id`, `service_plan_code`, `service_plan_desc`, `each_quota`, `unit`, `volume`, `tier0_speed`, `bundle_code`, `bundle_type`, `sim_id`, `sim_master_id` |
| `iot_portal_tb_roaming_destination` | Roaming network / country ref | `roaming_destination_id` (PK), `roaming_destination_name`, `country`, `mcc`, `operator` |
| `iot_portal_tb_country` | Country ref | — |
| `smsc_record_parsed` | SMSC records | — |

Variants also seen in queries: `iot_portal_tb_usage_log_rep` (reporting copy).

### ⚠️ Request-log index gap — why month-wide `count(DISTINCT msisdn)` hangs

`iot_portal_tb_request_log` is indexed on `req_time` **only**:

```sql
CREATE INDEX iot_portal_tb_request_log_req_time_idx
    ON public.iot_portal_tb_request_log USING btree (req_time ASC NULLS LAST);
```

`msisdn` is in **no** index on this table. So a month-wide
`count(DISTINCT msisdn)` with a range on `req_time` must fetch **every row in
the window** from the heap before de-duplicating. The index makes locating the
range fast; it does nothing for reading a month of CDRs (tens of millions of
rows). Observed: a 2026-08 window ran **> 1 hour** without returning.

Fix — covering index, then index-only scan becomes possible:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS iot_portal_tb_request_log_req_time_msisdn_idx
    ON public.iot_portal_tb_request_log (req_time, msisdn);

VACUUM (ANALYZE) public.iot_portal_tb_request_log;  -- visibility map for index-only scan
```

`CONCURRENTLY` does not block writes but is slower and needs free disk; run
off-peak and verify `indisvalid` afterwards. Interim knobs:
`SET work_mem = '256MB';` and `SET max_parallel_workers_per_gather = 4;`.

This scan cost applies equally to cookbook item 10 and to
`request-queries/Q001.sql` — the report's month-wide active-subscriber count
pays the same price.

> `iot_portal_tb_sim_service_plan` schema is defined in
> `../../misc-scripts/import-iot_portal_tb_sim_service_plan.py`.

---

## 2. Package / plan resolution — CONFIRMED

The usage/request tables hold `sim_service_plan_id` (the SIM plan **instance**,
a large id such as `3332158`), **not** `service_plan_id`. The package name lives
on the same plan row, so **one join** is enough:

```
iot_portal_tb_usage_log.sim_service_plan_id
    = iot_portal_tb_sim_service_plan.sim_service_plan_id
  -> iot_portal_tb_sim_service_plan.service_plan_code
```

- `sim_service_plan_id` is the **PK** of `iot_portal_tb_sim_service_plan`, so this
  join keeps usage rows **1:1** (no fan-out).
- `service_plan_id` is the plan *template* id and is **not unique** in that table
  (e.g. `443` → several codes, `502` → several codes). Filtering by
  `service_plan_id` alone can therefore match more than one package.
- `last_grant_sim_service_plan_id` = the plan that actually **granted/consumed**
  quota for the record (`0` ⇒ PAYG). In every observed row so far it **equals**
  `sim_service_plan_id`.

### Correction — no `service_plan_lookup` table
There is **no** `service_plan_lookup` relation. That name was a mistake. The file
`sim_service_plan_distinct_plans.csv` is simply saved output of:

```sql
SELECT DISTINCT service_plan_id, service_plan_code, service_plan_desc
FROM iot_portal_tb_sim_service_plan
ORDER BY service_plan_code;
```

---

## 3. Confirmed data facts

- **Location**: `roaming_destination_id = 87` ⇒ Malaysia / home. Anything else ⇒
  roaming. `0` also exists in data (sometimes "CS" / unclassified) — decide per
  report whether it counts as roaming.
- **RAT types**: `4G` / `5G` = data, `VO` = voice, `SM` = SMS.
- **Volume columns**:
  - `act_usage_unit` = actual (bytes for data, seconds for voice).
  - `usage_unit` = billed volume.
  - request_log equivalents: `act_update_used_volume`, `update_used_volume`.
- **1 MB = 1048576 bytes** (consistent with existing repo queries).
- **`req_type`** (request_log): `C` = create, `U` = update, `T` = terminate
  (carries consumed usage), `E` = event (SMS).

### EZ50 packages (from `service_plan_code LIKE 'EZ50%'`)
| service_plan_id | service_plan_code |
|---|---|
| 446 | `EZ50-DATA` |
| 484 | `EZ50-DATA` |
| 563 | `EZ50-DATA-TEST` |
| 445 | `EZ50-ROAMING` |
| 485 | `EZ50-ROAMING` |
| 448 | `EZ50-SMS` |
| 447 | `EZ50-VOICE` |

### Observations
- Usage rows matching EZ50 so far resolve to `service_plan_id = 484` → `EZ50-DATA`.
- The newest usage-log rows (ordered by `usage_log_id DESC`) are
  `roaming_destination_id = 87` with `act_usage_unit = 0`. These look like
  **session / grant records**, not consumption → always filter
  `act_usage_unit > 0` before aggregating usage.

### EZ50 usage distribution (measured 2026-09-11)

| service_plan_code | rat_type | location | records | records_with_usage | total_mb |
|---|---|---|---:|---:|---:|
| EZ50-DATA | 4G | HOME | 3,870,350 | 3,733,775 | 1,963,461,099.38 |
| EZ50-DATA | 5G | HOME | 1,715,109 | 1,703,979 | 827,375,155.75 |
| EZ50-ROAMING | 4G | ROAMING | 10,080 | 9,932 | 767,357.38 |
| EZ50-ROAMING | 5G | ROAMING | 105 | 101 | 17,177.97 |

Key conclusions:
- **`EZ50-DATA` rows are all HOME; `EZ50-ROAMING` rows are all ROAMING.** The two
  codes partition the data cleanly by location.
- So "EZ50 subscriber roaming data" = rows with
  `service_plan_code LIKE 'EZ50%'` AND `roaming_destination_id <> 87` — in
  practice the `EZ50-ROAMING` rows (template ids 445 / 485).
- Roaming rows are non-zero (`records_with_usage` ≈ 98% of records), so
  `act_usage_unit` **is** a valid volume column for roaming data.
- Total EZ50 roaming data ≈ **784,535 MB** across 10,185 records.

### `roaming_destination_id = 0` — meaning

Documented in `queries/iot_portal_tb_usage_log-column-description.md` and
`queries/recon-queries.sql` (voice MT context):

- `0` ⇒ **CS (circuit-switched) call**; non-zero (e.g. `435`) ⇒ **s8HR** call.
- `roaming_mccmnc` = **fake GT** when `roaming_destination_id` is neither `0`
  nor `87`; **actual VLR GT** when it is `0`.
- The schema declares `roaming_destination_id` `NOT NULL DEFAULT 0`, so `0` can
  also just mean "not populated".
- Caveat: the source note says "the 0 part needs to be confirmed by MB". The
  CS/s8HR meaning is documented for **voice MT**; for **data (4G/5G)** it is not
  documented — treat it as unclassified until confirmed.
- Existing repo code already treats `0` as roaming (uses `<> 87`, and labels it
  `CS` in the MT voice query).

### ⚠️ Unexplained: many subscribers tie at exactly `3072.00` MB

In the 2026-09-01..10 top list, 10 subscribers all show exactly `3072.00` MB
roaming usage, despite record counts ranging from **1 to 19**.

- `3072.00 × 1048576 = 3,221,225,472 bytes` = **exactly 3 GiB**.
- Record counts differ by ~19× while totals are identical ⇒ this is **NOT**
  simple record duplication (duplication would scale with record count).
- Identical values clustered at the top of an `ORDER BY ... DESC` is the classic
  shape of a **fixed allowance / cap**: everyone who exhausts the bucket ties.
- Working hypothesis: `EZ50-ROAMING` has a **3 GiB** roaming data allowance and
  heavy users drain it fully, with no overage recorded on this bucket.
- **UNVERIFIED.** Confirm with cookbook queries 7–9 before trusting
  per-subscriber totals.

---

## 4. Query cookbook

Full, runnable versions live in `sim_service_plan_distinct_plans.sql`:

1. Confirm EZ50 exists on the plan table.
2. Top 10 usage-log rows for EZ50.
2b. Sanity check: does EZ50 have non-zero usage, home vs roaming, by RAT.
3. EZ50 subscribers with ≥ 100 MB roaming data (usage_log) — **runnable**; EZ50
    roaming rows are all `EZ50-ROAMING`, non-zero. Group by `msisdn` for the
    per-subscriber answer, or by `msisdn, service_plan_code` to keep the code.
4. Same from `iot_portal_tb_request_log` with `req_type = 'T'` (not yet run).
5. Which RAT / direction each EZ50 code is used for (data vs voice vs SMS).
6. EZ50 roaming ≥ 100 MB restricted to a date window (`usage_start_time`).
7. Inspect raw EZ50-ROAMING rows for one subscriber (cap vs duplication).
8. Read the plan allowance (`each_quota` / `unit` / `volume`) for EZ50-ROAMING.
9. Find totals shared by many subscribers (cap detection) + duplicate-row check.

Date-window pattern used in this repo:

```sql
AND u.usage_start_time >= DATE '2026-09-01'
AND u.usage_start_time <  DATE '2026-09-11'   -- 1st..10th inclusive
```

Canonical package-filter join:

```sql
FROM iot_portal_tb_usage_log u
JOIN iot_portal_tb_sim_service_plan ssp
  ON ssp.sim_service_plan_id = u.sim_service_plan_id
WHERE ssp.service_plan_code LIKE 'EZ50%'
```

10. **Active subscribers from `iot_portal_tb_request_log`** (list + count). The
    count is the canonical report definition and already exists in the repo as
    `report-generation-postgres/2-Invoice-Recon/request-queries/Q001.sql`
    (sample output: `9,118.00` for one month). Definition: a distinct `msisdn`
    with `act_update_used_volume > 0` inside the window.

```sql
-- List form
SELECT DISTINCT BTRIM(t.msisdn::text) AS msisdn
FROM public.iot_portal_tb_request_log t
WHERE t.req_time >= TIMESTAMP '2026-09-01 00:00:00'
  AND t.req_time <  TIMESTAMP '2026-10-01 00:00:00'
  AND COALESCE(t.act_update_used_volume, 0) > 0
  AND BTRIM(COALESCE(t.msisdn::text, '')) <> ''
ORDER BY msisdn;

-- Count form (matches request-queries/Q001.sql)
SELECT COUNT(DISTINCT BTRIM(t.msisdn::text)) AS total
FROM public.iot_portal_tb_request_log t
WHERE t.req_time >= TIMESTAMP '2026-09-01 00:00:00'
  AND t.req_time <  TIMESTAMP '2026-10-01 00:00:00'
  AND COALESCE(t.act_update_used_volume, 0) > 0
  AND BTRIM(COALESCE(t.msisdn::text, '')) <> '';
```

Request-log specifics for this definition:

- Use **`act_update_used_volume`**, not `update_used_volume`.
  `queries/iot_portal_tb_request_log-column-description.md` says the `act_` column
  is the *actual* value (bytes for data, actual seconds for voice), while
  `update_used_volume` rounds call duration up to the nearest 60 s. Same `act_`
  convention as `act_usage_unit` on the usage log.
- `BTRIM(msisdn::text)` + blank guard is required — the repo does this everywhere
  and `msisdn` is `varchar(50)`.
- `msisdn` = subscriber number, `iccid` = SIM. `DISTINCT msisdn` is the repo
  convention for "subscriber"; switch to `iccid` for lines/SIMs.
- Window on `req_time` (indexed: `iot_portal_tb_request_log_req_time_idx`), never
  `cr_time`.
- **`req_type` semantics confirmed by the vendor (2026-09-23)** — `C` = Create
  (session/call starts), `U` = Update (still running, reports usage so far),
  `T` = Terminate (session finished, final consumed usage reported), `E` = Event
  (one SMS). `C`/`U`/`T` = voice + data; `E` = SMS. Cross-ref:
  `reports-pipelines/ReadMe.md` and the root `README.md`.
- **Open point:** the canonical definition has **no `req_type` filter**, so it
  also counts **in-progress sessions** (`C`/`U` rows) whose usage is not final —
  and because the sync copies rows on a settle-time timer rather than on
  completeness, some of those immature rows are already in the reporting DB. A
  finished voice/data session is identifiable by a `T` row for its `session_id`.
  Decide whether to require `T` before trusting a month-wide count.

11. **IDD calls to a country prefix** (worked example: India `91`). Canonical IDD
    voice definition — same as `request-queries/Q012.sql` and
    `usage-queries/Q012.sql`: `rat_type='VO'`, `service_type_sub_cd='MO'`,
    `roaming_destination_id=87`, `act_* > 0`, `opposite_number` not starting `60`.

```sql
-- request_log (CDR-level): volume column is act_update_used_volume
SELECT BTRIM(r.msisdn::text) AS msisdn, BTRIM(r.opposite_number::text) AS opposite_number,
       r.iccid, r.imsi, r.req_time,
       ROUND(r.act_update_used_volume / 60.0, 2) AS minutes
FROM public.iot_portal_tb_request_log r
WHERE r.req_time >= TIMESTAMP '2026-08-01 00:00:00'
  AND r.req_time <  TIMESTAMP '2026-09-01 00:00:00'
  AND r.rat_type = 'VO' AND r.service_type_sub_cd = 'MO' AND r.roaming_destination_id = 87
  AND COALESCE(r.act_update_used_volume, 0) > 0
  AND BTRIM(COALESCE(r.opposite_number::text, '')) NOT IN ('', 'None', 'none')
  AND BTRIM(r.opposite_number::text) NOT LIKE '60%'   -- international
  AND BTRIM(r.opposite_number::text) LIKE '91%'       -- India
ORDER BY r.req_time;

-- usage_log (usage-level): volume column is act_usage_unit; time column usage_start_time
SELECT BTRIM(u.msisdn::text) AS msisdn, BTRIM(u.opposite_number::text) AS opposite_number,
       u.iccid, u.imsi, u.usage_start_time,
       ROUND(u.act_usage_unit / 60.0, 2) AS minutes
FROM public.iot_portal_tb_usage_log u
WHERE u.usage_start_time >= TIMESTAMP '2026-08-01 00:00:00'
  AND u.usage_start_time <  TIMESTAMP '2026-09-01 00:00:00'
  AND u.rat_type = 'VO' AND u.service_type_sub_cd = 'MO' AND u.roaming_destination_id = 87
  AND COALESCE(u.act_usage_unit, 0) > 0
  AND BTRIM(COALESCE(u.opposite_number::text, '')) NOT IN ('', 'None', 'none')
  AND BTRIM(u.opposite_number::text) NOT LIKE '60%'
  AND BTRIM(u.opposite_number::text) LIKE '91%'
ORDER BY u.usage_start_time;
```

The standalone (copy-paste, self-contained) form covering **both** tables at once
— no `temp_country_code`, no `{{placeholders}}`:

```sql
SELECT src, record_id, msisdn, opposite_number, iccid, imsi, event_time,
       act_seconds, ROUND(act_seconds / 60.0, 2) AS minutes
FROM (
    SELECT 'request_log' AS src, r.request_log_id AS record_id,
           BTRIM(r.msisdn::text) AS msisdn, BTRIM(r.opposite_number::text) AS opposite_number,
           r.iccid, r.imsi, r.req_time AS event_time, r.act_update_used_volume AS act_seconds
    FROM public.iot_portal_tb_request_log r
    WHERE r.req_time >= TIMESTAMP '2026-08-01 00:00:00'
      AND r.req_time <  TIMESTAMP '2026-09-01 00:00:00'
      AND r.rat_type = 'VO' AND r.service_type_sub_cd = 'MO' AND r.roaming_destination_id = 87
      AND COALESCE(r.act_update_used_volume, 0) > 0
      AND BTRIM(COALESCE(r.opposite_number::text, '')) NOT IN ('', 'None', 'none')
      AND BTRIM(r.opposite_number::text) NOT LIKE '60%'
      AND BTRIM(r.opposite_number::text) LIKE '91%'
    UNION ALL
    SELECT 'usage_log', u.usage_log_id,
           BTRIM(u.msisdn::text), BTRIM(u.opposite_number::text),
           u.iccid, u.imsi, u.usage_start_time, u.act_usage_unit
    FROM public.iot_portal_tb_usage_log u
    WHERE u.usage_start_time >= TIMESTAMP '2026-08-01 00:00:00'
      AND u.usage_start_time <  TIMESTAMP '2026-09-01 00:00:00'
      AND u.rat_type = 'VO' AND u.service_type_sub_cd = 'MO' AND u.roaming_destination_id = 87
      AND COALESCE(u.act_usage_unit, 0) > 0
      AND BTRIM(COALESCE(u.opposite_number::text, '')) NOT IN ('', 'None', 'none')
      AND BTRIM(u.opposite_number::text) NOT LIKE '60%'
      AND BTRIM(u.opposite_number::text) LIKE '91%'
) dialled_india;
```

Swap the outer `SELECT` for a summary when you only want totals:

```sql
SELECT src, COUNT(*) AS calls, COUNT(DISTINCT msisdn) AS subscribers,
       ROUND(SUM(act_seconds) / 60.0, 2) AS mou_mins
FROM ( ...same subquery... ) dialled_india
GROUP BY src ORDER BY src;
```

`roaming_destination_id = 87` = caller in Malaysia. Drop it to also include
roaming subscribers dialling India (see the probe in `report-query-voice.sql`).

- Volume semantics: `act_update_used_volume` (request) and `act_usage_unit`
  (usage) are both **seconds** for voice → `/60.0` gives MOU. Never mix in the
  non-`act_` columns (those round call duration up to the nearest 60 s).
- For SMS instead of voice: `rat_type = 'SM'` and **drop** the
  `service_type_sub_cd = 'MO'` filter (SM has no MO/MT in current data).
- `request_log` is CDR-level and `usage_log` is usage-level, so call counts will
  not tie out exactly between the two.
- Exact-match alternative to `LIKE '91%'`: replicate the report's country mapping
  (`report_engine/query_executor.py`) — split `iot_portal_tb_country.cc` +
  `idd_call_prefix_list` on commas, strip non-digits, longest prefix wins. A
  stored `+9198…` or `0091…` will **not** match `'91%'` (the report shares this
  limitation).

### ⚠️ Index gaps on both CDR tables (drives all the slowness)

From the repo schema dumps (which look like local copies — verify with
`pg_indexes` on the real DB):

| Table | Indexed columns | Missing |
|---|---|---|
| `iot_portal_tb_request_log` | `account_id`, `customer_id`, `iccid`, `req_time`, `req_type`, `service_type_id`, `session_id`, `sim_id` | `opposite_number` |
| `iot_portal_tb_usage_log` | `usage_log_id` (PK), `iccid`, `(session_id, rating_group)` unique, `sim_id` | **`usage_start_time`**, `opposite_number` |

`iot_portal_tb_usage_log` has **no index on `usage_start_time`**, so *every*
date-windowed usage report seq-scans the table. Recommended:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS iot_portal_tb_usage_log_usage_start_time_idx
    ON public.iot_portal_tb_usage_log (usage_start_time);
CREATE INDEX CONCURRENTLY IF NOT EXISTS iot_portal_tb_usage_log_opnum_start_time_idx
    ON public.iot_portal_tb_usage_log (opposite_number, usage_start_time);
CREATE INDEX CONCURRENTLY IF NOT EXISTS iot_portal_tb_request_log_opnum_req_time_idx
    ON public.iot_portal_tb_request_log (opposite_number, req_time);
```

Note `LIKE '91%'` filters rows *returned*, not rows *read* — an anchored prefix
is index-usable, so `(opposite_number, <time>)` is what makes IDD-by-country
queries fast.

### ⚠️ Report shows a country as `UNMAPPED` while a direct prefix query finds data

Observed 2026-09-22, Aug-26 report: **Intl. Voice has no India row**, but
`opposite_number LIKE '91%'` returns India calls. Cause: `Q011`/`Q012`/`Q013` do
**not** match the number directly — they resolve the country through
`temp_country_code`, built by `report_engine/query_executor.py` from
`iot_portal_tb_country.cc` + `idd_call_prefix_list` (comma-split, non-digits
stripped), then match `opposite_number LIKE country_code || '%'`, longest prefix
wins, `COALESCE(..., 'UNMAPPED')`.

So an incomplete/inconsistent reference row silently moves a country's traffic
into `UNMAPPED` (Aug: 464 calls / 1181.7 MOU). China (`86`) and Singapore (`65`)
resolved fine in the same sheet, so the mechanism works — the reference row is
the problem. Suspects: row missing; prefix absent; or prefix stored as `0091`
(the digit-strip turns `0091` into `0091`, which never matches numbers stored as
`91…`; `+91` would strip to `91` and work).

- The writer does **no** template matching — `excel_processor._render_table_anchor`
  writes exactly the rows the query returns, one per record. A missing country row
  therefore means the query did not return it.
- Diagnose with: `SELECT country_id, country_name, cc, idd_call_prefix_list FROM
  iot_portal_tb_country WHERE ...` plus a `LEFT(opposite_number,4)` breakdown of
  non-`60%` originations to see which prefix is unmapped.
- Fix = correct `iot_portal_tb_country` (reference data), not report code. Expect
  `UNMAPPED` to shrink by exactly the recovered volume.
- Manual row to patch a sheet (usage log): `'Voice' AS service_type, 'Voice MO' AS
  charge_type, 'India' AS country, COUNT(*) AS call_count, ROUND(SUM(act_usage_unit)/60.0,2) AS mou_mins`
  with the standard IDD filters + `LIKE '91%'`.

12. **1300/1700/1800 numbers — `Q014`'s length guard is wrong (corrected rule).**
    Measured 2026-09-22. The canonical format is **`60` + `1300|1700|1800` + exactly
    6 digits = 12 digits** (local form: 10 digits, no `60`). The existing
    `CHAR_LENGTH(opposite_number) < 12` guard therefore excludes the *entire* real
    population — which is why the query returns zero rows.

    | bucket | digits | rows | distinct |
    |---|---|---|---|
    | `60 1300` | 12 | 25,692 | 346 |
    | `60 1700` | 12 | 333 | 51 |
    | `60 1800` | 12 | 8,697 | 415 |
    | `1300` (no 60) | 10 | 222 | 12 |
    | `1800` (no 60) | 10 | 19 | 10 |

    - **Length is the mobile discriminator**: `6013` + 7 digits = **11 digits** = an
      `013` mobile; `601300` + 6 digits = **12 digits** = a 1300 service number.
      Same for `017`/`018`. Landlines (`603…`) and international codes can never
      match either bucket.
    - Correct shape test (normalise digits first, so `+60…` / `60-1300…` still match):
      `digits ~ '^60(1300|1700|1800)[0-9]{6}$' OR digits ~ '^(1300|1700|1800)[0-9]{6}$'`

    #### Final rule — DECISION 2026-09-23: include the junk

    `Q014.sql` in **both** `usage-queries/` and `request-queries/` now classifies on
    the digit-normalised number with:

    ```
    digits ~ '^(60)?(1300|1700|1800)[0-9]{6,8}$'
    ```

    where `digits = REGEXP_REPLACE(BTRIM(opposite_number::text), '[^0-9]', '', 'g')`
    (so `+60…`, `60-1300…` and `1300 88 1234` all normalise before matching).

    **Why include the junk:** the purpose is to count calls to Malaysian special
    numbers **for settlement with UMobile**. Where a class is ambiguous, counting it
    and reviewing later is safer than silently dropping revenue-bearing calls.

    **INCLUDED — 35,414 of 35,646 measured rows**

    | digits after code | with `60` | without `60` | verdict |
    |---|---|---|---|
    | +6 | 12 digits — 25,692 (1300), 333 (1700), 8,697 (1800) | 10 digits — 222 (1300), 19 (1800) | Standard, well-formed 1300/1700/1800 numbers |
    | +7 | 13 digits — 61 (1300), 107 (1800) | 11 digits — 1 (1300), 5 (1800) | **Junk, included** — unexplained extra digit. 32/52 distinct values, so looks like real traffic |
    | +8 | 14 digits — 277 (1300) | — | **Junk, included** — 277 rows but only **5 distinct** numbers, so likely padding/duplication |

    **EXCLUDED — 232 rows**

    | Excluded | rows | why |
    |---|---|---|
    | `60` + code + 0–5 digits (6–10 total), e.g. `601300`, `60130038`, `6013001313` | 98 (69 × 1300, 4 × 1700, 24 × 1800, 1 local) | Truncated/partial captures — not a complete dialled number |
    | `60` + `13`/`17`/`18` + 7 digits (11 total), e.g. `60130005454`, `60170036052` | 134 (101 × 1300, 3 × 1700, 30 × 1800) | **Ordinary mobile numbers** (`013`/`017`/`018` + 7 digits), not service numbers |
    | not starting with the code or `60`+code | — | Not a 1300/1700/1800 destination; landlines (`603…`) and international codes can never match |

    The `{6,8}` bound is what keeps mobiles out: an `013` number is `6013` + 7 digits
    = 11 total = only **9** digits after `60`, below the 10-digit minimum the rule
    requires.

    **Follow-up before settlement sign-off:** ask UMobile to confirm whether the `+7`
    and `+8` classes are genuine longer service numbers or data artefacts. If they are
    artefacts, tighten the quantifier to `{6}` — that yields 34,963 rows. The
    pre-decision counts above are kept so either answer can be applied later. See also
    item 11.

---

## 5. Open questions / next steps

---

## 6. Mongo equivalent (`eastel-data.usage_logs`)

Verified live on 2026-09-18. The Mongo collection `eastel-data.usage_logs` mirrors
Postgres `iot_portal_tb_usage_log` (sync state key
`iot_portal_tb_usage_log->usage_logs`, last synced id `371144219`; no `_rep` rows).

> SQL → Mongo translation used in this repo: `iot_portal_tb_usage_log` → `usage_logs`,
> `msisdn`/`iccid`/`imsi`/`opposite_number` are plain strings, `LIKE 'x%'` → `{ $regex: "^x" }`,
> `ORDER BY ... DESC` → `.sort({ usage_start_time: -1 })`, `ISODate("...")` for date windows.

### Column list requested (prefix `60182330`, `rat_type='SM'`, `usage_unit > 0`)

```javascript
db.getSiblingDB("eastel-data").usage_logs.find(
  { rat_type: "SM", opposite_number: { $regex: "^60182330" }, usage_unit: { $gt: 0 } },
  { _id: 0, usage_log_id: 1, msisdn: 1, iccid: 1, imsi: 1, opposite_number: 1, usage_start_time: 1 }
).sort({ usage_start_time: -1 });
```

### Data-format facts

- `usage_log_id`, `usage_unit`, `act_usage_unit` are **Decimal128** (from `numeric(20,0)` /
  `numeric(32,16)`). Numeric comparisons such as `{ $gt: 0 }` work cross-type; but Mongo
  `find` output prints them as `Decimal128("371042893")` — convert (`$toLong` / `$toDouble`)
  before CSV/Excel export.
- `usage_start_time` is a BSON Date built from a **naive** Postgres timestamp, so it is stored
  as if UTC (no +08:00 shift). Use the same `ISODate("YYYY-MM-DD")` convention as the existing
  report queries so Postgres and Mongo windows line up.
- Rows are also augmented with `derived.*` (`service_type`, `roaming_status`,
  `opposite_number_type`, `is_billable` = `act_usage_unit > 0`, `rat_family`) and `sync_metadata`.
- For this number prefix, `usage_unit > 0` and `act_usage_unit > 0` return the **same** 42,846 rows.

### Bounded version (use this one) — date window + limit

Never run the unbounded form. Add a `usage_start_time` window (the index is
`(opposite_number, usage_start_time)`, so the window + sort are served by the index)
and a `limit` for interactive/ad-hoc work.

```javascript
// mongosh — last 100 matching rows in a window
db.getSiblingDB("eastel-data").usage_logs.find(
  {
    rat_type: "SM",
    opposite_number: { $regex: "^60182330" },
    usage_unit: { $gt: 0 },
    usage_start_time: { $gte: ISODate("2026-09-11"), $lt: ISODate("2026-09-18") }
  },
  { _id: 0, usage_log_id: 1, msisdn: 1, iccid: 1, imsi: 1, opposite_number: 1, usage_start_time: 1 }
).sort({ usage_start_time: -1 }).limit(100);
```

```javascript
// mongosh — exact count for the window (no row materialisation)
db.getSiblingDB("eastel-data").usage_logs.countDocuments({
  rat_type: "SM",
  opposite_number: { $regex: "^60182330" },
  usage_unit: { $gt: 0 },
  usage_start_time: { $gte: ISODate("2026-09-11"), $lt: ISODate("2026-09-18") }
});
```

```python
# pymongo — Decimal128 fields stringified for CSV/Excel export
from datetime import datetime

START = datetime(2026, 9, 11)   # inclusive
END   = datetime(2026, 9, 18)   # exclusive  -> 11th..17th

flt = {
    "rat_type": "SM",
    "opposite_number": {"$regex": "^60182330"},
    "usage_unit": {"$gt": 0},
    "usage_start_time": {"$gte": START, "$lt": END},
}
proj = {"_id": 0, "usage_log_id": 1, "msisdn": 1, "iccid": 1, "imsi": 1,
        "opposite_number": 1, "usage_start_time": 1}

rows = list(col.find(flt, proj).sort("usage_start_time", -1).limit(100))
```

Window convention: keep it half-open (`>= start`, `< end`) and use the same
`2026-09-11` / `2026-09-18` style boundaries as the Postgres queries so both
databases return the same set.

Measured on the live cluster, 2026-09-18 (window `2026-09-11` → `2026-09-18`):

| Variant | Result | Time |
| --- | --- | --- |
| window + `limit(100)` | 100 rows | **5.1 s** |
| `countDocuments` for the window | **1,232 rows** | **2.4 s** |
| same query, no window, no limit | 42,846 rows | 80–107 s |

The 100 newest rows inside the window span only ~2.4 hours
(`2026-09-17 21:26` → `23:50`), so even a one-week window is dense for these
shortcodes — prefer a narrow window **and** a limit.

> ⚠️ **Never run the unbounded form, not even "just to get the count".** The
> planner picks `(opposite_number, usage_start_time)`, but `rat_type` is not in
> that index, so every prefix match (~98.6k docs) must be FETCHed and
> re-filtered. During this investigation a repeated unbounded run dropped the
> cluster connection (`AutoReconnect` after 1,682 s, then
> `ServerSelectionTimeoutError`); connectivity recovered after a reconnect.
> Always bound the window, add a `limit`, and pass `maxTimeMS`.

### Verified counts (2026-09-18)

| Filter | Count |
| --- | --- |
| `opposite_number ^60182330` (all RAT) | 98,601 |
| + `rat_type = 'SM'` | 98,560 |
| + `usage_unit > 0` | 42,846 |

Matching numbers are few but very hot: `60182330793` (19,710), `60182330794` (19,508),
`60182330632` (19,304), `60182330873` (13,566), `60182330872` (13,311), `60182330875` (13,180),
plus a long tail of ≤ 7-row numbers. So `LIKE '60182330%'` is **not** selective.

### Performance ⚠️

- The planner picks `ix_opposite_number_usage_start_time` with bounds
  `["60182330", "60182331")` — but `rat_type` is not in that index, so **every** matching doc is
  FETCHed and re-filtered.
- `find(...).sort({usage_start_time: -1}).limit(5)` is fast (~0.9 s) because the sort+limit lets
  the index scan stop early. Adding a date window keeps it fast (**5.1 s for 100 rows**, 2.4 s for
  the window count) because the window also narrows the index scan. Anything unbounded (full
  export, `count_documents`, no `LIMIT`, no window) takes **80–107 s** and can destabilise the
  connection — see the warning above.
- Recommended index for this shape:
  `{ rat_type: 1, opposite_number: 1, usage_start_time: -1 }` (equality → range → sort, all
  satisfied by one index). Consider a partial index on `rat_type: "SM"` if only SMS shortcodes
  are ever queried.
- Always add a `usage_start_time` window (or `LIMIT`) — the user's SQL had none.

- [x] Does EZ50 have any **roaming** usage rows, and are they non-zero?
      **YES** — under `EZ50-ROAMING` (4G + 5G), ~98% non-zero. See §3.
- [x] Is `act_usage_unit` a valid volume column? **YES** for data (bytes).
- [ ] For roaming, should "on EZ50" match `sim_service_plan_id` (subscriber plan)
      or `last_grant_sim_service_plan_id` (bucket that paid)? (Both equal in
      every row observed so far.)
- [ ] Should `roaming_destination_id = 0` be treated as roaming? Meaning is
      documented for voice MT (CS vs s8HR) but not for data — see §3.
- [ ] Is `EZ50-ROAMING` used for **voice / SMS** too, or is roaming voice/SMS
      carried by `EZ50-VOICE` / `EZ50-SMS`? Check `rat_type` ×
      `service_type_sub_cd` per EZ50 code.
- [ ] **UNRESOLVED**: why do many subscribers tie at exactly `3072.00` MB
      (= 3 GiB)? Real cap or duplicated/replayed CDRs? See §3. Do not trust
      per-subscriber roaming totals until this is confirmed.
- [ ] Confirm the `iot_portal_tb_request_log` + `req_type = 'T'` variant returns
      comparable numbers to the usage-log query.

---

## 7. Saved data snapshots

| File | Contents |
|---|---|
| `sim_service_plan_distinct_plans.csv` | 125 distinct (service_plan_id, service_plan_code, service_plan_desc) from `iot_portal_tb_sim_service_plan` |
| `samples/iot_portal_tb_usage_log_latest10.csv` | 10-row sample of `iot_portal_tb_usage_log` (60 columns) |
| `../report-generation-mongo/mongo-collections/samples/usage_logs_opposite_number_60182330_sm_latest100_2026-09-11_to_2026-09-17.csv` | 100 newest `usage_logs` rows for `opposite_number` starting `60182330`, `rat_type='SM'`, `usage_unit > 0`, window 2026-09-11 → 09-17 (exclusive). Columns: `usage_log_id`, `msisdn`, `iccid`, `imsi`, `opposite_number`, `usage_start_time` |

---

## 8. Change log

- **2026-09-18** — Added the Mongo equivalent (§6). Confirmed `usage_logs` mirrors
  `iot_portal_tb_usage_log`, Decimal128 typing for numeric columns, BSON-Date
  storage of `usage_start_time`, and that `LIKE 'x%'` must be anchored. Found the
  index gap (`rat_type` absent from `(opposite_number, usage_start_time)`), which
  makes unbounded runs 80–107 s.
- **2026-09-21** — Added the bounded (date window + limit) form and measured it:
  100 rows in 5.1 s, window count 2.4 s. Saved the 100-row sample CSV. Noted that a
  repeated unbounded run dropped the cluster connection — always bound the window,
  add a limit, and pass `maxTimeMS`.
- **2026-09-11** — Created. Recorded the 1-hop package join path; documented the
  `service_plan_lookup` mistake and correction; recorded EZ50 plan ids and the
  zero-usage / home observation on recent usage rows.
- **2026-09-11** — Ran the by-code / RAT / location summary. Confirmed EZ50-DATA
  is HOME-only and EZ50-ROAMING is ROAMING-only; recorded the full distribution
  table and total roaming volume. `act_usage_unit` confirmed usable. The
  ≥100 MB roaming query is now runnable.
- **2026-09-11** — Documented `roaming_destination_id = 0` (CS vs s8HR, fake GT
  vs VLR GT, DEFAULT 0) from `queries/iot_portal_tb_usage_log-column-description.md`
  and `queries/recon-queries.sql`. Added the date-window pattern and the
  "which RAT/direction per EZ50 code" open question.
- **2026-09-11** — Observed 10 subscribers tying at exactly `3072.00` MB (= 3 GiB)
  roaming usage with record counts from 1 to 19. Flagged as an unresolved
  cap-vs-duplication anomaly; added diagnostics (cookbook 7–9) and a blocking
  open question. **Per-subscriber roaming totals should not be trusted yet.**
