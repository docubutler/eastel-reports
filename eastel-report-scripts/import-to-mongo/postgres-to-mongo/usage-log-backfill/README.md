# Usage Log Backfill

This folder contains a one-off repair/backfill tool for `usage_logs`.

Use it when Mongo usage-log documents need to be refreshed from the current
PostgreSQL values, especially when PostgreSQL updated usage-related fields after
the row had already been synced once. The script uses Mongo upserts, so it can
both update existing documents and insert missing ones.

## Files

- `backfill_usage_logs.py`
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

For stale usage-log rows, prefer time-based repair using `usage_update_time`.
If that field is unreliable for a case, use `up_time`.

Example:

```powershell
py .\backfill_usage_logs.py --time-field usage_update_time --start 2026-06-30T00:00:00 --end 2026-07-01T00:00:00
```

## Examples

Repair exact IDs:

```powershell
py .\backfill_usage_logs.py --ids 202170656,202170657
```

Repair by usage event time:

```powershell
py .\backfill_usage_logs.py --time-field usage_start_time --start 2026-06-30T00:00:00 --end 2026-07-01T00:00:00
```

Repair by usage update time:

```powershell
py .\backfill_usage_logs.py --time-field usage_update_time --start 2026-06-30T00:00:00 --end 2026-07-01T00:00:00
```

Repair by generic row update time:

```powershell
py .\backfill_usage_logs.py --time-field up_time --start 2026-06-30T00:00:00 --end 2026-07-01T00:00:00
```

Repair by ID range:

```powershell
py .\backfill_usage_logs.py --id-from 202000000 --id-to 203000000
```

Use a smaller batch size if needed:

```powershell
py .\backfill_usage_logs.py --time-field usage_update_time --start 2026-06-30T00:00:00 --end 2026-07-01T00:00:00 --batch-size 250
```

Time mode with an age gate:

```powershell
py .\backfill_usage_logs.py --time-field usage_update_time --start 2026-06-30T00:00:00 --end 2026-07-01T00:00:00 --min-record-age-seconds 7200
```

## Temporary Sync History

The backfill script now uses a temporary Mongo collection named
`usage_synced` by default.

Purpose:

- store usage IDs already handled by this backfill flow
- avoid re-upserting the same `usage_log_id` in later backfill runs
- make restart or rerun behavior more predictable

Behavior:

- Mongo creates the collection automatically on first write
- the script ensures indexes before use
- Mongo always has the default `_id` index
- the script also creates:
  - a unique index on `(source_table, mongo_collection, usage_log_id)`
  - a non-unique index on `usage_log_id`

## Progress Logging

The script now:

- prints an explicit startup message before counting begins
- counts the total matching PostgreSQL rows before it starts updating
- checks `usage_synced` before upserting a batch
- upserts only rows not already marked in `usage_synced`
- marks successfully upserted IDs into `usage_synced`
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

- `--mode ids --ids 202170656,202170657 --start ... --end ...`
  Only `ids` is used. The time values are ignored.
- `--mode time --start ... --end ... --ids 202170656,202170657`
  Only the time range is used. The ids are ignored.

## Recommendations

- Prefer `usage_update_time` for data-correction backfills.
- Prefer `--ids` when you already know the exact bad rows.
- Prefer ID range only when the affected rows are contiguous.
- Prefer `min_record_age_seconds` in time mode when very recent rows should be left alone.
- Start narrow, verify the repaired rows, then widen the scope.
