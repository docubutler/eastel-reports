# Report Generation Scripts

This folder now contains two Python scripts:

- `split_queries.py`
  Splits [quries.sql](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/quries.sql) into numbered files such as `1.sql`, `2.sql`, `3.sql` inside the folder configured in `config.yml`.
- `generate_report.py`
  Reads those numbered SQL files, replaces SQL variables from `config.yml`, executes them on PostgreSQL, and writes a new report CSV from [report-template.csv](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/report-template.csv) without modifying the template.

## Files

- [config.yml](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/config.yml)
- [quries.sql](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/quries.sql)
- [report-template.csv](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/report-template.csv)
- [split_queries.py](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/split_queries.py)
- [generate_report.py](D:/DB_repos/eastel-reports/eastel-report-scripts/report-generation-script/generate_report.py)

## Config

`config.yml` has three sections relevant to this flow:

```yaml
postgres:
  dsn: ""
  host: "localhost"
  port: 5432
  database: "anchor_iot"
  user: "postgres"
  password: "postgres"
  sslmode: "disable"

report_generation:
  source_queries_file: "quries.sql"
  split_queries_dir: "generated-queries"
  template_csv: "report-template.csv"
  output_csv: "report-output.csv"
  query_column_name: "Query"

variables:
  start_date: "2026-05-11"
  end_date: "2026-05-12"
```

### What each key does

- `report_generation.source_queries_file`
  Source SQL file containing all numbered queries.
- `report_generation.split_queries_dir`
  Output folder for `1.sql`, `2.sql`, `3.sql`, and so on.
- `report_generation.template_csv`
  Input template CSV. This file is never modified.
- `report_generation.output_csv`
  Final CSV written by the report runner.
- `report_generation.query_column_name`
  Column where the executed SQL text is written in the final report.
- `variables`
  Global SQL variables injected into the split queries at runtime.

## Step 1: Split the source SQL

Run:

```powershell
python split_queries.py
```

What it does:

- Reads `quries.sql`
- Detects numbered sections like `1.`, `2.`, `3.`
- Creates numbered files in `report_generation.split_queries_dir`
- Replaces hardcoded `t.req_time` date literals with:
  - `{{start_date}}`
  - `{{end_date}}`

Example generated SQL:

```sql
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction
FROM iot_portal_tb_request_log t
WHERE
    t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date}}';
```

## Step 2: Generate the report

Run:

```powershell
python generate_report.py
```

What it does:

- Reads database settings from `postgres`
- Reads SQL variable values from `variables`
- Reads all `*.sql` files from `report_generation.split_queries_dir`
- Replaces placeholders like `{{start_date}}` and `{{end_date}}`
- Executes each query against PostgreSQL
- Reads the template CSV row by row
- Replaces template placeholders such as `%1.total_transaction%`
- Writes a new file to `report_generation.output_csv`
- Writes the final executed SQL into the `Query` column

## Template placeholder format

The runner understands placeholders in this form:

```text
%query_number.column_name%
```

Examples:

- `%1.total_transaction%`
- `%1.mou_minutes%`
- `%5.mou_MBs%`

Notes:

- Column lookup is case-insensitive, so `%5.mou_MBs%` matches SQL alias `mou_mbs`.
- If a query returns multiple rows, numeric columns are summed before substitution.
  This is useful for grouped queries like international voice or SMS summaries.
- If a placeholder refers to a missing value, the output cell is left blank.

## Expected flow

1. Update `variables.start_date` and `variables.end_date` in `config.yml`
2. Run `python split_queries.py`
3. Run `python generate_report.py`
4. Open the generated CSV from `report_generation.output_csv`

## Dependencies

These scripts require:

- `python`
- `PyYAML`
- `psycopg`

If they are not installed already:

```powershell
pip install PyYAML psycopg[binary]
```
