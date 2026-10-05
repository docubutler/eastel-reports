# Eastel Reports — Scripts & Pipelines

This repository holds the scripts that move data out of the live telecom systems
and turn it into reports, invoices and reconciliations.

---

## 1. What Eastel is

Eastel is a Malaysian **MVNO** (Mobile Virtual Network Operator) — <https://eastel.com.my/>.

An MVNO does not own its own radio network. Eastel sells SIM cards, plans and
service to customers, but the actual calls, data sessions and SMS travel over
**UMobile's** network. Eastel therefore pays UMobile for the traffic its
subscribers generate, and has to be able to *prove* what that traffic was.

That is the whole reason this repository exists: every number produced here can
end up in a settlement or an invoice, so **accuracy matters more than speed**.

---

## 2. The two databases

| | PostgreSQL — **IOT portal** | MongoDB — **reporting copy** |
|---|---|---|
| Role | The **live** database | A **copy** used for reporting |
| Who writes | The IOT portal and the live signalling services, in real time | The sync jobs in this repo |
| Content | The source of truth for CDRs (voice, data, SMS) | Only selected tables, refreshed from Postgres |

> **In short:** Postgres is where the network records the truth. Mongo is a
> comfortable place to read it from, so reports don't load the live system.

Tables currently copied into Mongo (`eastel-data`):

- `request_logs` ← `iot_portal_tb_request_log`
- `usage_logs` ← `iot_portal_tb_usage_log`
- `smsc_cdrs`, `country_code`, `roaming_destination`

The sync and repair tools live in `import-to-mongo/`.

---

## 3. ⚠️ The catch: a row does *not* mean a finished record

This is the single most important thing to understand about this data.

When a call or a data session is in progress, the network **keeps writing to
Postgres while it is still happening**. The same session produces several rows
over time, each one updating the usage so far.

So the fact that a row exists does **not** mean the record is complete. Copy it
too early and you copy a **partially-filled record**, whose figures will still
change — which then fails to match the invoice.

### How a record matures — the `req_type` column

Confirmed by the network vendor, the `req_type` column in
`iot_portal_tb_request_log` tells you where a session is in its life:

| `req_type` | Meaning | What it tells you |
|---|---|---|
| `C` | **Create** | The data session or voice call has just **started** |
| `U` | **Update** | The session is **still running**; usage so far is reported |
| `T` | **Terminate** | The session has **finished**, and the final consumed usage is reported |
| `E` | **Event** | Used for **one SMS** |

`C` / `U` / `T` apply to **voice and data**. `E` applies to **SMS**.

The practical rule that falls out of this:

- A `C` or `U` row is a **work in progress** — its usage numbers will still grow.
- A voice or data record is only **final once the session reaches `T`**.
- The `session_id` column links the rows of one session together, across both
  `iot_portal_tb_request_log` and `iot_portal_tb_usage_log`.

### How it works today — and why it isn't good enough

Today the sync does not look at `req_type` at all. It waits a **configurable
settle time** (`min_record_age_seconds`, e.g. `7200` = 2 hours) based on the
row's creation time, then copies the row blindly, hoping it has settled by then.

**That assumption does not hold.** Records do not mature on a fixed clock — a
session can stay open far longer than the settle time, and a record can take
**days** to become final. A row copied after 2 hours may still be an in-progress
`C` or `U` row, and nothing will revisit it unless someone deliberately runs a
backfill.

**Consequence:** reports and reconciliation figures built on recently-synced
data can be *incomplete*, and will not match the invoice until a backfill
repairs them.

### The rule we actually want (not implemented yet)

Instead of "wait N hours and copy", migrate when the record is **finished**:

1. **Voice / data:** only migrate a session once a `T` (Terminate) row exists for
   it — that is when the final consumed usage is reported. Take the session's
   rows from `iot_portal_tb_request_log`, and its usage rows from
   `iot_portal_tb_usage_log` matched on `session_id`.
2. **SMS:** `req_type = 'E'`.
3. **Usage log readiness:** **open question.** Unlike the request log, there is
   no confirmed column on `iot_portal_tb_usage_log` that says "this session is
   closed". This still needs confirming with the vendor, so for now the usage
   log cannot independently tell you whether a record is mature.

**Status: not implemented.** Until it is, treat recently-synced data as
provisional, and use the backfill tools in `import-to-mongo/postgres-to-mongo/`
to repair records once they have settled.

---

## 4. Service plans and package usage

### Plan template versus SIM plan instance

`iot_portal_tb_sim_service_plan` connects usage records to plan codes. Its rows
represent plan instances assigned to SIMs, with both an instance ID and a
template ID:

| Field | Meaning | How to use it |
|---|---|---|
| `sim_service_plan_id` | Primary key of an assigned SIM plan instance | Join a usage record to exactly one plan mapping row |
| `service_plan_id` | ID of the service-plan template, often a DATA, SMS, VOICE, or ROAMING component | Describe the template shared by many assigned instances |
| `service_plan_code` | Internal component code, such as `EZ35-DATA` | Group usage by its resolved component |
| `bundle_code` | Bundle code on the instance, where populated | Supporting evidence for the retail-package mapping; it can be blank |

