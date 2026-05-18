# SMSC CDR To Mongo Sync

This folder contains the MongoDB workflow for importing SMSC CDR files.

## Files

- `smsc_cdr_to_mongo_sync.py`: main importer
- `create_mongo_smsc_cdr_collection.py`: creates Mongo collections and indexes
- `config.yml`: runtime configuration
- `requirements.txt`: Python dependencies

## Behavior

- Reads files matching `cdr.log.YYYY-MM-DD`
- Only processes files whose date is before the current day
- Backfills all historical eligible files on first run
- Uses Mongo upserts keyed by `source_path + line_number`
- Uses Mongo state for lock, resume, and file progress
- Logs to console and a configured log file

## Uniqueness

The importer currently treats one CDR line as unique by:

- `source_path`
- `line_number`

This is deliberate. `MESSAGE_ID` is stored and indexed for querying, but it is not used as a unique key because it is not globally unique in the source data.

For example, the same logical id can appear in multiple related records such as:

- a `message` record
- a `dlr` record

So using `MESSAGE_ID` as a unique identifier would risk collapsing distinct CDR rows into one document.

## CDR field spec

| Position | Column | Meaning |
| -------- | ------ | ------- |
| 1 | `DELIVERY_DATE` | Time CDR generated / delivery completed |
| 2 | `SUBMIT_DATE` | Time SMS reached SMSC |
| 3 | `ADDR_SRC_DIGITS` | Source number |
| 4 | `ADDR_SRC_TON` | Source TON |
| 5 | `ADDR_SRC_NPI` | Source NPI |
| 6 | `ADDR_DST_DIGITS` | Destination number |
| 7 | `ADDR_DST_TON` | Destination TON |
| 8 | `ADDR_DST_NPI` | Destination NPI |
| 9 | `Message_Delivery_Status` | `success` / `failed` / `ocs_rejected` etc |
| 10 | `ORIGINATION_TYPE` | `SMPP` / `SS7_MO` / `LOCAL_ORIG` etc |
| 11 | `MESSAGE_TYPE` | `message` / `dlr` |
| 12 | `ORIG_SYSTEM_ID` | SMPP system id |
| 13 | `MESSAGE_ID` | Internal message id |
| 14 | `DVL_MESSAGE_ID` | SMPP delivery-side message id |
| 15 | `RECEIPT_LOCAL_MESSAGE_ID` | Original message id for DLR correlation |
| 16 | `NNN_DIGITS` | MSISDN from SRI response |
| 17 | `IMSI` | Subscriber IMSI |
| 18 | `CORR_ID` | Home-routing correlation id |
| 19 | `ORIGINATOR_SCCP_ADDRESS` | SCCP source address |
| 20 | `MtServiceCenterAddress` | SMSC GT address |
| 21 | `ORIG_NETWORK_ID` | Origin network id |
| 22 | `NETWORK_ID` | Destination network id |
| 23 | `MPROC_NOTES` | Notes from processing rules |
| 24 | `MSG_PARTS` | Multipart SMS count |
| 25 | `CHAR_NUMBERS` | Character count |
| 26 | `PROCESSING_TIME` | SMSC processing time (ms) |
| 27 | `DELIVERY_DELAY` | Delivery delay (ms) |
| 28 | `SCHEDULE_DELIVERY_DELAY` | Scheduled delay |
| 29 | `DELIVERY_COUNT` | Delivery attempts |
| 30 | `First 20 characters of SMS` | SMS preview |
| 31 | `Reason_For_Failure` | Failure reason |

## Run

Install dependencies:

```powershell
pip install -r .\requirements.txt
```

Create collections and indexes:

```powershell
python .\create_mongo_smsc_cdr_collection.py
```

Run once:

```powershell
python .\smsc_cdr_to_mongo_sync.py --run-once
```

Run continuously:

```powershell
python .\smsc_cdr_to_mongo_sync.py --continuous
```

## Config

Edit [config.yml](/d:/DB_repos/eastel-reports/eastel-report-scripts/smsc-cdr-to-mongo-sync/config.yml) before running.
