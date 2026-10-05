# 3-OneDay-CDR-Details — PostgreSQL

Exports usage CDRs from PostgreSQL and SMSC A2P records from MongoDB into one CSV,
with one row per categorized source record and the same category
labels and precedence as the [Mongo report](../../report-generation-mongo/3-OneDay-CDR-Details/README.md).
This is a detail extractor, not a package summary or an aggregated usage report.

## Run

From this directory:

```powershell
pip install -r requirements.txt
Copy-Item -LiteralPath config-sample.yml -Destination config.yml
```

Configure the connection in `config.yml`, or supply `POSTGRES_DSN` or the standard
`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSSLMODE` variables.
Use your existing read-only Postgres account. Environment values override the
corresponding config fields. For SMSC, set `mongo.uri` / `mongo.database` or
`MONGO_URI` / `MONGO_DB`. The ignored local `config.yml` is not committed.

```powershell
python .\generate_report.py
python .\generate_report.py --start-date 2026-09-30 --end-date 2026-09-30 --msisdn-a 601169070013
python .\generate_report.py --usage-table public.iot_portal_tb_usage_log --start-date 2026-10-01 --end-date 2026-10-01
```

`--config`, `--output`, `--usage-table`, `--smsc-collection`, `--include-smsc`, and
`--skip-smsc` are also available. An explicitly empty `--msisdn-a ""` clears a
configured subscriber filter. Output paths are relative to the config directory.

To inspect the SQL and parameters without connecting or writing a report:

```powershell
python .\generate_report.py --dry-run
```

## Dates and source tables

Both dates are inclusive calendar dates in `YYYY-MM-DD` format. For a one-day
report, set them to the same date. For all September, use September 1 and 30.
The internal range is `start_date 00:00 <= timestamp < end_date + 1 day`.
The dates use the stored Postgres timestamp convention without timezone shifts.
For Mongo SMSC, the same literal date boundaries are interpreted as UTC BSON
dates, matching the original Mongo extractor. Confirm that the source timestamp
conventions align when defining a reporting period; there is no automatic
conversion between the sources' business timezones.

The sample selects `public.iot_portal_tb_usage_log_old20260930` because September
data was rolled over on October 1. Select the appropriate live/archive table for
other periods. Each run reads one configured usage table; it does not search or
combine archives automatically.

## Categories and precedence

| Category | Service type |
|---|---|
| 1 | Domestic Data 4G |
| 2 | Domestic Data 5G |
| 3 | Domestic MO SMS (Offnet / Onnet) |
| 4 | Domestic MO Voice (Onnet) |
| 5 | Domestic MO Voice (Offnet) |
| 6 | Domestic IDD MO Voice |
| 7 | Domestic IDD MO SMS |
| 8 | Roaming Data 4G / 5G |
| 9 | Roaming MT Voice (Camel/S8HR) |
| 10 | Roaming MO Voice (Camel/S8HR) |
| 11 | Roaming SMS MO (Camel/S8HR) |
| 12 | Premium Special Number Voice |
| 13 | Non-Profit A2P |
| 14 | Commercial A2P |

The usage rules are in `queries/usage-details.sql`; SMSC uses the Mongo pipeline
in `generate_report.py`. They preserve the existing Mongo behavior:

- Home destination is 87. Other destinations, including null and zero, match
  roaming rules. This mirrors Mongo's inequality handling.
- Domestic data excludes rating group `500003`; null rating groups are included.
- Premium MO voice is checked before generic voice categories.
- Roaming MT voice includes callers from any country.
- Roaming MO voice requires the opposite number not to start with `60`.
- SMS direction is not used. Domestic SMS category 3 precedes category 7, so
  domestic international SMS also appears in category 3. Category 7 therefore
  receives no rows under the existing rules; this is preserved for parity.
- The special A2P sender `601170337777` matches only Non-Profit A2P.
- Unclassified records are omitted. Each classified source record appears once.

`exclude_zero_usage_rows: true` applies `act_usage_unit > 0` in SQL, matching
Mongo's implementation; it also excludes negative and null values. False includes
all values for classified records. No aggregation or deduplication is performed.

## SMSC support

Categories 13 and 14 come from MongoDB, enabled by default with
`report_generation.include_smsc: true`. Configure `mongo.uri` and
`mongo.database`, or provide `MONGO_URI` and `MONGO_DB`. The collection defaults
to `smsc_cdrs` and can be overridden with `collections.smsc_cdr` or CLI:

```powershell
python .\generate_report.py --include-smsc --smsc-collection smsc_cdrs
python .\generate_report.py --skip-smsc
```

The Mongo query selects successful SMPP messages by `delivery_date`, optionally
filtered by recipient `addr_dst_digits`. Senders beginning with `2`, plus
`601170337777`, are Non-Profit A2P. Other senders beginning with `6` are Commercial
A2P. The shared date window and subscriber filter apply to both sources.
No PostgreSQL SMSC table is required. An enabled Mongo connection/query failure
fails the export; SMSC is never silently skipped. The Mongo pipeline contains
only read stages and does not insert, update, or delete documents.

## CSV columns

The first eight columns match the Mongo report:

- `S.No.`
- `Category No.`
- `Service Type`
- `Event/Call Start Date Time`
- `Call Duration (second) / Total Volume (UL +DL ) in bytes`
- `MSISDN A#`
- `MSISDN B#`
- `IMSI`

Verification columns are `Source Database`, `Source Table / Collection`,
`Source Record ID`, `Postgres Record ID`, and `Mongo Record ID`.
Usage rows identify PostgreSQL and the configured table, with `usage_log_id` in
both source and Postgres ID columns and a blank Mongo ID. SMSC rows identify
MongoDB and the collection, with `message_id` as the source ID, Mongo `_id` as
the Mongo ID, and a blank Postgres ID.

Duration/volume comes directly from `act_usage_unit`: seconds for voice, bytes
for data, and the raw unit for SMS. SMSC duration/volume is blank. Decimal values
retain full precision and identifiers remain strings in the CSV. Use a text
import when opening the CSV in Excel to preserve phone numbers and IMSIs.

Rows are ordered by category, event timestamp, and the database record ID
(Postgres ID for usage, Mongo `_id` string for SMSC). A2P categories follow the
usage categories. Microseconds from Postgres are preserved.

## Read-only execution and verification

The connection uses a read-only, repeatable-read transaction. Server-side cursors
stream rows in `fetch_batch_size` batches; the full result is not loaded into
Python memory. SQL filtering and categorization happen in Postgres. Mongo SMSC
is streamed from an aggregation cursor. No tables, collections, indexes, or
database records are created or modified. The sources are read independently;
the Postgres snapshot does not establish a shared snapshot with Mongo.

`statement_timeout_ms` bounds each statement. The completed CSV replaces its
destination only after all source cursors finish successfully; a failed query
leaves an existing report intact. Logs include row counts per category.

Run local checks without database access:

```powershell
python -m unittest discover -s tests -v
```

Tests execute usage-category SQL against local fixtures with SQLite parameter
syntax adapted for the test runner. They also compare SMSC selection/category
stages with the original Mongo extractor and check the combined export using
mocked database cursors. Coverage includes precedence, null handling, filters,
boundaries, source IDs, exact numeric output, and failed export preservation.
They do not validate live connectivity or production schemas. A live read-only
run is still needed in your environment.
