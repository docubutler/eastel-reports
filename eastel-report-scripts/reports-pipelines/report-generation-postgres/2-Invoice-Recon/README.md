# PostgreSQL Invoice Recon Excel Pipeline

This pipeline generates the Invoice Recon workbook from PostgreSQL CDR tables while keeping the same Excel-template output style as the Mongo Invoice-Recon pipeline.

The runner reads an Excel template, finds scalar placeholders such as `%Q004.onnet_mou%`, finds table anchors such as `%TABLE:Q014%`, executes the configured query files, and writes the completed workbook.

## Why Mongo Is Still Required

This is a PostgreSQL report runner, but SMSC/A2P SMS records are still read from Mongo.

- **A2P SMS / SMSC records**: Query `Q015` is executed directly against the Mongo `smsc_cdrs` collection.
- **Country code mapping**: the runner reads PostgreSQL `iot_portal_tb_country` into a temporary PostgreSQL table named `temp_country_code` for the current session.
- **Roaming destination mapping**: the runner reads PostgreSQL `iot_portal_tb_roaming_destination` into a temporary PostgreSQL table named `temp_roaming_destination` for the current session.

Those temporary tables are created only for the active report run. They are not persistent database objects and do not require schema changes.

## Query Folders

The selected query folder controls whether the report is extracted from usage logs or request logs:

```yaml
report_generation:
  queries_dir: "usage-queries"
```

Use:

- `usage-queries` for `public.iot_portal_tb_usage_log`
- `request-queries` for `public.iot_portal_tb_request_log`

Both folders contain the same query IDs and workbook output shapes. The differences are the source table and column names:

| Concept | Usage logs | Request logs |
| --- | --- | --- |
| Time column | `usage_start_time` | `req_time` |
| Actual usage column | `act_usage_unit` | `act_update_used_volume` |
| Table variable | `{{usage_log_table}}` | `{{request_log_table}}` |

Every query file starts with a concrete July 2026 copy-paste sample query. The runnable query below that sample uses placeholders from `config.yml`.

## Files

- `generate_report.py`: entrypoint.
- `report_engine/`: Excel rendering, config loading, PostgreSQL execution, and Mongo helper execution.
- `usage-queries/`: one query file per workbook query, sourced from usage logs.
- `request-queries/`: one query file per workbook query, sourced from request logs.
- `recon-report-samples/`: sample CSV outputs for the recon sections. These are reference files for expected report shape and values, not runtime inputs.
- `templates/`: CSV templates for the individual recon tables/sections. These document the column layout used by the report sections.
- `2. CDR-Reconcialation-Report_template.xlsx`: workbook template copied into this folder.
- `config.yml`: local runtime config.
- `config-sample.yml`: sample config for new environments.
- `queries.sql`: combined/reference SQL used for review or copy-paste validation. Runtime execution uses the query files in the selected query folder.
- `requirements.txt`: Python dependencies.

`split_queries.py` is intentionally removed. Query files are now maintained directly in the selected query folder.

## Reference Folders

### `recon-report-samples/`

This folder contains example CSV files for the major Invoice Recon sections:

- `recon-report-active-subs_sample.csv`: active subscriber count sample.
- `recon-report-domestic-sms-voice-and-data_sample.csv`: domestic SMS, voice, 4G data, and 5G data sample.
- `recon-report-internation-voice-and-sms_sample.csv`: international SMS and voice sample.
- `recon-report-domestic-a2p-sms_sample.csv`: domestic A2P SMS sample.
- `recon-report-permium-and-speical-numbers_sample.csv`: premium and special numbers sample.

Use these files to compare the generated workbook layout and section totals. The runner does not read these files while generating the report.

### `templates/`

This folder contains CSV table templates that describe the expected columns for each report section:

- `recon-report-active-subs-template.csv`
- `recon-report-domestic-sms-voice-and-data-template.csv`
- `recon-report-international-voice-and-sms-template.csv`
- `recon-report-domestic-a2p-sms-template.csv`
- `recon-report-premium-and-special-numbers-template.csv`