For example, subscriber A and subscriber B can both use `EZ35-DATA`, with the
same `service_plan_id` but different `sim_service_plan_id` values. These
illustrative IDs show the relationship:

| Subscriber | `sim_service_plan_id` | `service_plan_id` | `service_plan_code` |
|---|---:|---:|---|
| A | 10001 | 482 | EZ35-DATA |
| B | 10002 | 482 | EZ35-DATA |
| A | 10003 | 444 | EZ35-SMS |

The instance ID is **unique per assigned plan record, not per subscriber**.
A subscriber can have several component plans or add-ons and therefore several
instance IDs. Usage records repeat the instance ID whenever that instance is
referenced. Do not count distinct plan instance IDs as distinct subscribers.
The example does not establish that the subscriber's DATA and SMS components
belong to the same retail package.

The template ID identifies a particular configured plan component, not the
generic service type DATA or SMS. Different components normally have different
template IDs, while instances of the same template share its ID. However, the
same component code can have multiple template IDs: September's mapping has
both `482` and `545` for `EZ35-DATA`.

When we say `service_plan_id` is "not unique", we mean it repeats across rows of
the **instance table**, so it is not a valid unique join key there. This does
not mean the template's own primary key is duplicated. Historical exports also
show some template IDs associated with different code strings, so do not assume
an immutable one-to-one relationship between template ID and code across all
snapshots. September's supplied mapping contained 275,992 unique instance IDs
and 40 distinct template IDs, with no template-to-code conflicts in that export.

### Which package receives the usage?

There are two attribution choices. Name the choice in every report:

| Report question | Usage field joined to mapping `sim_service_plan_id` |
|---|---|
| Which plan instance does the usage record reference? | `usage_logs.sim_service_plan_id` |
| Which plan granted the quota consumed by this record? | `usage_logs.last_grant_sim_service_plan_id` |

The SQL equivalents use the same fields on `iot_portal_tb_usage_log`.
In both cases, the target join key is
`iot_portal_tb_sim_service_plan.sim_service_plan_id`, **not** its
`service_plan_id`. Joining an instance-table mapping through the repeated
template ID can duplicate a usage event and inflate the total.

The two usage fields are not always equal. In the September 2026 Mongo window
`2026-09-01T00:00:00Z` through `2026-10-01T00:00:00Z`, they differed on 39,141
positive-volume data records. One inspected event referenced an `EMERGENCY`
instance but drew quota from an `EZ35-DATA` instance. Consequently, grouping by
the grant field and grouping by the referenced field can give different package
totals. These are alternative breakdowns of the same usage; never add them
together.

Neither field alone identifies a subscriber's primary retail subscription.
"Quota consumed from EZ35" and "all usage by subscribers whose main package is
EZ35" are different questions. The latter needs subscriber-package assignment
history valid at the time of each event, including attribution of PAYG and
add-on usage to that subscriber's main package.

### Current retail packages and internal component codes

The current retail package list below was supplied on 2026-10-05. Internal codes
are taken from the September mapping or the repository's saved plan export.
Candidate retail associations require confirmation from the plan catalogue;
similar names or prices alone are not sufficient to finalize a mapping.

| Retail package | Internal data / roaming codes | Mapping evidence |
|---|---|---|
| 5G EZ15 | `EZ15-DATA` | Observed in September |
| 5G EZ35 | `EZ35-DATA` | Observed in September |
| 5G EZ50 | `EZ50-DATA`, `EZ50-ROAMING` | Observed in September; keep DATA and ROAMING separately or explicitly combine |
| 5G EZ68 | `EZ68-DATA`, `EZ68-ROAMING` | Observed in September |
| 5G EZ98 | `EZ98-DATA`, `EZ98-ROAMING` | Observed in September |
| CUKUP25 | Candidate: `TNG-25-DATA` | Code observed; retail association needs confirmation |
| POWER35 | Candidate: `TNG-35-DATA` | Code observed; retail association needs confirmation |
| MANTAP48 | Candidate: `TNG-48-DATA` | Code observed; retail association needs confirmation |
| F20 | Candidates: `F20-DATA`, `CGO-F20-DATA` | First code in saved export; second in September; confirm which belongs to F20 |
| F25 | Not yet established | Needs catalogue mapping |
| TRAVEL40 | Candidates: `TNG-TRAVEL40-DATA`, `TNG-TRAVEL40-ROAMING` | Codes observed; retail association needs confirmation |
| BD25 | Not yet established | Needs catalogue mapping |
| PLAY30_TEST | Not yet established | Needs catalogue mapping; keep test plans separate |
| PLAY200_TEST | Not yet established | Needs catalogue mapping; keep test plans separate |
| PLAY500_TEST | Not yet established | Needs catalogue mapping; keep test plans separate |
| PLAY30 | Not yet established | Needs catalogue mapping |
| PLAY200 | Not yet established | Needs catalogue mapping |
| PLAY500 | Not yet established | Needs catalogue mapping |
| EASY 38 | `WEKONGSI_EASY38_DATA` | Matching code observed in September |
| EASY 50 | `WEKONGSI_EASY50_DATA` | Matching code observed in September |

