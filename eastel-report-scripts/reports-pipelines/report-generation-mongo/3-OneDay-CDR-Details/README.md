# 3-OneDay-CDR-Details

This folder generates a non-summarized CSV report of categorized CDR detail rows from MongoDB.

It is intentionally different from the placeholder-summary model used in `1A-Monthly-Summary`.

## What It Does

- Reads a date range from `config.yml` or CLI arguments
- Optionally filters to one `msisdn_a`
- Extracts matching detail rows from:
  - `usage_logs` for categories `1` to `12`
  - `smsc_cdrs` for categories `13` and `14`
- Categorizes each matched document
- Writes one CSV row per matched document

This report is not aggregated. Each Mongo document that matches a category produces one output row.
An optional config flag can exclude `usage_logs` rows where the duration/volume column is exactly zero, and that filter is applied in the Mongo query itself.

## Source Files In This Folder

- `3-OneDay-CDR-Details.csv`
  Original report shape/spec provided by the user. It is used as a format reference only.
- `3-OneDay-CDR-Details-Mapping.csv`
  Category mapping reference that maps report categories to the existing monthly summary rows.
- `config.yml`
  Active runtime configuration.
- `config-sample.yml`
  Example configuration.
- `generate_report.py`
  MongoDB report generator.

## Output CSV

The generated CSV omits the `Comments` column and adds verification columns:

- `S.No.`
- `Category No.`
- `Service Type`
- `Event/Call Start Date Time`
- `Call Duration (second) / Total Volume (UL +DL ) in bytes`
- `MSISDN A#`
- `MSISDN B#`
- `IMSI`
- `Source Collection`
- `Source Record ID`
- `Mongo Record ID`

### Notes

- `S.No.` is a running serial number for the output file.
- `Category No.` is the report category from the spec file.
- `Source Collection` is either `usage_logs` or `smsc_cdrs`.
- `Source Record ID` is:
  - `usage_log_id` for `usage_logs`
  - `message_id` for `smsc_cdrs`
- `Mongo Record ID` is the Mongo `_id` converted to text so the original document can be verified later.
- `Call Duration (second) / Total Volume (UL +DL ) in bytes` is populated as:
  - `act_usage_unit` for `usage_logs`
  - blank for `smsc_cdrs`
  - if `report_generation.exclude_zero_usage_rows` is enabled, `usage_logs` rows with zero in this column are filtered out by the Mongo query

### Meaning of `Call Duration (second) / Total Volume (UL +DL ) in bytes`

This column is intentionally populated from the raw detail record, not from a derived summary:

- For voice records in `usage_logs`, `act_usage_unit` represents the actual call duration in seconds.
- For data records in `usage_logs`, `act_usage_unit` represents the actual used volume in bytes.
- For SMS records in `usage_logs`, `act_usage_unit` is the raw usage unit recorded for that SMS event.
- For A2P rows from `smsc_cdrs`, there is no equivalent duration/volume field in the current report design, so the value is left blank.

## Input Parameters

Supported runtime parameters:

- `start_date`
- `end_date`
- optional `msisdn_a`
- optional `report_generation.exclude_zero_usage_rows`

Behavior:

1. If only `start_date` and `end_date` are provided:
   all matching rows in the date range are exported.
2. If `start_date`, `end_date`, and `msisdn_a` are provided:
   only matching rows for that `msisdn_a` are exported.
3. If `report_generation.exclude_zero_usage_rows = true`:
   `usage_logs` rows with `act_usage_unit = 0` are excluded in the `usage_logs` Mongo query before results are returned.

## Date Filtering

- `start_date` is inclusive
- `end_date` is inclusive
- the script computes `end_date_exclusive = end_date + 1 day`

For `usage_logs`, the date field is:

- `usage_start_time`

For `smsc_cdrs`, the date field is:

- `delivery_date`

## Field Mapping

### usage_logs categories

Rows `1` to `12` come from `usage_logs`.

Shared output mapping:

- `Event/Call Start Date Time` -> `usage_start_time`
- `Call Duration (second) / Total Volume (UL +DL ) in bytes` -> `act_usage_unit`
- `MSISDN A#` -> `msisdn`
- `MSISDN B#` -> `opposite_number`
- `IMSI` -> `imsi`
- `Source Record ID` -> `usage_log_id`

Category logic:

1. `Domestic Data 4G`
   - `rat_type = '4G'`
   - `roaming_destination_id = 87`
   - `rating_group != '500003'`
2. `Domestic Data 5G`
   - `rat_type = '5G'`
   - `roaming_destination_id = 87`
   - `rating_group != '500003'`
3. `Domestic MO SMS (Offnet / Onnet)`
   - mapped from monthly row `3`
   - `rat_type = 'SM'`
   - `roaming_destination_id = 87`
   - no on-net/off-net split is attempted
