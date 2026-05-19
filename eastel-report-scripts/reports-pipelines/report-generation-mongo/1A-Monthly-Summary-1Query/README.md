# Mongo Monthly Summary - Consolidated

This folder is an isolated variant of `1A-Monthly-Summary` that reduces report execution to two Mongo queries:

- `queries/1.yml`
  Consolidates the `request_logs` metrics that were previously spread across query ids `1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14`.
- `queries/2.yml`
  Consolidates the `smsc_cdrs` metrics that were previously spread across query ids `15, 16`.

## Why

The original Mongo migration executes many month-wide scans on `request_logs`. This version keeps the same CSV placeholder model but maps multiple CSV rows to the same merged query result row.

## Template Mapping

The report template still uses placeholders, but many rows now point to query `1`:

- Row 1 uses `%1.q1_total_transaction%`, `%1.q1_mou_minutes%`
- Row 6 uses `%1.q6_total_transaction%`, `%1.q6_mou_mbs%`
- Row 14 uses `%1.q14_total_transaction%`, `%1.q14_mou_minutes%`

Rows 15 and 16 point to query `2`:

- `%2.q15_total_transaction%`
- `%2.q16_total_transaction%`

## Files

- `generate_report.py`
  Thin wrapper around the existing report runner, using this folder's `config.yml`.
- `report-template.csv`
  Placeholder template remapped to the merged query field names.
- `queries/1.yml`
  Consolidated `request_logs` aggregation.
- `queries/2.yml`
  Consolidated `smsc_cdrs` aggregation.

## Run

```powershell
python .\generate_report.py
```

Output is written to the `report_generation.output_csv` path in `config.yml`.
