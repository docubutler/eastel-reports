# 2-Invoice-Recon Report Engine

This folder contains a MongoDB-driven Excel report generator for the `2-Invoice-Recon` report.

The engine reads `config.yml`, renders query files by substituting config values, executes the queries against MongoDB, and writes results into an Excel workbook based on placeholders already present in the template.

## Folder Layout

```text
2-Invoice-Recon/
  config.yml
  queries/
    1.js
    2.js
    ...
  report_engine/
    config_loader.py
    daily_execution.py
    excel_processor.py
    main.py
    query_executor.py
    query_renderer.py
    run_query.py
    validators.py
```

## Main Files

- `config.yml`: runtime configuration, paths, variables, query mapping, logging, and day-wise options.
- `queries/*.js`: Mongo aggregation scripts containing placeholders such as `{{start_date}}` and `{{request_log}}`.
- `report_engine/main.py`: main report-generation entry point.
- `report_engine/run_query.py`: standalone runner for a single configured query file.
- `report_engine/daily_execution.py`: day-wise slicing, checkpoint persistence, and aggregation logic.

## Configuration

The engine is driven by `config.yml`.

Important sections:

- `mongo`
  - `uri`: MongoDB connection string.
  - `database`: database name used by `mongosh`.
- `report_generation`
  - `queries_dir`: directory containing source `.js` query files.
  - `template_xlsx`: Excel template used as the starting point.
  - `output_xlsx`: report workbook that is progressively updated and saved.
  - `actual_quries_used_output_file`: workbook containing the final rendered queries used.
  - `daily_checkpoint_output_file`: workbook containing saved day-wise query checkpoints.
  - `default_collection`: optional fallback collection placeholder.
- `collections`
  - named collection placeholders used in query files, for example `{{request_log}}`.
- `variables`
  - runtime values used in query files, for example `{{start_date}}` and `{{end_date}}`.
- `queries`
  - query registry keyed by query id such as `Q013` or `intl.-sms`.

## Date Semantics

Current behavior:

- `start_date` is inclusive.
- `end_date` is exclusive.

Queries are written and rendered using:

```text
>= start_date
< end_date
```

Example:

- `start_date = 2026-04-01T00:00:00Z`
- `end_date = 2026-04-03T00:00:00Z`

This includes April 1 and April 2, and excludes April 3.

The day-wise execution mode follows the same exclusive `end_date` behavior.

## Query Configuration

Each query entry can contain:

```yaml
intl.-sms:
  file: queries/intl.-sms.js
  output: fixed_table
  anchor: "%TABLE:intl.-sms%"
  columns:
    - service_type
    - charge_type
    - country
    - sms_count
  execute_day_wise: false
```

Supported keys:

- `file`: query file path.
- `output`: `scalar` or `fixed_table`.
- `anchor`: required for table outputs referenced by `%TABLE:<query_id>%`.
- `columns`: required for `fixed_table`; defines write order.
- `execute_day_wise`: optional boolean; if `true`, the query is executed one day at a time and aggregated.

## Query Placeholder Substitution

Before a query runs, the engine builds a replacement map from:

- `collections`
- `variables`
- `report_generation.default_collection` as `{{default_collection}}` if configured

Then it substitutes placeholders inside the query text:

```javascript
db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      }
    }
  }
]);
```

becomes:

```javascript
db.request_logs.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("2026-04-01T00:00:00Z"),
        $lt: ISODate("2026-04-03T00:00:00Z")
      }
    }
  }
]);
```

If a placeholder in the query file is missing from config, the engine raises a clear error.

## Excel Placeholder Types

### Scalar placeholders

Format:

```text
%Q001.total%
%Q004.mou%
%Q006.mou_mbs%
%intl.-voice.mou_mins%
```

Behavior:

1. Execute query `Qxxx` once.
2. Cache the result in memory during the current run.
3. Read the requested field from the scalar result.
4. Replace the placeholder in the workbook.
5. Save the workbook immediately.

Scalar placeholders support both legacy ids like `Q001` and descriptive ids
such as `intl.-voice`, as long as the query id exists in `config.yml`.

If a scalar field is missing, that query is logged as failed and the placeholder remains unchanged.

### Table placeholders

Format:

```text
%TABLE:Q011%
%TABLE:intl.-sms%
%TABLE:roam-data%
```

Behavior:

1. Find the anchor row in the workbook.
2. Determine the configured column order from `config.yml`.
3. Insert result rows at the anchor position.
4. Delete the original anchor row.
5. Save the workbook immediately.

The template headers are expected to exist already. If a header row is missing at the anchor area, the engine creates one using bold white text on a blue background.

## Output Workbook as Checkpoint State

The output workbook is the source of truth for report progress.

Algorithm:

1. Load `config.yml`.
2. Validate config and query files.
3. Check whether `output_xlsx` exists.
4. If it does not exist, copy `template_xlsx` to `output_xlsx`.
5. Scan `output_xlsx` for remaining scalar placeholders and table anchors.
6. If no placeholders remain, stop with:
   `Output workbook does not contain any placeholders. Delete the output file if you want to generate a new file.`
7. Process queries in workbook reference order.
8. After each query completes, write its result into `output_xlsx` and save immediately.
9. Continue to the next query even if one query fails.

This means partial progress is preserved directly in the report workbook.

## Day-Wise Execution

If `execute_day_wise: true` is set for a query, the engine does not execute the full date range in one shot.

Instead it:

1. Reads `variables.start_date` and `variables.end_date`.
2. Splits the range into one-day windows using inclusive start and exclusive end boundaries.
3. For each day, overrides only that day’s `start_date` and `end_date` in the query renderer.
4. Executes the query for that day.
5. Saves the day result into the daily checkpoint workbook.
6. Aggregates all saved day results into one final query result.
7. Writes that final aggregated result into the output workbook.

