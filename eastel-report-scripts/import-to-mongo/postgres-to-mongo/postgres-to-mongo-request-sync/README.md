# PostgreSQL To Mongo Request Sync

This folder contains the standalone request-log sync flow from PostgreSQL to MongoDB.

## Files

- `config-sample.yml`
- local `config.yml`
- `requirements.txt`
- `create_mongo_request_log_collection.py`
- `postgres_to_mongo_request_log_sync.py`
- `drop_request_log_reporting_indexes.py`
- `recreate_request_log_reporting_indexes.py`
- `release_request_log_sync_lock.py`
- `test_postgres_connection.py`
- `test_mongo_connection.py`

## Config

Copy the sample file before running:

```powershell
Copy-Item config-sample.yml config.yml
```

The local `config.yml` contains:

- PostgreSQL connection settings
- MongoDB URI, database, request collection, and state collection
- request source table and sync tuning values

## Run

```powershell
python create_mongo_request_log_collection.py
python postgres_to_mongo_request_log_sync.py
```
