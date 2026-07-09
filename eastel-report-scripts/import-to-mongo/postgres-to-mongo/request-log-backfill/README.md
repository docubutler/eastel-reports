# Request Log Backfill

This folder contains a one-off repair/backfill tool for `request_logs`.

Use it when Mongo documents already exist but need to be refreshed from the
current PostgreSQL row values, for example after PostgreSQL updated rows after
they were first synced.

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

## Progress Logging

The script now:

- counts the total matching PostgreSQL rows before it starts updating
- blindly upserts all matched rows into Mongo
- logs batch progress as:
  - rows updated in the current batch
  - cumulative rows processed
  - total matching rows
  - percentage completed
  - latest processed id

It does not compare PostgreSQL and Mongo row-by-row before updating.
This is intentional to keep repair runs simple and predictable.

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
- Start with a narrow window first, verify results, then widen if needed.