Example with:

- `start_date = 2026-04-01T00:00:00Z`
- `end_date = 2026-04-03T00:00:00Z`

Day slices become:

- `2026-04-01T00:00:00Z` to `2026-04-02T00:00:00Z`
- `2026-04-02T00:00:00Z` to `2026-04-03T00:00:00Z`

## Daily Checkpoint Workbook

The day-wise mode persists progress to:

- `report_generation.daily_checkpoint_output_file`

This workbook contains one sheet per query id, for example `Q013` or `intl.-sms`.

Each query sheet stores:

- `Date`
- `Status`
- `DurationSeconds`
- `PayloadJSON`
- `RenderedQuery`
- `ErrorMessage`
- `UpdatedAtUTC`

Behavior:

- successful day results are reused on rerun
- failed days are logged and can be retried later
- completed days are not recalculated if already saved successfully

## Day-Wise Aggregation Logic

### Scalar results

Scalar day results are aggregated by summing numeric fields and keeping non-numeric descriptive fields.

Example:

```json
{"service_type":"SMS","total":100}
{"service_type":"SMS","total":150}
```

becomes:

```json
{"service_type":"SMS","total":250}
```

### Table results

Table day results are aggregated using the configured `columns`.

Current generic rule:

- numeric columns are treated as measures to sum
- non-numeric columns are treated as grouping keys

Example for `Q013`:

- `service_type`
- `charge_type`
- `country`
- `usage_mbs`

Grouping key:

- `service_type + charge_type + country`

Summed measure:

- `usage_mbs`

So if `Vietnam` appears on multiple days, those rows are merged and `usage_mbs` is added.

Important limitation:

- if a numeric field is actually intended to be a grouping key, the current generic logic is not sufficient
- in that case, explicit config such as `group_by` and `sum_columns` would be a better future enhancement

## Query Execution

Queries are executed through `mongosh`.

Current execution flow:

1. Render the final query text.
2. Build a temporary JavaScript file that selects the configured database.
3. Run it using `mongosh --quiet --file`.
4. Convert the cursor to an array if needed.
5. Print JSON using `EJSON.stringify(...)`.
6. Parse the output back into Python.

Supported result shapes:

- scalar result:

```json
{"total": 100}
```

- table result:

```json
[
  {"country": "Vietnam", "usage_mbs": 100},
  {"country": "Thailand", "usage_mbs": 200}
]
```

## Query Caching

Within a single report run, each query id is executed only once and cached in memory.

Example:

```text
%Q001.total%
%Q001.some_other_field%
```

Only one query execution occurs for `Q001`.

For day-wise queries, daily results are additionally cached across runs in the daily checkpoint workbook.

## Query Id Format

The report engine supports two query id styles:

- legacy ids such as `Q001`, `Q013`, `Q015`
- descriptive ids such as `intl.-sms`, `intl.-voice`, `roam-data`, `roam-sms`, `roam-voice`, `premium-and-special-numbers`

These ids are used consistently across:

- the `queries:` section in `config.yml`
- scalar placeholders such as `%Q001.total%`
- table anchors such as `%TABLE:intl.-sms%`
- daily checkpoint sheet names
- the rendered queries workbook

## Validation

Before report generation, the engine validates:

- `mongo.uri` exists
- `mongo.database` exists
- `queries_dir` exists
- `template_xlsx` exists
- every configured query file exists
- every query output type is supported
- every `fixed_table` query has `columns`
- every workbook placeholder query id exists in config
- scalar placeholders point to `scalar` queries
- table anchors point to `fixed_table` queries
- day-wise queries have valid `variables.start_date` and `variables.end_date`

## Error Handling

The report engine is designed not to abort the full run because of one bad query.

Behavior:

- if a query fails, the error is logged
- the related placeholders remain unchanged in the output workbook
- the engine continues with the next query
- day-wise failures are also written into the daily checkpoint workbook

## Rendered Queries Workbook

The engine also writes a second workbook:

- `actual_quries_used_output_file`

Sheet name:

- `Query Definitions`

Columns:

- `Query ID`
- `Query File`
- `Rendered Query`

For day-wise queries, the workbook stores one rendered query entry per day slice.

## Running the Report

Install dependencies first:

```powershell
pip install PyYAML pymongo openpyxl
```

Recommended operator entry point:

```powershell
py .\generate_report.py
```

That wrapper calls the underlying report engine and is the simplest command for day-to-day use.

Equivalent direct engine entry point:

From the `2-Invoice-Recon` folder:

```powershell
py .\report_engine\main.py
```

Or from the repo root:

```powershell
py reports-pipelines/report-generation-mongo/2-Invoice-Recon/report_engine/main.py
```

## Running a Single Query

For query-level testing without generating the full workbook:

To render and execute one configured query file:

```powershell
py .\report_engine\run_query.py .\queries\13.js
```

To also print the rendered query:

```powershell
py .\report_engine\run_query.py .\queries\13.js --show-rendered-query
```

You can also pass a repo-root relative path:

```powershell
py reports-pipelines/report-generation-mongo/2-Invoice-Recon/report_engine/run_query.py reports-pipelines/report-generation-mongo/2-Invoice-Recon/queries/13.js
```

## Current Design Summary

- The template is copied once to create the output workbook.
- The output workbook is incrementally updated and saved after each query.
- Scalar placeholders and table anchors inside the workbook fully drive which queries are executed.
- Query files are rendered only from `config.yml` values.
- Day-wise execution is optional per query.
- Day-wise results are resumable through a separate checkpoint workbook.
- `end_date` is currently exclusive.
