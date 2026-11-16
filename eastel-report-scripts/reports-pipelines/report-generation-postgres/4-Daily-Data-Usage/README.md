# 4-Daily-Data-Usage — PostgreSQL

Produces the day-wise 4G / 5G domestic data usage report requested for the
U Mobile CDR reconciliation, in this exact shape:

```
Date | 4G Usage (MBYTE) | 5G Usage (MBYTE) | Total Usage
```

One row per calendar day in the report window, sourced from a read-only
PostgreSQL connection. Days with no qualifying records are written as `0.00`
so the reconciliation always shows every date in the month.

## Run

From this directory:

```powershell
pip install -r requirements.txt
Copy-Item -LiteralPath config-sample.yml -Destination config.yml
```

Configure the connection in `config.yml`, or supply `POSTGRES_DSN` or the standard
`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSSLMODE` variables.
Environment values override the corresponding config fields. The ignored local
`config.yml` is not committed.

```powershell
python .\generate_report.py
python .\generate_report.py --start-date 2026-10-01 --end-date 2026-10-31
python .\generate_report.py --usage-table public.iot_portal_tb_usage_log --output october-daily.csv
python .\generate_report.py --dry-run
```

`--config`, `--output`, and `--usage-table` are also available. `--dry-run` prints
the final SQL and bound parameters without connecting. Output paths are relative
to the config directory.

## Dates and source tables

`start_date` and `end_date` are inclusive calendar dates in `YYYY-MM-DD` format.
The internal window is `start_date 00:00 <= usage_start_time < end_date + 1 day`.
The dates use the stored Postgres timestamp convention without timezone shifts;
confirm the business timezone before presenting figures to U Mobile.

Each run reads the single table configured in `tables.usage_log_table`. It does
not search or combine archives. The sample selects
`public.iot_portal_tb_usage_log`; September data lived in
`public.iot_portal_tb_usage_log_old20260930` because the live table rolled over on
October 1, so switch the config value when a month lives in an archive.

## What the numbers mean

The row definition is deliberately identical to the Invoice Recon data queries
(`../2-Invoice-Recon/usage-queries/Q006.sql` and `Q007.sql`), so the sum of all
daily rows ties back to that report:

| Rule | Value |
|---|---|
| Data records | `rat_type IN ('4G', '5G')` |
| Location | `roaming_destination_id = 87` (domestic) |
| Excluded rating group | `COALESCE(rating_group, '') <> '500003'` |
| Volume column | `act_usage_unit` — actual bytes, not `usage_unit` (billed) |
| MB conversion | bytes / `1048576` (MiB) |

`Total Usage` is the 4G + 5G byte total converted the same way, so it is not
always exactly `4G + 5G` after rounding.

## Limitations to state alongside the report

- **Domestic only.** Roaming 4G/5G (`roaming_destination_id <> 87`) is excluded.
- **MiB, not decimal MB.** If U Mobile reports decimal megabytes, the two numbers
  will not match; change the divisor to `1000000` in
  `queries/daily-data-usage.sql` for a like-for-like comparison.
- **Record maturity.** Data sessions are only final at `req_type = 'T'` in
  `iot_portal_tb_request_log`. This report reads the usage log, so verify that the
  sync for the requested month is complete before treating it as definitive.
- Only days present in `start_date`..`end_date` are emitted; the report does not
  extrapolate or backfill missing days.
