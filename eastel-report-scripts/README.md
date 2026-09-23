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

## 4. Repository layout

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

## 5. Reference

- `reports-pipelines/ReadMe.md` — staging vs production, and record completeness.
- `reports-pipelines/report-generation-postgres/QUERY-NOTES.md` — living notes
  for writing report queries: confirmed tables and columns, how to resolve a
  subscriber's package, known data caveats, and a running change log. **Append
  new findings here as they are discovered.**
