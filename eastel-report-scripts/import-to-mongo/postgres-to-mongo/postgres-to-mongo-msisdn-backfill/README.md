# PostgreSQL To Mongo MSISDN Backfill

Copies every usage-log row for a supplied list of MSISDNs from PostgreSQL to
MongoDB, without waiting for the main usage sync to reach those rows.

Use it when a subscriber's data is needed now but the main
`postgres-to-mongo-usage-sync` is still catching up through its `usage_log_id`
backlog.

## Relationship to the main sync

- **Documents are identical.** Both scripts use `transform_row()` from the main
  usage sync module, imported directly from `../postgres-to-mongo-usage-sync`.
  Keep the two folders side by side.
- **Separate lock.** The lock key is
  `lock::msisdn-backfill::<source_table>-><collection>`, so this script and the
  main sync can run at the same time. They never share a checkpoint, and every
  write is an idempotent upsert keyed by `usage_log_id`, so overlapping rows are
  simply rewritten with the same values.
- **The main sync is unaffected.** This script never advances or reads the main
  sync checkpoint; the main sync will re-upsert these rows when it reaches them.

## Files

- `config-sample.yml`
- local `config.yml`
- `requirements.txt`
- `postgres_to_mongo_msisdn_backfill.py`
- `msisdns.csv` (your input list, one MSISDN per row)

## Config

Copy the sample file before running:

```powershell
Copy-Item config-sample.yml config.yml
```

The local `config.yml` holds the PostgreSQL connection, the MongoDB URI,
database, usage collection and state collection, plus:

- `backfill.msisdns_csv` — default CSV path, so `--msisdn-csv` can be omitted.
- `backfill.batch_size` — rows fetched per batch, per MSISDN.
- `sync.lock_timeout_seconds` — expiry of this script's own lock.
- `sync.oom_retry_attempts` / `sync.oom_retry_delay_seconds` — batch write retries
  when the machine runs out of memory.

## Input CSV

One MSISDN per row. A header row is optional and accepted:

```csv
msisdn
601176003805
601176068225
```

Whitespace, `+`, spaces and dashes are stripped before matching, and duplicate
values are ignored. Rows are processed in the order given.

## Run

```powershell
python postgres_to_mongo_msisdn_backfill.py --msisdn-csv msisdns.csv
```

Useful options:

- `--dry-run` — print how many source rows each MSISDN has; writes nothing.
- `--reset-progress` — forget stored progress for the supplied MSISDNs and copy
  them again from the first row.
- `--batch-size`, `--lock-timeout-seconds` — override the config values.

## Progress tracking

Progress is stored per MSISDN in a dedicated state document:

```
_id: msisdn-backfill::iot_portal_tb_usage_log->usage_logs
progress: { "601176003805": 482991595, ... }
```

Re-running with the same CSV skips nothing but continues from each MSISDN's
stored checkpoint, so an interrupted run resumes where it stopped. Adding new
MSISDNs to the CSV starts them at the first row.

At the end the script prints a per-MSISDN summary of rows copied and time taken.
