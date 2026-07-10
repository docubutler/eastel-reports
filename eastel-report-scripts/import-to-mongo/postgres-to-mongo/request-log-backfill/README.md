# Request Log Backfill

This folder contains a one-off repair/backfill tool for `request_logs`.

Use it when Mongo documents need to be refreshed from current PostgreSQL row
values, or when matching Mongo documents are missing and should be inserted by
the repair run. The script uses Mongo upserts, so it can both update existing
documents and insert missing ones.

## Files

- `backfill_request_logs.py`
- `config.yml`
- `config-sample.yml`

## Scope Options

The repair scope is selected by `backfill.mode` in `config.yml` or by `--mode`.

Supported modes:

- `ids`
- `id_range`
- `time`

Only the properties relevant to the selected mode are used. Other populated
properties are ignored.

## Recommended Usage

For stale request-log rows, prefer time-based repair using `up_time`, because
that targets rows that were updated after insert.

Example:

```powershell
py .\backfill_request_logs.py --time-field up_time --start 2026-05-16T00:00:00 --end 2026-05-20T00:00:00
```

## Examples

Repair exact IDs:

```powershell
py .\backfill_request_logs.py --ids 191392446,191398089,194661431
```

Repair by request event time:

```powershell
py .\backfill_request_logs.py --time-field req_time --start 2026-05-16T00:00:00 --end 2026-05-20T00:00:00
```

Repair by update time:

```powershell
py .\backfill_request_logs.py --time-field up_time --start 2026-05-16T00:00:00 --end 2026-05-20T00:00:00
```

Repair by creation time:

```powershell
py .\backfill_request_logs.py --time-field cr_time --start 2026-05-16T00:00:00 --end 2026-05-20T00:00:00
```

Repair by ID range:

```powershell
py .\backfill_request_logs.py --id-from 190000000 --id-to 196000000
```

Use a smaller batch size if the database is under load:

```powershell
py .\backfill_request_logs.py --time-field up_time --start 2026-05-16T00:00:00 --end 2026-05-20T00:00:00 --batch-size 250
```

Time mode with an age gate:

```powershell
py .\backfill_request_logs.py --time-field up_time --start 2026-05-16T00:00:00 --end 2026-05-20T00:00:00 --min-record-age-seconds 7200
```

## Temporary Sync History

The backfill script now uses a temporary Mongo collection named
`request_synced` by default.

Purpose:

- store request IDs already handled by this backfill flow
- avoid re-upserting the same `request_log_id` in later backfill runs
- make restart or rerun behavior more predictable

Behavior:

- Mongo creates the collection automatically on first write
- the script ensures indexes before use
- Mongo always has the default `_id` index
- the script also creates:
  - a unique index on `(source_table, mongo_collection, request_log_id)`
  - a non-unique index on `request_log_id`

## Progress Logging

The script now:

- prints an explicit startup message before counting begins
- counts the total matching PostgreSQL rows before it starts updating
- checks `request_synced` before upserting a batch
- upserts only rows not already marked in `request_synced`
- marks successfully upserted IDs into `request_synced`
- logs batch progress as:
  - rows repaired in the current batch
  - rows skipped because they were already marked
  - cumulative rows processed
  - total matching rows
  - percentage completed
  - latest processed id

The script still does not compare PostgreSQL and Mongo document contents
row-by-row before updating.

## Time Mode Age Gate

`min_record_age_seconds` applies only to `time` mode.

Behavior:

- `time` mode filters on the selected `time_field` window
- `time` mode also requires `cr_time <= now - min_record_age_seconds`
- `ids` mode ignores `min_record_age_seconds`
- `id_range` mode ignores `min_record_age_seconds`

With `min_record_age_seconds: 7200`, rows newer than 2 hours by `cr_time` are
excluded from the time-based count and processing.

## CLI vs Config

- If `--mode` is provided, it overrides `backfill.mode` from config.
- If a CLI option for the chosen mode is provided, it overrides the corresponding config value.
- If multiple filtering families are supplied, the selected mode decides which one is used.

Examples:

- `--mode ids --ids 1,2,3 --start ... --end ...`
  Only `ids` is used. The time values are ignored.
- `--mode time --start ... --end ... --ids 1,2,3`
  Only the time range is used. The ids are ignored.

## Recommendations

- Prefer `up_time` when the issue is "row was synced before final update".
- Prefer `--ids` when you already have exact suspect `request_log_id` values.
- Prefer ID range only when the bad rows are known to be contiguous.
- Prefer `min_record_age_seconds` in time mode when very recent rows should be left alone.
- Start with a narrow window first, verify results, then widen if needed.
