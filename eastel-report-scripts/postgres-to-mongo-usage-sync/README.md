# PostgreSQL To Mongo Usage Sync

This folder contains an idempotent usage-log migration flow for `iot_portal_tb_usage_log_rep`.

## Files

- `create_mongo_usage_collection.py`
  Creates the MongoDB collection and reporting indexes. Safe to run multiple times.
- `postgres_to_mongo_usage_sync.py`
  Incrementally syncs new rows from PostgreSQL into MongoDB using `usage_log_id` as the checkpoint.
- `requirements.txt`
  Python dependencies for these scripts.
- `config.sample.yml`
  Sample YAML config for PostgreSQL, MongoDB, and sync settings.

## What The Sync Script Does

- Reads from PostgreSQL instead of MySQL.
- Fetches only rows where `usage_log_id` is greater than the last stored checkpoint.
- Writes into MongoDB using `upsert` on `usage_log_id`, so reruns do not duplicate records.
- Stores the sync checkpoint in MongoDB collection `usage_log_sync_state`.
- Can read settings from environment variables first, and from a YAML config file if env vars are not set.
- Can run once for cron usage, or continuously with a configurable polling interval.
- Preserves the raw source columns and also adds a small `derived` block:
  - `derived.service_type`
  - `derived.roaming_status`
  - `derived.opposite_number_type`
  - `derived.is_billable`

## Why This Is Idempotent

There are two layers of protection:

1. The script only requests rows with `usage_log_id > last_usage_log_id`.
2. MongoDB uses a unique index on `usage_log_id`, and each write is an `upsert`.

This means:

- A row that is already present in MongoDB is matched by `usage_log_id` and updated, not inserted again.
- A row that is not yet present in MongoDB is inserted.
- The checkpoint is advanced only after a MongoDB batch write succeeds.

If a run is repeated after a failure, previously written `usage_log_id` values are updated in place and missing ones are inserted, which prevents duplicate documents for the same source row.

## Mongo Keys And Indexes Chosen From Your Queries

The SQL query set in this repository repeatedly filters or groups by:

- `usage_log_id`
- `msisdn`
- `rat_type`
- `service_type_sub_cd`
- `roaming_destination_id`
- `roaming_mccmnc`
- `opposite_number`
- `rating_group`
- `usage_start_time`
- `customer_id`
- `sim_id`

The setup script creates these indexes:

- `usage_log_id`
  Supports idempotent upsert and direct lookup.
- `msisdn, usage_start_time`
  Supports subscriber reports over date ranges.
- `rat_type, usage_start_time`
  Supports data/voice/sms slicing over date ranges.
- `rat_type, service_type_sub_cd, usage_start_time`
  Supports MO/MT voice reporting.
- `rat_type, roaming_destination_id, usage_start_time`
  Supports roaming vs non-roaming filters.
- `opposite_number, usage_start_time`
  Supports FaceTime-number and destination-number reports.
- `rat_type, rating_group, usage_start_time`
  Supports ONNET/OFFNET and rating-group analysis.
- `roaming_mccmnc, usage_start_time`
  Supports operator / VLR GT / MCCMNC analysis.
- `customer_id, usage_start_time`
- `sim_id, usage_start_time`

## Environment Variables

### PostgreSQL

- `POSTGRES_DSN`
  Optional full DSN. If this is set, the script uses it directly.

Or set the individual values:

- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGPASSWORD`
- `PGSSLMODE`

### MongoDB

- `MONGO_URI`
- `MONGO_DB`
  Optional. Default: `eastel-data`
- `MONGO_COLLECTION`
  Optional. Default: `usage_logs`
- `MONGO_STATE_COLLECTION`
  Optional. Default: `usage_log_sync_state`

### Sync Tuning

- `SYNC_BATCH_SIZE`
  Optional. Default: `1000`
- `SYNC_POLL_INTERVAL_SECONDS`
  Optional. Default: `60`

## YAML Config Fallback

If environment variables are not set, both scripts look for:

`D:\DB_repos\eastel-reports\eastel-report-scripts\postgres-to-mongo-usage-sync\config.yml`

You can copy the sample file and edit it:

```powershell
Copy-Item config.sample.yml config.yml
```

You can also pass a different file:

```powershell
python create_mongo_usage_collection.py --config D:\path\to\config.yml
python postgres_to_mongo_usage_sync.py --config D:\path\to\config.yml
```

Priority is:

1. Environment variables
2. YAML config
3. Built-in defaults where available

## Sample Config

See [config.sample.yml](D:/DB_repos/eastel-reports/eastel-report-scripts/postgres-to-mongo-usage-sync/config.sample.yml).

The sync section controls:

- `source_table`
- `batch_size`
- `continuous`
- `poll_interval_seconds`
- `lock_timeout_seconds`

The mongo section controls:

- `uri`
- `database`
- `collection`
- `state_collection`

The postgres section controls:

- `dsn`
  If filled, it is used directly.
- `host`
- `port`
- `database`
- `user`
- `password`
- `sslmode`

## Where Progress Is Saved

The script stores its checkpoint in MongoDB, not in a local file.

By default:

- Database: `eastel-data`
- State collection: `usage_log_sync_state`

Each sync stream stores a document whose `_id` is:

`<source_table>-><mongo_collection>`

Example:

`iot_portal_tb_usage_log_rep->usage_logs`

That document contains:

- `last_usage_log_id`
- `updated_at`
- `source_table`
- `mongo_collection`

That `last_usage_log_id` is the value used on the next run so the script continues from where it stopped.

## Install

```powershell
cd D:\DB_repos\eastel-reports\eastel-report-scripts\postgres-to-mongo-usage-sync
pip install -r requirements.txt
Copy-Item config.sample.yml config.yml
```

## Run Once

This is the mode you would usually use from cron or Task Scheduler.

```powershell
python create_mongo_usage_collection.py
python postgres_to_mongo_usage_sync.py
```

If `sync.continuous` is `false`, the sync script runs one cycle and exits.

## Run Continuously

```powershell
python postgres_to_mongo_usage_sync.py --continuous
```

Continuous mode can be enabled in either of these ways:

- Set `sync.continuous: true` in `config.yml`
- Run the script with `--continuous`

If both are absent, the script runs once and exits.

If `sync.continuous: true` is set in `config.yml`, `--run-once` forces a single sync cycle:

```powershell
python postgres_to_mongo_usage_sync.py --run-once
```

In continuous mode, the script keeps running and polls PostgreSQL every `poll_interval_seconds`.

## Concurrent Runs

The sync script uses a lock document in the MongoDB state collection so only one instance can run at a time for the same source table and target collection.

If a second instance starts while another instance already holds the lock, the second instance exits with an error instead of syncing concurrently.

The lock timeout is controlled by `sync.lock_timeout_seconds`. This allows a stale lock to expire if a process terminates unexpectedly.

## Reset The Checkpoint

Use this only if you want to re-read all PostgreSQL rows from the start. Existing Mongo rows are still safe because the script uses `upsert`.

```powershell
python postgres_to_mongo_usage_sync.py --reset-state
```

## Notes

- The script assumes the PostgreSQL table name and schema match the current usage table.
- The source query orders by `usage_log_id ASC`, so inserts are processed in stable order.
- The checkpoint is updated only after a Mongo batch write succeeds.
