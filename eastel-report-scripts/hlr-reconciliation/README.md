# HLR/BOSS/IOT Monthly Reconciliation

Production-grade Python application for monthly reconciliation of active subscriber records across:

- HLR file feed
- BOSS CRM in MySQL
- IOT BSS in PostgreSQL

The application downloads the monthly HLR archive, imports the HLR snapshot into MongoDB, fetches active subscriber keys from BOSS and IOT using configurable SQL, compares each unique `(IMSI, MSISDN)` pair, stores historical comparison results, generates a CSV report, emails it, and records execution history.

## Current Status

This project is self-contained under `hlr-reconciliation/`.

Database access is intentionally not hardcoded. When MySQL/PostgreSQL access is granted, update `config.yml` with credentials and SQL queries.

## Query Contract

BOSS and IOT queries are configurable, but both must return columns in this order:

```sql
SELECT msisdn, imsi
FROM ...
```

- Column 1: `msisdn`
- Column 2: `imsi`
- Extra columns are ignored in Phase 1.

This contract keeps the reconciliation engine independent from source database schema differences.

## Folder Layout

```text
hlr-reconciliation/
  main.py
  mongo_init.py
  config-sample.yml
  requirements.txt
  README.md
  src/hlr_reconciliation/
    boss/
    comparison/
    config/
    core/
    email/
    hlr/
    iot/
    logging/
    models/
    mongo/
    reporting/
    transfer/
    utils/
  tests/
```

## Setup

```bash
cd hlr-reconciliation
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config-sample.yml config.yml
```

Edit `config.yml`. Sensitive values should come from environment variables such as:

```bash
export MONGO_URI='mongodb://user:password@host:27017/?authSource=admin'
export BOSS_MYSQL_HOST='...'
export BOSS_MYSQL_USERNAME='...'
export BOSS_MYSQL_PASSWORD='...'
export IOT_POSTGRES_HOST='...'
export IOT_POSTGRES_USERNAME='...'
export IOT_POSTGRES_PASSWORD='...'
```

## Commands

Validate non-secret config structure:

```bash
python main.py --config config.yml validate-config
```

Create MongoDB collections and indexes:

```bash
python main.py --config config.yml init-db
```

or:

```bash
python mongo_init.py --config config.yml
```

Run reconciliation for the current month:

```bash
python main.py --config config.yml run
```

Run reconciliation for a specific month:

```bash
python main.py --config config.yml run --month 2026-07
```

Clean up a month before reprocessing:

```bash
python main.py --config config.yml cleanup-month 2026-07 --force
```

## HLR File

Expected archive:

```text
MVNO_ANCHOR_2026070102.tar.gz
```

Expected CSV headers:

```text
IMSI,MSISDN,IMEISV
```

Phase 1 comparison uses only `IMSI` and `MSISDN`. `IMEISV` is parsed and stored in MongoDB.

## Data Flow

```text
CLI
  -> load YAML config and env vars
  -> configure rotating logs
  -> initialize MongoDB collections/indexes if missing
  -> derive processing_month and deterministic batch_id
  -> abort if execution_history already has SUCCESS for that month
  -> download latest HLR archive by FTP/SFTP/local mode
  -> validate and extract tar.gz
  -> parse and validate CSV
  -> insert HLR monthly snapshot into MongoDB
  -> fetch BOSS active subscribers from MySQL
  -> fetch IOT active subscribers from PostgreSQL
  -> compare all unique IMSI/MSISDN keys
  -> insert comparison_results into MongoDB
  -> generate CSV report
  -> email report
  -> update execution_history
```

## MongoDB Collections

### `execution_history`

One document per execution attempt.

Important fields:

- `batch_id`
- `execution_id`
- `processing_month`
- `execution_timestamp`
- `completion_timestamp`
- `status`
- `source_filename`
- `source_file_hash`
- `HLR record count`
- `CRM record count`
- `IOT record count`
- `comparison record count`
- `execution duration`
- `report filename`
- `remarks`

### `hlr_records`

Immutable monthly HLR snapshot.

- `batch_id`
- `processing_month`
- `import_timestamp`
- `IMSI`
- `MSISDN`
- `IMEISV`

### `comparison_results`

Historical reconciliation result.

- `batch_id`
- `processing_month`
- `execution_timestamp`
- `IMSI`
- `MSISDN`
- `inHLR`
- `inCRM`
- `inBSS`

## MongoDB Initialization

Initialization is idempotent.

The initializer creates missing collections and indexes only. It is available as an independent script and is also called by `main.py run` before processing.

Recommended indexes are created for:

- successful monthly idempotency in `execution_history`
- month/batch filtering
- IMSI/MSISDN lookup
- processing-month plus IMSI/MSISDN historical reporting

## Monthly Idempotency

The deterministic batch ID is:

```text
YYYYMM
```

Example:

```text
202607
```

If a successful execution already exists for the processing month, the app aborts before inserting new records:

```text
Processing has already been completed for month YYYY-MM (Batch ID: YYYYMM). Please execute the monthly cleanup utility before reprocessing this month.
```

To reprocess, run cleanup first.

## Cleanup

Cleanup removes all records for a processing month from:

- `hlr_records`
- `comparison_results`
- `execution_history`

Cleanup requires `--force` and is fully logged.

## Logging

Logging uses Python's `logging` module with `TimedRotatingFileHandler`.

Each entry includes:

- timestamp
- log level
- logger/module name
- function name
- message

Secrets are redacted from common `password=`, `secret=`, `token=`, and `uri=` patterns.

## Scheduling On Linux

Recommended systemd timer model:

```ini
[Unit]
Description=HLR monthly reconciliation

[Service]
Type=oneshot
WorkingDirectory=/opt/hlr-reconciliation
EnvironmentFile=/etc/hlr-reconciliation/env
ExecStart=/opt/hlr-reconciliation/.venv/bin/python main.py --config config.yml run
```

Run monthly using a systemd timer or cron after confirming the HLR file is available.

## Security

- Prefer SFTP over FTP.
- Keep `config.yml` out of source control when it contains real values.
- Use environment variables or a secret manager for credentials.
- Do not log SQL credentials, SMTP passwords, MongoDB URIs, or transfer passwords.
- Use least-privilege database users.
- Enable TLS/SSL for MongoDB, PostgreSQL, MySQL, and SMTP where available.

## Testing

Run:

```bash
pytest
```

Tests cover:

- config loading and validation
- batch ID derivation
- HLR CSV/archive parsing
- comparison uniqueness and flags
- Mongo initializer idempotency with fakes
- cleanup deletion scope with fakes
- CSV report output
- source adapter row-shape conversion for MySQL/PostgreSQL
- mocked end-to-end reconciliation flow

## Extension Points

- Add Excel report writer by implementing another reporting strategy.
- Add source systems by introducing another adapter returning `SubscriberKey`.
- Add REST/web dashboard on top of MongoDB historical collections.
- Add Prometheus metrics around counts, durations, and failures.
- Move deployment to Docker/Kubernetes without changing core business logic.
