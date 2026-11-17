# postgres-table-to-s3

Archives a PostgreSQL table to S3 as size-split, gzipped parts, with resumable,
idempotent progress tracking.

Built for moving a rolled-over usage table (for example
`public.iot_portal_tb_usage_log_old20260930`) out of the database and into cheap
object storage.

## Why CSV and not JSON

`COPY ... TO STDOUT (FORMAT csv)` is the fastest export path PostgreSQL has: the
server formats the rows and streams them out, and Python never touches a row.
JSON needs `row_to_json()` per row and costs roughly 1.5-2x more server time.
CSV also preserves `numeric(32,16)` exactly, while JSON would hand the numbers to
a JSON parser.

`format: jsonl` is supported if you specifically want one JSON document per line,
but CSV is the faster and more faithful archive of a relational table.

## No local staging

The export streams **directly into S3**. `COPY` output is gzipped on the fly and
pushed into an S3 multipart upload through an in-memory buffer of
`multipart_part_bytes` (default 8 MiB). Nothing is written to local disk at any
table size, so the host only needs a few megabytes of RAM, not free disk space for
a dump.

If a part grows past `max_part_bytes` (default 50 MiB, measured uncompressed), the
upload is abandoned **before** it is committed and the same key range is retried
with fewer rows — so a bad guess costs a retry, not a broken archive.

## Run

From this directory:

```powershell
pip install -r requirements.txt
Copy-Item -LiteralPath config-sample.yml -Destination config.yml
```

Fill in `postgres` and `s3`, then:

```powershell
py .\postgres_table_to_s3.py
py .\postgres_table_to_s3.py --status      # progress so far
py .\postgres_table_to_s3.py --verify      # row counts: table vs manifest
```

AWS credentials come from the normal boto3 chain (`AWS_PROFILE`, environment
variables, or an instance/task role). Connection settings can also come from
`POSTGRES_DSN` or `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`.
The ignored local `config.yml` is not committed.

`--local-dir .\out` writes the parts and manifest to a folder instead of S3, which
is handy for a dry rehearsal without AWS.

Press Ctrl+C at any point; re-running the same command resumes.

## Output layout

```
<prefix>/<table>_00001.csv.gz
<prefix>/<table>_00002.csv.gz
...
<prefix>/manifest.json
```

The index is zero-padded, so a lexical listing is also numeric order. Each part
lands near `max_part_bytes` (default 50 MiB uncompressed, roughly 15 MiB gzipped).
Every part has its own CSV header, so any part can be loaded on its own; strip the
header (`header: false`) only if you intend to concatenate them first.

## How resume and idempotency work

`manifest.json` lives next to the parts and is the checkpoint. After each part is
uploaded it records:

- `last_key` — the highest `resume_column` value safely stored in S3
- `parts[]` — per part: index, key, rows, bytes, `after_key`, `last_key`, sha256
- `totals` — parts, rows, bytes, bytes stored

Key values are stored type-tagged, for example
`{"__type__": "decimal", "value": "124907541"}`. The production key is
`numeric(20,0)`, which psycopg2 hands back as `Decimal`, so tagging keeps the
resumed comparison numeric rather than turning it into a text comparison.

The next run reads the manifest and continues with `resume_column > last_key`.
A part is only recorded after its upload succeeds, so the resume boundary is
always a complete part; a crash mid-part just redoes that part. Re-running an
interrupted export therefore neither duplicates nor skips rows, as long as the
source table is not changing.

If a part would exceed the size limit by more than 10%, it is discarded and the
same key range is retried with a smaller row count — nothing is uploaded until the
size fits. Row counts are then re-tuned after every part so parts stay near the
target size.

`--restart` ignores the manifest and starts again at part 1. Prefer a fresh
`prefix` when you restart, so an abandoned part cannot be picked up later.

## Requirements on the source table

- `resume_column` must be **unique and indexed** — it is the cursor. The primary
  key (`usage_log_id`) is the natural choice.
- The table should be **static** during the export. Appends are picked up on the
  next part; rows updated or deleted mid-run are not re-read.
- One writer at a time. Two concurrent runs against the same prefix will fight
  over the manifest.

## Restoring the parts

`restore_from_s3.py` does the whole of the below automatically: it streams each
part from S3 through gunzip straight into `COPY ... FROM STDIN` (no local disk),
verifies each part's sha256 against the manifest and rolls that part back on a
mismatch, and records progress in `restore-state.json` so it can resume.

```powershell
py .\restore_from_s3.py --status
py .\restore_from_s3.py
py .\restore_from_s3.py --verify
```

Each part is plain gzipped CSV, so a single part also loads by hand:

```powershell
psql -c "\copy public.iot_portal_tb_usage_log_old20260930 FROM PROGRAM 'gunzip -c iot_portal_tb_usage_log_old20260930_00001.csv.gz' WITH (FORMAT csv, HEADER true)"
```

To load everything, keep the header on the first part only:

```powershell
Get-ChildItem *.csv.gz | Sort-Object Name | ForEach-Object {
    $header = if ($_ -eq (Get-ChildItem *.csv.gz | Sort-Object Name)[0]) { "true" } else { "false" }
    psql -c "\copy staging_table FROM PROGRAM 'gunzip -c $($_.Name)' WITH (FORMAT csv, HEADER $header)"
}
```

Load into a *staging* table first and compare row counts with the manifest before
swapping anything. `--verify` gives you the manifest total to compare against.

If the archive is destined for MongoDB later, load the CSV into PostgreSQL first
and transform from there — that keeps the numeric precision that a direct CSV to
BSON conversion would lose.

## Notes and limits

- Single-threaded by design. `COPY` is server-side and usually saturates the
  connection; if throughput is short, the next step is parallel workers over
  disjoint `resume_column` ranges.
- Memory use is bounded by `multipart_part_bytes` (8 MiB by default) plus gzip
  buffers. Local disk use is zero — the archive never lands on the host.
- Deleting the source table is deliberately **not** part of this script. Verify
  the S3 object count and row totals first, then do it as a separate step.
