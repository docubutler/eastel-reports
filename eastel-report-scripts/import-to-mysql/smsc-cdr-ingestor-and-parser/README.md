# SMSC CDR Ingestor and Parser

This folder contains the original MySQL workflow only:

1. `smsc_cdr_ingestor.py`
2. `smsc_cdr_parser.py`

These files were not changed as part of the MongoDB work.

## What each script does

### `smsc_cdr_ingestor.py`

- Scans files under the configured input path
- Extracts the CDR payload from each log line
- Inserts the raw CDR text into MySQL table `smsc_record`
- Tracks processed files in `smsc_processed_file`

### `smsc_cdr_parser.py`

- Reads rows from `smsc_record`
- Parses the CSV payload
- Inserts parsed fields into `smsc_record_parsed`

## Run order

Run them in this order:

1. `python .\smsc_cdr_ingestor.py`
2. `python .\smsc_cdr_parser.py`

## MongoDB version

The new MongoDB importer has been moved to:

[smsc-cdr-to-mongo-sync](/d:/DB_repos/eastel-reports/eastel-report-scripts/smsc-cdr-to-mongo-sync)

That folder contains:

- `smsc_cdr_to_mongo_sync.py`
- `create_mongo_smsc_cdr_collection.py`
- its own `config.yml`
- its own `requirements.txt`