These templates are documentation/reference assets. The Excel workbook template remains the source used by the runner.

### Query Folders And Table Sources

The selected query folder decides which PostgreSQL CDR table is used:

| Config value | PostgreSQL table | When to use |
| --- | --- | --- |
| `usage-queries` | `public.iot_portal_tb_usage_log` | Use this when invoice recon should be based on usage-log CDRs. |
| `request-queries` | `public.iot_portal_tb_request_log` | Use this when invoice recon should be based on request-log CDRs. |

The table names are configured in `config.yml`:

```yaml
tables:
  usage_log_table: "public.iot_portal_tb_usage_log"
  request_log_table: "public.iot_portal_tb_request_log"
  country_table: "public.iot_portal_tb_country"
  roaming_destination_table: "public.iot_portal_tb_roaming_destination"
```

The Mongo collection used for A2P SMS/SMSC input is also configured in `config.yml`:

```yaml
collections:
  smsc_cdr: "smsc_cdrs"
```

## Query IDs

The folder includes Mongo-style workbook query IDs:

- `Q001`: Active subscribers.
- `Q002`: Domestic MO SMS total.
- `Q004`: Domestic MO voice on-net/off-net MOU.
- `Q006`: Domestic 4G data usage.
- `Q007`: Domestic 5G data usage.
- `Q011`: International SMS by destination country.
- `Q012`: International voice by destination country.
- `Q013`: International data placeholder. The current CDR schema has no defensible destination-country field for data records.
- `Q014`: Premium and special numbers.
- `Q015`: Domestic A2P SMS from Mongo `smsc_cdrs`.
- `roam-data`: Roaming data by roaming destination.
- `roam-sms`: Roaming SMS by roaming destination.
- `roam-voice`: Roaming voice by roaming destination.

## Running

Install dependencies:

```powershell
pip install -r requirements.txt
```

Prepare `config.yml`:

```yaml
postgres:
  host: "localhost"
  port: 5432
  database: "anchor_iot"
  user: "postgres"
  password: "postgres"
  sslmode: "disable"

mongo:
  uri: "mongodb+srv://..."
  database: "eastel-data"

report_generation:
  queries_dir: "usage-queries"
```

Run:

```powershell
python generate_report.py --config config.yml
```

Switch to request logs by changing only:

```yaml
report_generation:
  queries_dir: "request-queries"
```

The generated workbook path is controlled by:

```yaml
report_generation:
  output_xlsx: "2-Invoice-Recon-postgres-report-July.xlsx"
```

If the output workbook already exists and no placeholders remain, delete it or change `output_xlsx` before running again.

## Date Window

To generate the invoice recon for a particular month, update only the month window in `config.yml`.

The config uses an exclusive end date. For July 2026, set `start_date` to the first day of July and `end_date` to the first day of August:

```yaml
variables:
  start_date: "2026-07-01 00:00:00"
  end_date: "2026-08-01 00:00:00"
```

This matches the SQL pattern:

```sql
WHERE event_time >= '2026-07-01 00:00:00'
  AND event_time <  '2026-08-01 00:00:00'
```

For August 2026, update only these values:

```yaml
variables:
  start_date: "2026-08-01 00:00:00"
  end_date: "2026-09-01 00:00:00"
```

In normal use, you do not need to edit SQL files for a new month. Update `variables.start_date` and `variables.end_date` in `config.yml`, then run:

```powershell
python generate_report.py --config config.yml
```

## Notes

- MOU and MB values follow the Mongo report semantics and use actual usage fields.
- Premium/special numbers include all opposite-number rules from the Mongo query, including `6015555`, `6015999`, `6013504`, `6015511`, `6015800`, and `6015995`.
- `Q015.js` files are documentation/rendered-query references for the actual-queries workbook. Execution is handled by the Python `mongo_a2p_sms` engine using PyMongo.
- The runner leaves failed query placeholders unchanged and continues, matching the Mongo workbook runner behavior.
