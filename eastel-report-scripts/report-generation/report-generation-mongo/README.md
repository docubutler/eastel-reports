# Mongo Report Generation Scripts

This folder is the MongoDB-based migration of the PostgreSQL report-generation flow.
It keeps the same CSV placeholder model, but query execution now runs through Mongo aggregation pipelines.

## Files

- `config.yml`
  Main runtime configuration for Mongo connection, paths, collections, and date variables.
- `queries/`
  Source query directory that contains one YAML file per query such as `1.yml`, `2.yml`, etc.
- `generate_report.py`
  Executes the query files on MongoDB and writes the populated report CSV.
- `report-template.csv`
  Input template used to produce the final report.

## Query Format

Each query lives in its own YAML file inside `queries/`.

Example `queries/1.yml`:

```yaml
query_id: 1
title: Voice (Mobile Origination) - On Net
collection: "{{request_log}}"
pipeline:
  - $match:
      req_time:
        $gte:
          $dateVar: start_date
        $lt:
          $dateVar: end_date_exclusive
```

## Config

`config.yml` has four main sections:

```yaml
mongo:
  uri: ""
  database: "eastel-data"

report_generation:
  queries_dir: "queries"
  template_csv: "report-template.csv"
  output_csv: "report-output.csv"
  query_column_name: "Query"
  default_collection: "request_logs"

collections:
  request_log: "request_logs"

variables:
  start_date: "2026-05-11"
  end_date: "2026-05-11"
```

### Important date behavior

- `start_date` is inclusive.
- `end_date` is also inclusive.
- You should set `end_date` to the real last day you want in the report.
- The script automatically computes `end_date_exclusive = end_date + 1 day` internally for Mongo range filters.
- Do not manually enter `end_date + 1` in config.

## Collections

Collection names are kept in the `collections` section so query definitions can reference them as variables:

```yaml
collection: "{{request_log}}"
```

This is cleaner than mixing collection names into normal runtime variables, and it scales better if future reports need multiple collections.

## CSV Template Format

The report template uses placeholders in this form:

```text
%query_number.column_name%
```

Examples:

- `%1.total_transaction%`
- `%1.mou_minutes%`
- `%5.mou_MBs%`

Notes:

- Column matching is case-insensitive.
- If a query returns multiple rows, numeric values are summed before substitution.
- Text values from multiple rows are de-duplicated and joined.
- Missing values become blank cells.
- The configured `Query` column is filled with the rendered collection name and aggregation pipeline used for that row.

## How It Runs

### 1. Split the source query file

### Generate the report

```powershell
python generate_report.py
```

What it does:

- Reads the CSV template first and identifies which query ids are actually referenced
- Loads Mongo config and report variables
- Resolves named collections
- Converts `start_date` and inclusive `end_date` into Mongo-ready date filters
- Reads the required YAML query files from `queries/`
- Executes only the referenced query files in order
- Reads `report-template.csv`
- Replaces placeholders like `%1.total_transaction%`
- Writes the final CSV to `report_generation.output_csv`

## Runtime Logs

`generate_report.py` logs clear progress to the console, including:

- Script start time
- Config and file paths in use
- Date window being executed
- Query ids referenced by the CSV template
- Total number of queries that will actually be executed
- Which query is currently executing
- Query id, title, collection, and number of pipeline stages
- Rows returned per query
- Execution time per query
- Final CSV output path
- Script end time and total duration

This makes it easier to see whether the process is moving, which query is slow, and where it failed if something breaks.

## What To Expect

- `generate_report.py` does not modify `report-template.csv`.
- Only queries referenced by placeholders in the CSV template are executed.
- The output CSV is created fresh at the configured output path.
- If Mongo connection settings are missing, the runner fails early with a clear error.
- If a query file is invalid, the process fails with the query number/file context.

## Dependencies

Install:

```powershell
pip install PyYAML pymongo
```

## Typical Flow

1. Set `mongo.uri` and `mongo.database` in `config.yml`, or provide `MONGO_URI` and `MONGO_DB`.
2. Set `collections.request_log` to the correct Mongo collection.
3. Set `variables.start_date` and `variables.end_date`.
4. Update the files inside `queries/` if report logic changes.
5. Run `python generate_report.py`.
