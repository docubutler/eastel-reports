# Invoice Recon Report Pipeline

This folder is set up as a multi-report PostgreSQL pipeline for the sample reconciliation outputs in `recon-report-samples`.

## Files

- `config.yml`
  Holds PostgreSQL settings, runtime dates, and the list of CSV reports to generate.
- `queries.sql`
  Single source SQL file for all invoice recon reports.
- `split_queries.py`
  Splits `queries.sql` into numbered files under `generated-queries`.
- `generate_report.py`
  Executes the required split queries and renders every configured output CSV.
- `templates/`
  CSV template headers for each report.
- `outputs/`
  Generated CSVs are written here.

## Current query coverage

- Implemented from `iot_portal_tb_request_log`:
  - Domestic SMS / voice / data summary
  - Premium and special numbers
- Left as TODO placeholders:
  - Active subscribers
  - Domestic A2P SMS
  - International voice / SMS / data country breakdown

The placeholder queries already return the correct column structure, so you can replace only the SQL body later without changing the pipeline wiring.

## Run

```powershell
python split_queries.py
python generate_report.py
```

## Config notes

- Set `variables.start_date` and `variables.end_date` in `config.yml`.
- `end_date` is inclusive in config.
- The runner derives `end_date_exclusive` automatically.
- All report outputs are defined in `report_generation.reports`.
