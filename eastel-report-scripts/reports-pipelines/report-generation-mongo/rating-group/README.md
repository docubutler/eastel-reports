# Rating Group Mongo Report

This folder generates a CSV report directly from Mongo aggregation output for the rating-group summary.

## Files

- `generate_report.py`
  Runs the Mongo aggregation query and writes the CSV file.
- `queries/1.yml`
  Mongo aggregation version of the PostgreSQL rating-group query.
- `report-template.csv`
  Header-only template for direct export.
- `config.yml`
  Active runtime config.
- `config-sample.yml`
  Example config with comments.

## Template Format

Use a header-only CSV when you want the query result written exactly as returned:

```csv
report_start_date,report_end_date,count,sum,rating_group
```

How it works:

- In `raw_rows` mode, the script treats the template header row as the output column list.
- Each Mongo result document becomes one CSV row.
- With the current template, the output matches the query fields exactly.

## Renaming Columns Later

If you later want different CSV headers, keep the query the same and set `report_generation.output_columns` in `config.yml`:

```yaml
output_columns:
  - source: "report_start_date"
    header: "Report Start Date"
  - source: "report_end_date"
    header: "Report End Date"
  - source: "count"
    header: "Transaction Count"
  - source: "sum"
    header: "Total Used Volume"
  - source: "rating_group"
    header: "Rating Group"
```

## Mongo Query

The PostgreSQL query:

```sql
select '2026-04-01' as report_start_date,
       '2026-04-30' as report_end_date,
       count(*),
       sum(update_used_volume),
       rating_group
from iot_portal_tb_request_log t
where t.req_time >= '2026-04-01'
  and t.req_time < '2026-05-01'
group by rating_group;
```

is implemented in Mongo as:

- `$match` on `req_time` from `start_date` inclusive to `end_date_exclusive` exclusive
- `$group` by `rating_group`
- `$sum: 1` for `count`
- `$sum: "$update_used_volume"` for `sum`
- `$project` to add `report_start_date` and `report_end_date`
- `$sort` by `rating_group`

## Config

Set these values in `config.yml`:

- `mongo.uri`
- `mongo.database`
- `collections.request_log`
- `variables.start_date`
- `variables.end_date`
- `report_generation.output_csv`

For this repo, PostgreSQL table `iot_portal_tb_request_log` is synced into Mongo collection `request_logs`, so `collections.request_log` should normally be `request_logs`.

`end_date` is inclusive. The script automatically computes `end_date_exclusive = end_date + 1 day`.

For large date ranges, these config options are available:

- `allow_disk_use: true`
- `hint: "ix_req_time"`
- `max_time_ms: 0`

`hint: "ix_req_time"` is useful here because the April 2026 window is large.

## Run

Install dependencies:

```powershell
pip install PyYAML pymongo
```

Run:

```powershell
python generate_report.py
```

Or with an explicit config:

```powershell
python generate_report.py --config config.yml
```

The output file path is taken from `report_generation.output_csv`.
