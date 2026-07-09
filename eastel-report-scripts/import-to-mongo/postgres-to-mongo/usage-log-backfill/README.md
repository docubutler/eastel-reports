# Usage Log Backfill

This folder contains a one-off repair/backfill tool for `usage_logs`.

Use it when Mongo usage-log documents need to be refreshed from the current
PostgreSQL values, especially when PostgreSQL updated usage-related fields after
the row had already been synced once.

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
This keeps long repair jobs simpler and avoids extra comparison cost.

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
- Start narrow, verify the repaired rows, then widen the scope.
