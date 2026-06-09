# SMSC CDR To Mongo Sync

This folder contains the MongoDB workflow for importing SMSC CDR files.

## Files

- `smsc_cdr_to_mongo_sync.py`: main importer
- `create_mongo_smsc_cdr_collection.py`: creates Mongo collections and indexes
- `config.yml`: runtime configuration
- `requirements.txt`: Python dependencies

## Behavior

- Reads files matching `cdr.log.YYYY-MM-DD` and `cdr.log.YYYY-MM-DD.gz`
- Ignores files that do not exactly match those formats, including plain `cdr.log`
- Only processes files whose date is before the current day
- Backfills all historical eligible files on first run
- Computes a full-file hash once per eligible file using `blake2b-256`
- Uses file-level locking, not collection-level locking
- Uses Mongo upserts keyed by `server_name + file_hash + line_number`
- Keeps permanent per-file metadata in a dedicated meta collection
- Keeps resumable progress for incomplete files
- Moves completed source files into `source.processed_dir`
- Logs to console and a configured log file

## File Housekeeping

The housekeeping flow is intentionally isolated from parsing and Mongo upserts.

## Accepted File Formats

The importer only processes these exact filename formats:

- `cdr.log.YYYY-MM-DD`
- `cdr.log.YYYY-MM-DD.gz`

Examples:

- `cdr.log.2026-05-01`
- `cdr.log.2026-05-01.gz`

The importer ignores:

- plain `cdr.log`
- current writer files that do not include a finished date suffix
- unrelated files in the same directory
- any filename that does not exactly match the patterns above

The importer also ignores files whose parsed date is the current day or later.

### Plain files

- A plain `cdr.log.YYYY-MM-DD` file is processed directly from `source.input_dir`.
- Only after the file completes successfully is it moved to `source.processed_dir`.
- If the script dies before completion, the file remains in `source.input_dir` and is resumed from there on the next run.

### Gzip files

- A `cdr.log.YYYY-MM-DD.gz` file is extracted to a temporary file outside the input directory.
- The extracted temporary file name is the logical uncompressed name, for example:
  `cdr.log.2026-05-01.gz` -> temp file `cdr.log.2026-05-01`
- The temporary extracted file is created under the system temp directory in a unique UUID-based folder for each run, so it does not overwrite a previous extraction.
- The extracted temporary file is hashed and processed.
- After successful completion, the temporary extracted file is deleted and the original `.gz` file is moved to `source.processed_dir`.
- If the script dies before completion, the original `.gz` file remains in `source.input_dir`, so the next run starts from the input directory again.
- On the next run after a crash, the importer extracts the `.gz` file again to a fresh temp path and resumes from the saved line checkpoint using the same file hash.

### Processed directory behavior

- The importer can keep `processed_dir` outside `input_dir` or inside it.
- If `processed_dir` is inside `input_dir`, the importer explicitly skips that subtree during discovery.
- The move preserves the relative path under `processed_dir`.
- If the target path already exists in `processed_dir`, the importer writes the moved file with a timestamped suffix instead of overwriting the existing file.

## Extraction And Processing Sequence

For a plain file:

1. Discover a file matching `cdr.log.YYYY-MM-DD`
2. Hash the file contents
3. Check permanent file meta using `server_name + file_hash`
4. Skip, resume, or process
5. After successful completion, move the source file to `processed_dir`

For a `.gz` file:

1. Discover a file matching `cdr.log.YYYY-MM-DD.gz`
2. Extract it to a temporary uncompressed file in the system temp directory
3. Hash the extracted file contents
4. Check permanent file meta using `server_name + file_hash`
5. Skip, resume, or process
6. Delete the extracted temporary file
7. After successful completion or duplicate skip, move the original `.gz` file to `processed_dir`

This housekeeping is separated from the Mongo parsing/upsert path so the ingestion logic and the file movement logic remain isolated.

## Identity And Dedupe

The importer now has two levels of identity.

### File identity

A file is treated as the same logical file when these match:

- `server_name`
- `file_hash`

This means:

- copying the same file to a different directory on the same server does not create duplicate processing
- the same filename on `server1` and `server2` remains distinct because `server_name` is part of the identity
- filename alone is not used as the durable dedupe key
- if a file that is already known by hash is encountered again, it is skipped and moved to `processed_dir`

The file hash is a full-file hash, not a partial hash of the first few bytes or lines.

### Row identity

Within a file, one CDR line is treated as unique by:

- `server_name`
- `file_hash`
- `line_number`

The importer stores this as `identity_key` and upserts on it.

### Why not `MESSAGE_ID`

`MESSAGE_ID` is stored and indexed for querying, but it is not used as a unique key because it is not globally unique in the source data.

For example, the same logical id can appear in multiple related records such as:

- a `message` record
- a `dlr` record

So using `MESSAGE_ID` as a unique identifier would risk collapsing distinct CDR rows into one document.

## Permanent Meta Collection

The importer keeps a permanent file metadata record for each processed logical file.

The meta record is keyed by:

- `mongo_collection`
- `server_name`
- `file_hash`

The meta collection stores operational history such as:

- `file_name`
- `relative_path`
- `source_full_path`
- `seen_paths`
- `seen_full_paths`
- `file_size`
- `last_modified_at`
- `total_lines`
- `status`
- `last_processed_line`
- `records_upserted`
- `parse_errors`
- `invalid_prefix_lines`
- `hash_duration_seconds`
- `count_duration_seconds`
- `read_duration_seconds`
- `write_duration_seconds`
- `started_at`
- `process_completed_at`
- `first_seen_at`
- `last_seen_at`

