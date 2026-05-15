# SMSC CDR Ingestor and Parser

This folder contains two Python scripts that are meant to be run in sequence:

1. `smsc_cdr_ingestor.py`
2. `smsc_cdr_parser.py`

The first script loads raw SMSC CDR log lines into MySQL. The second script reads those raw rows, splits the CSV payload into columns, and inserts the parsed data into a parsed table.

## What each script does

### `smsc_cdr_ingestor.py`

- Scans all files under `INPUT_DIR` recursively
- Extracts the CDR payload from each log line
- Inserts the raw CDR text into table `smsc_record`
- Tracks processed files in `smsc_processed_file`
- Writes:
  - `ingestion_summary.txt`
  - `ingestion_errors.txt`

### `smsc_cdr_parser.py`

- Reads rows from `smsc_record`
- Only processes rows where `processed_flag = 0`
- Parses `raw_cdr` as CSV
- Inserts parsed columns into `smsc_record_parsed`
- Marks the raw row as processed by updating `smsc_record.processed_flag = 1`

## Run order

Run them in this order:

1. Run `smsc_cdr_ingestor.py` first
2. After ingestion completes, run `smsc_cdr_parser.py`

If you run the parser first, it will not have any raw records to parse.

## Before you run

Both scripts have hardcoded configuration at the top of the file. Review and update these values before running:

### In `smsc_cdr_ingestor.py`

- `DB_CONFIG`
- `INPUT_DIR`
- `TABLE_NAME`
- `BATCH_SIZE`

### In `smsc_cdr_parser.py`

- `DB_CONFIG`
- `BATCH_SIZE`

## Database prerequisites

The ingestor creates these tables if they do not exist:

- `smsc_record`
- `smsc_processed_file`

However, the parser expects additional schema that is **not created by the scripts in this folder**:

- `smsc_record.processed_flag` column
- `smsc_record_parsed` table

So before running `smsc_cdr_parser.py`, make sure:

1. `smsc_record` contains a `processed_flag` column, typically defaulting to `0`
2. `smsc_record_parsed` already exists with the columns used by the parser

If those objects do not exist, the parser will fail.

## Suggested table checks

Run these in MySQL before running the parser:

```sql
DESCRIBE smsc_record;
DESCRIBE smsc_record_parsed;
```

You should confirm:

- `smsc_record` has `id`, `raw_cdr`, and `processed_flag`
- `smsc_record_parsed` has all insert target columns used in `smsc_cdr_parser.py`

## Python requirements

These scripts require:

- Python 3
- `mysql-connector-python`

Install dependency if needed:

```powershell
pip install mysql-connector-python
```

## How to run

Open PowerShell in this folder:

```powershell
cd D:\DB_repos\eastel-reports\eastel-report-scripts\smsc-cdr-ingestor-and-parser
```

Run ingestion:

```powershell
python .\smsc_cdr_ingestor.py
```

Then run parsing:

```powershell
python .\smsc_cdr_parser.py
```

## Expected output

### Ingestor

You should see console output like:

- total files found
- each file being processed
- inserted row progress
- completion summary

It also writes:

- `ingestion_summary.txt`
- `ingestion_errors.txt`

Both files are created under the configured `INPUT_DIR`.

### Parser

You should see console output like:

- `Processed batch of 1000 rows`
- `No more records to process.`

## Operational notes

- The ingestor skips files already recorded in `smsc_processed_file`
- The ingestor walks subfolders recursively
- The parser processes records in batches using `LIMIT %s`
- Rows that fail CSV parsing are silently skipped by the parser because `parse_row()` returns `None`

## Quick checklist

Before running:

1. Update DB connection details in both scripts
2. Update `INPUT_DIR` in `smsc_cdr_ingestor.py`
3. Confirm MySQL is reachable
4. Confirm `smsc_record_parsed` exists
5. Confirm `smsc_record.processed_flag` exists

Execution order:

1. `python .\smsc_cdr_ingestor.py`
2. `python .\smsc_cdr_parser.py`

