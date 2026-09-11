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

---

## 5. Open questions / next steps

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

## 6. Saved data snapshots

| File | Contents |
|---|---|
| `sim_service_plan_distinct_plans.csv` | 125 distinct (service_plan_id, service_plan_code, service_plan_desc) from `iot_portal_tb_sim_service_plan` |
| `samples/iot_portal_tb_usage_log_latest10.csv` | 10-row sample of `iot_portal_tb_usage_log` (60 columns) |

---

## 7. Change log

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