A retail package may include several components. Shared SMS/VOICE codes such as
`EZ35-50-68-98-SMS` cannot identify one retail package on their own. For a data
report, start with exact data/roaming codes and apply a verified retail mapping.
The "5G" label in a retail name does not mean its report should exclude 4G usage.

### How to segregate actual data usage

1. Fix the reporting period and timestamp convention. Use an inclusive start
   and exclusive end. Existing Mongo scripts interpret timezone-less boundaries
   as UTC; source PostgreSQL timestamps have no timezone. Confirm the business
   timezone rather than assuming UTC storage proves that the source used UTC.
2. Select data records (`rat_type IN ('4G', '5G')`; Mongo also has
   `derived.service_type = 'DATA'`) and `act_usage_unit > 0`.
3. Choose referenced-plan or quota-grant attribution, then resolve the chosen
   instance ID through a mapping with one row per `sim_service_plan_id`.
4. Sum **`act_usage_unit`**, the actual bytes for data. `usage_unit` is billed
   volume. Report bytes or explicitly labeled units: MiB = bytes / 1,048,576;
   GiB = bytes / 1,073,741,824.
5. Group first by `service_plan_code`, then optionally combine components using
   the verified retail mapping above. State whether home, roaming, or both are
   included. Preserve test plans and unknown retail associations separately.
6. Keep PAYG, EMERGENCY, add-ons, missing mappings, null IDs, and ID zero visible.
   Positive instance IDs can resolve to PAYG, so filtering out ID zero does not
   remove PAYG. Earlier notes associate grant ID zero with PAYG; retain it as a
   separate category until its reporting treatment is confirmed.
7. Reconcile package sums against the unjoined total over the same records.
   Validate mapping uniqueness and coverage before treating the report as final.
   Record maturity and sync completeness still apply; see section 3.

For example, this **read-only** SQL groups September data by quota-granting
component, retaining unresolved records. The September source was rolled over
on October 1 and is `iot_portal_tb_usage_log_old20260930`. These literal date
boundaries follow the stored PostgreSQL timestamps; confirm their timezone.

```sql
SELECT
    CASE
        WHEN u.last_grant_sim_service_plan_id IS NULL THEN 'NO_PLAN_ID'
        WHEN u.last_grant_sim_service_plan_id = 0 THEN 'NO_PLAN_ID_ZERO'
        WHEN s.sim_service_plan_id IS NULL THEN 'UNMAPPED'
        ELSE COALESCE(NULLIF(s.service_plan_code, ''), 'MISSING_PLAN_CODE')
    END AS service_plan_code,
    COUNT(*) AS positive_usage_records,
    SUM(u.act_usage_unit) AS actual_bytes,
    ROUND(SUM(u.act_usage_unit) / 1073741824.0, 2) AS actual_gib
FROM iot_portal_tb_usage_log_old20260930 u
LEFT JOIN iot_portal_tb_sim_service_plan s
    ON s.sim_service_plan_id = u.last_grant_sim_service_plan_id
WHERE u.usage_start_time >= TIMESTAMP '2026-09-01'
  AND u.usage_start_time < TIMESTAMP '2026-10-01'
  AND u.rat_type IN ('4G', '5G')
  AND u.act_usage_unit > 0
GROUP BY 1
ORDER BY actual_bytes DESC;
```

For Mongo, use the same filtering and aggregate by the chosen instance ID,
then join the totals locally to an exported CSV of
`sim_service_plan_id, service_plan_id, service_plan_code, bundle_code`.
As inspected on 2026-10-05, `eastel-data` had no plan mapping collection.
The local CSV approach requires no Mongo writes. The repository's
`sim_service_plan_distinct_plans.csv` contains template IDs and codes only;
it cannot substitute for the instance-level mapping.

---

## 5. Repository layout

| Folder | What it does |
|---|---|
| `import-to-mongo/` | Postgres → Mongo sync, plus backfill/repair tools |
| `reports-pipelines/` | Report generation (Postgres and Mongo variants) |
| `queries/` | Reusable SQL and column references for the portal tables |
| `helper-data-ingestor/` | Reference-data ingest (country codes, roaming destinations) |
| `hlr-reconciliation/` | Monthly HLR vs BOSS/IOT active-subscriber reconciliation |
| `cdrs-to-postgres/` | CDR ingestion into Postgres |
| `import-to-mysql/` | Ingestion/parsing flows for MySQL |
| `misc-scripts/` | Ad-hoc utilities and one-off migrations |

---

## 6. Reference

- `reports-pipelines/ReadMe.md` — staging vs production, and record completeness.
- `reports-pipelines/report-generation-postgres/QUERY-NOTES.md` — living notes
  for writing report queries: confirmed tables and columns, how to resolve a
  subscriber's package, known data caveats, and a running change log. **Append
  new findings here as they are discovered.**
