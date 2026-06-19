"""
===============================================================================
REPORT: International SMS by Destination Country
===============================================================================

PURPOSE
-------
This script generates an International SMS report showing:

- Malaysian subscribers (home network only)
- Sending SMS to international destinations (non-Malaysia numbers)

The report groups SMS records by destination country using the country code
reference table and produces:

    Service Type
    Charge Type
    Country
    No. of SMS

-------------------------------------------------------------------------------
BUSINESS LOGIC
-------------------------------------------------------------------------------

Included Records:
-----------------
- rat_type = 'SM'
- roaming_destination_id = 87 (subscriber is in Malaysia)
- act_usage_unit > 0
- opposite_number does NOT start with '60' (international destination)
- usage_start_time within reporting period

Excluded Records:
-----------------
- Domestic Malaysia SMS
- Roaming subscribers
- Voice/Data records

Note:
-----
- service_type_sub_cd is not used for SMS because MO/MT is not populated for
  SMS in this dataset.

-------------------------------------------------------------------------------
COUNTRY MAPPING LOGIC
-------------------------------------------------------------------------------

Destination country is derived from the destination number
(opposite_number) using the country_code collection.

Longest-prefix matching is used to ensure correct identification.

-------------------------------------------------------------------------------
INPUT COLLECTIONS
-------------------------------------------------------------------------------

Usage Collection:
    usage_logs

Country Code Collection:
    country_code

-------------------------------------------------------------------------------
OUTPUT FILE
-------------------------------------------------------------------------------

idd_sms_by_country.csv

===============================================================================
"""

from pymongo import MongoClient
from bson.decimal128 import Decimal128
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import pandas as pd

# =========================
# Configuration
# =========================

MONGO_URI = "mongodb+srv://prodUser:CxNFHCraErGeEsYI@easteldataanalysis.zwi2ei.mongodb.net/?appName=EastelDataAnalysis"
DATABASE = "eastel-data"

START_DATE = datetime(2026, 4, 1)
END_DATE = datetime(2026, 5, 1)  # exclusive

OUTPUT_FILE = "idd_sms_by_country.csv"


def to_float(value, default=0.0):
    """Convert Mongo/Python numeric values to float safely."""
    if value is None or value == "":
        return default

    if isinstance(value, Decimal128):
        return float(value.to_decimal())

    if isinstance(value, Decimal):
        return float(value)

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# =========================
# Mongo Connection
# =========================

client = MongoClient(MONGO_URI)
db = client[DATABASE]

usage_col = db["usage_logs"]
country_col = db["country_code"]

# =========================
# Load Country Codes
# Longest code first so:
# 880 beats 88
# 1242 beats 1
# =========================

country_codes = sorted(
    (
        {
            "country": doc["country"],
            "code": str(doc["country_code"])
        }
        for doc in country_col.find(
            {},
            {"_id": 0, "country": 1, "country_code": 1}
        )
    ),
    key=lambda x: len(x["code"]),
    reverse=True
)

# =========================
# Query Usage Records
# Home subscriber (Malaysia)
# Sending SMS to international numbers
# =========================

cursor = usage_col.find(
    {
        "rat_type": "SM",
        "roaming_destination_id": 87,
        "act_usage_unit": {"$gt": 0},
        "usage_start_time": {
            "$gte": START_DATE,
            "$lt": END_DATE
        }
    },
    {
        "_id": 0,
        "opposite_number": 1,
        "act_usage_unit": 1
    }
)

# =========================
# Aggregate Results
# =========================

results = defaultdict(lambda: {"sms_count": 0})

for record in cursor:
    number = str(record.get("opposite_number", "")).strip()

    if not number or number.lower() == "none":
        continue

    if number.startswith("60"):
        continue

    if to_float(record.get("act_usage_unit")) <= 0:
        continue

    country = "UNMAPPED"

    for cc in country_codes:
        if number.startswith(cc["code"]):
            country = cc["country"]
            break

    results[country]["sms_count"] += 1

# =========================
# Convert to DataFrame
# =========================

rows = []

for country, data in sorted(results.items()):
    rows.append(
        {
            "Service Type": "SMS",
            "Charge Type": "SMS MO",
            "Country": country,
            "No. of SMS": data["sms_count"]
        }
    )

df = pd.DataFrame(rows)

if not df.empty:
    df = df.sort_values("Country")

# =========================
# Export CSV
# =========================

df.to_csv(OUTPUT_FILE, index=False)

print(f"Report generated: {OUTPUT_FILE}")
print(f"Total countries: {len(df)}")
