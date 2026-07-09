# Mongo Report Generation Handover

This folder contains MongoDB-based report extraction scripts for Eastel reporting.

The Mongo collections used by these reports are designed to mirror the PostgreSQL
source tables closely, so the report logic maps directly from the original
PostgreSQL versions. Collection structure references are available under:

- `mongo-collections/request_logs.json`
- `mongo-collections/usage_logs.json`
- `mongo-collections/smsc_cdrs.json`

## Report Types

There are three main report groups in this folder.

### 1. `1A-Monthly-Summary`

Purpose:
- produce a monthly summary of total usage by usage type
- output is a CSV populated from placeholders in a template

Entry point:
- `1A-Monthly-Summary/generate_report.py`

Primary guide:
- `1A-Monthly-Summary/README.md`

### 2. `2-Invoice-Recon`

Purpose:
- produce the invoice reconciliation workbook used with UMobile
- output is an Excel workbook populated from Mongo aggregation query results

Entry point:
- `2-Invoice-Recon/generate_report.py`

Primary guide:
- `2-Invoice-Recon/README.md`

Useful helper:
- `2-Invoice-Recon/misc_scripts/run_query.py`
  This can be used to run a single configured query for testing/debugging.

### 3. `3-OneDay-CDR-Details`

Purpose:
- export complete daily CDR detail rows
- can be used either for a whole day or for a single `msisdn`

Entry point:
- `3-OneDay-CDR-Details/generate_report.py`

Primary guide:
- `3-OneDay-CDR-Details/README.md`

## Common Requirements

Recommended environment:

- Windows with PowerShell
- Python 3.11+ or another modern Python 3 version already used by the team
- network access to the MongoDB cluster

Python packages used by these scripts:

```powershell
pip install PyYAML pymongo openpyxl
```

Notes:

- `openpyxl` is required for Excel-based reports such as `2-Invoice-Recon`
- CSV-based reports may not use `openpyxl` directly, but installing it once is simplest for operators

## Common Configuration Pattern

Each report folder has its own `config.yml` and `config-sample.yml`.

At a high level, the NOC team usually only needs to review:

- `mongo`
  connection string and database name
- `collections`
  mapping of logical names such as `request_log`, `usage_log`, `smsc_cdr`
- `variables`
  reporting date range and any optional runtime filters
- `report_generation`
  input template path and output file path

Always refer to the README inside the specific report folder before changing any
config field, because date semantics differ slightly between reports.

## Quick Run Summary

From repo root:

```powershell
py reports-pipelines/report-generation-mongo/1A-Monthly-Summary/generate_report.py
py reports-pipelines/report-generation-mongo/2-Invoice-Recon/generate_report.py
py reports-pipelines/report-generation-mongo/3-OneDay-CDR-Details/generate_report.py
```

Or run from inside the target report folder with:

```powershell
py .\generate_report.py
```

## Operator Guidance

- Use the report-specific README first.
- Use `config-sample.yml` as the baseline if a fresh `config.yml` is needed.
- For `2-Invoice-Recon`, use `run_query.py` when validating one query without running the whole workbook.
- Do not assume date handling is identical across folders; check the README in the report you are running.