4. `Domestic MO Voice (Onnet)`
   - mapped from monthly row `1`
   - `rat_type = 'VO'`
   - `service_type_sub_cd = 'MO'`
   - `rating_group = 'ONNET'`
   - `roaming_destination_id = 87`
   - `LENGTH(opposite_number) > 10`
5. `Domestic MO Voice (Offnet)`
   - mapped from monthly row `2`
   - `rat_type = 'VO'`
   - `service_type_sub_cd = 'MO'`
   - `rating_group = 'OFFNET'`
   - `roaming_destination_id = 87`
   - `LENGTH(opposite_number) > 10`
   - `opposite_number LIKE '60%'`
6. `Domestic IDD MO Voice`
   - mapped from monthly row `7`
   - `rat_type = 'VO'`
   - `service_type_sub_cd = 'MO'`
   - `roaming_destination_id = 87`
   - `opposite_number NOT LIKE '60%'`
7. `Domestic IDD MO SMS`
   - mapped from monthly row `8`
   - `rat_type = 'SM'`
   - `roaming_destination_id = 87`
   - `opposite_number NOT LIKE '60%'`
8. `Roaming Data 4G / 5G`
   - mapped from monthly rows `9` and `10`
   - `rat_type IN ('4G', '5G')`
   - `roaming_destination_id != 87`
   - both 4G and 5G are emitted under one category label
9. `Roaming MT Voice (Camel/S8HR)`
   - mapped from monthly row `12`
   - `rat_type = 'VO'`
   - `service_type_sub_cd = 'MT'`
   - `roaming_destination_id != 87`
   - `opposite_number NOT LIKE '60%'`
10. `Roaming MO Voice (Camel/S8HR)`
   - mapped from monthly row `11`
   - `rat_type = 'VO'`
   - `service_type_sub_cd = 'MO'`
   - `roaming_destination_id != 87`
   - `opposite_number NOT LIKE '60%'`
11. `Roaming SMS MO (Camel/S8HR)`
   - mapped from monthly row `13`
   - `rat_type = 'SM'`
   - `roaming_destination_id != 87`
   - no `service_type_sub_cd` filter is applied because SMS direction is not effective in `usage_logs`
12. `Premium Special Number Voice`
   - mapped from monthly row `14`
   - `rat_type = 'VO'`
   - `service_type_sub_cd = 'MO'`
   - `opposite_number` is one of:
     - `600380008000`
     - `60103`
     - `60100`
     - `6015454`
     - `6015300`
     - `6015353`
     - `6015404`
     - `6015444`
     - `6015777`
   - or starts with:
     - `601300`
     - `601700`
     - `601800`
   - and has length less than `12`

### Category precedence in usage_logs

The detail report needs each `usage_logs` document to be emitted only once.

Because of that, category matching is applied in a fixed order. Important cases:

- `Premium Special Number Voice` is checked before generic domestic voice categories.
- `Roaming Data 4G / 5G` is a single merged category.

## SMSC A2P Categories

Rows `13` and `14` come from `smsc_cdrs`.

Shared output mapping:

- `Event/Call Start Date Time` -> `delivery_date`
- `Call Duration (second) / Total Volume (UL +DL ) in bytes` -> blank
- `MSISDN A#` -> `addr_dst_digits`
- `MSISDN B#` -> `addr_src_digits`
- `IMSI` -> `imsi`
- `Source Record ID` -> `message_id`

Common filter:

- `origination_type = 'SMPP'`
- `message_delivery_status = 'success'`
- date range on `delivery_date`

Category logic:

13. `Non-Profit A2P`
   - mapped from monthly row `15`
   - `addr_src_digits LIKE '2%'`
   - or `addr_src_digits = '601170337777'`
14. `Commercial A2P`
   - mapped from monthly row `16`
   - `addr_src_digits LIKE '6%'`
   - excluding `601170337777` so one SMSC document is not emitted twice

## Sorting

Output rows are written in this order:

- `Category No.` ascending
- event datetime ascending
- Mongo record id ascending as a stable tie-breaker

## Index Usage

The script uses existing indexes when possible:

- If `msisdn_a` is provided for `usage_logs`, it hints `ix_msisdn_usage_start_time`
- If `msisdn_a` is provided for `smsc_cdrs`, it hints `ix_addr_dst_digits_delivery_date`

Without `msisdn_a`, MongoDB chooses the plan itself.

## Run

Install dependencies:

```powershell
pip install PyYAML pymongo
```

Run with config values:

```powershell
python .\generate_report.py
```

Run with CLI overrides:

```powershell
python .\generate_report.py --start-date 2026-04-01 --end-date 2026-04-01 --msisdn-a 601169070013
```

## Verification

Each output row includes:

- `Source Collection`
- `Source Record ID`
- `Mongo Record ID`

These two columns are included specifically so the original Mongo document can be verified later.
