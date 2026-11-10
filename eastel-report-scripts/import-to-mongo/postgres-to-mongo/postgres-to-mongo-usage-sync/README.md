# PostgreSQL To Mongo Usage Sync

This folder contains the standalone usage-log sync flow from PostgreSQL to MongoDB.

## Files

- `config-sample.yml`
- local `config.yml`
- `requirements.txt`
- `create_mongo_usage_collection.py`
- `postgres_to_mongo_usage_sync.py`
- `create-iot_portal_tb_usage_log.sql`
- `test_postgres_connection.py`
- `test_mongo_connection.py`

## Config

Copy the sample file before running:

```powershell
Copy-Item config-sample.yml config.yml
```

The local `config.yml` contains:

- PostgreSQL connection settings
- MongoDB URI, database, usage collection, and state collection
- usage source table and sync tuning values

Important sync tuning fields:

- `batch_size`
  Number of rows fetched from PostgreSQL per internal batch. The script already
  loops until there are no more eligible rows, so one poll cycle can process
  many batches if needed.
- `poll_interval_seconds`
  Sleep time between polling cycles when `continuous: true`.
- `min_record_age_seconds`
  Optional settle-time gate. Only rows with `cr_time <= now() - min_record_age_seconds`
  are eligible to sync. Example: `7200` means "skip rows newer than 120 minutes old".
- `lock_timeout_seconds`
  Mongo sync-lock expiry.
- `write_workers`
  Number of concurrent MongoDB bulk writes (default `1`). Batches are still read
  in `usage_log_id` order and the checkpoint only advances over fully written
  batches, so raising this is safe. Start with `4` and watch the Atlas CPU and
  disk-IOPS metrics of the cluster.

## Throughput

Almost all of a batch's wall time is spent in `mongo_write`. In order of impact:

1. `write_workers: 4` runs several bulk writes at once instead of one.
2. `sync_write_concern: "1"` skips waiting for the Atlas majority acknowledgement.
   Safe here because the checkpoint only moves after a batch completes, and a
   replayed batch is an idempotent upsert.
3. Keep `batch_size` in the 2000-5000 range; much larger batches make the
   checkpoint lag and increase memory use without raising write throughput.
4. Every index on the collection is maintained on each write. `usage_logs`
   currently carries indexes that duplicate each other, for example
   `msisdn_usage_start_service_type_idx` (msisdn, usage_start_time,
   derived.service_type) already covers `ix_msisdn_usage_start_time`. Drop the
   redundant ones with `db.usage_logs.drop_index(...)` after checking the Atlas
   query profiler, and drop the leftover request-log `ix_session_id` when nothing
   queries usage logs by session.
5. If the cluster is already CPU or IOPS saturated, scale the Atlas tier instead;
   extra workers will not help.

## Run

```powershell
python create_mongo_usage_collection.py
python postgres_to_mongo_usage_sync.py
```

`create_mongo_usage_collection.py` is the schema authority for the usage
collection: it drops every unique index except the `uq_usage_log_id` key and then
ensures the usage indexes. Run it whenever the sync reports incompatible unique
indexes (for example `uq_session_request_rating_group`, which belongs to
`request_logs` and rejects usage rows whose request-log fields are absent).