This collection is intended to remain permanent so you can see which files were processed, when they were first seen, and from which paths they were observed over time.

## Resume And Skip Rules

- If `server_name + file_hash` is new, the file is processed from the beginning.
- If the same `server_name + file_hash` is found with `status=completed`, the file is skipped and a warning is logged.
- If the same `server_name + file_hash` is found with an incomplete status, the importer resumes from `last_processed_line`.
- If the same file is copied into another directory on the same server, it is recognized by hash and skipped instead of duplicated.

`--reset-state` now resets resumable state and stale locks for incomplete files on the configured server, but it does not delete completed file meta history.

## Locking

Locks are now per file, not per collection.

That allows:

- multiple importer processes to use the same MongoDB database at the same time
- different SMSC scripts to work in parallel on different files
- stale lock cleanup to affect only the specific file that was being processed

The lock key is effectively based on:

- `mongo_collection`
- `server_name`
- `file_hash`

## Logging

The script logs to:

- console
- the configured `logging.file_path`

You should see hash and file lifecycle events in the logs, including:

- plain file selection
- gzip file discovery
- gzip extraction start and completion
- temporary extraction path
- temporary extracted file deletion
- processed-file move start and completion
- file hashing start and completion
- file skip because the same hash was already completed
- file resume because an incomplete meta record exists
- file-level lock activity
- batch checkpoints
- parse and mapping warnings

If `logging.file_path` is configured, the same events shown in console are also written to the log file.

Malformed-line audit output is separate:

- `logging.error_file_path`
  Writes only erroneous line references to a file
- each entry includes timestamp, error type, `server_name`, file name, relative path, and line number
- current error types written there are `INVALID_PREFIX` and `CSV_PARSE_ERROR`

## CDR field spec

The Mongo importer follows the same working field order as `smsc_cdr_parser.py`.
In the real CDR payloads used here, there is no populated `SUBMIT_DATE` column.
Some rows also include one trailing empty extra column, which the importer keeps in `extra_fields`.

| Position | Column | Meaning |
| -------- | ------ | ------- |
| 1 | `DELIVERY_DATE` | Time CDR generated / delivery completed |
| 2 | `ADDR_SRC_DIGITS` | Source number |
| 3 | `ADDR_SRC_TON` | Source TON |
| 4 | `ADDR_SRC_NPI` | Source NPI |
| 5 | `ADDR_DST_DIGITS` | Destination number |
| 6 | `ADDR_DST_TON` | Destination TON |
| 7 | `ADDR_DST_NPI` | Destination NPI |
| 8 | `Message_Delivery_Status` | `success` / `failed` / `ocs_rejected` etc |
| 9 | `ORIGINATION_TYPE` | `SMPP` / `SS7_MO` / `LOCAL_ORIG` etc |
| 10 | `MESSAGE_TYPE` | `message` / `dlr` |
| 11 | `ORIG_SYSTEM_ID` | SMPP system id |
| 12 | `MESSAGE_ID` | Internal message id |
| 13 | `DVL_MESSAGE_ID` | SMPP delivery-side message id |
| 14 | `RECEIPT_LOCAL_MESSAGE_ID` | Original message id for DLR correlation |
| 15 | `NNN_DIGITS` | MSISDN from SRI response |
| 16 | `IMSI` | Subscriber IMSI |
| 17 | `CORR_ID` | Home-routing correlation id |
| 18 | `ORIGINATOR_SCCP_ADDRESS` | SCCP source address |
| 19 | `MtServiceCenterAddress` | SMSC GT address |
| 20 | `ORIG_NETWORK_ID` | Origin network id |
| 21 | `NETWORK_ID` | Destination network id |
| 22 | `MPROC_NOTES` | Notes from processing rules |
| 23 | `MSG_PARTS` | Multipart SMS count |
| 24 | `CHAR_NUMBERS` | Character count |
| 25 | `PROCESSING_TIME` | SMSC processing time (ms) |
| 26 | `DELIVERY_DELAY` | Delivery delay (ms) |
| 27 | `SCHEDULE_DELIVERY_DELAY` | Scheduled delay |
| 28 | `DELIVERY_COUNT` | Delivery attempts |
| 29 | `First 20 characters of SMS` | SMS preview |
| 30 | `Reason_For_Failure` | Failure reason |

## Run

Install dependencies:

```powershell
pip install -r .\requirements.txt
```

Create collections and indexes:

```powershell
python .\create_mongo_smsc_cdr_collection.py
```

Run once:

```powershell
python .\smsc_cdr_to_mongo_sync.py --run-once
```

Run continuously:

```powershell
python .\smsc_cdr_to_mongo_sync.py --continuous
```

## Config

Edit [config.yml](/d:/DB_repos/eastel-reports/eastel-report-scripts/smsc-cdr-to-mongo-sync/config.yml) before running.

Important config values:

- `source.server_name`
  Required. Distinguishes one SMSC/source environment from another.
- `source.input_dir`
  Root directory scanned recursively for `cdr.log.YYYY-MM-DD` files.
- `source.processed_dir`
  Destination directory where successfully completed source files are moved.
- `mongo.smsc_cdr_collection`
  Destination CDR collection.
- `mongo.smsc_cdr_state_collection`
  Collection used for cycle state and file locks.
- `mongo.smsc_cdr_file_meta_collection`
  Permanent processed-file metadata collection.
- `logging.file_path`
  Log file path. Console events are also written here when configured.
- `logging.error_file_path`
  File-only audit log for malformed line numbers and file details.
