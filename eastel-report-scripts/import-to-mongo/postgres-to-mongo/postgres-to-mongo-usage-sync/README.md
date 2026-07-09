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

## Run

```powershell
python create_mongo_usage_collection.py
python postgres_to_mongo_usage_sync.py
```
