"""
===============================================================================
REPORT: Roaming Voice Usage by Country
===============================================================================

PURPOSE
-------
This script generates a roaming voice report showing:

- Subscribers making MO voice calls while outside Malaysia
- Grouped by visited country / roaming network

The report produces:

    Service Type
    Charge Type
    Country
    No. of Calls
    MOU

-------------------------------------------------------------------------------
BUSINESS LOGIC
-------------------------------------------------------------------------------

Included Records:
-----------------
- rat_type = 'VO'
- service_type_sub_cd = 'MO'
- roaming_destination_id != 87
- act_usage_unit > 0
- usage_start_time within reporting period

Excluded Records:
-----------------
- Malaysia / home network usage
- Incoming voice calls
- Zero-usage records
- SMS/Data records

-------------------------------------------------------------------------------
INPUT COLLECTIONS
-------------------------------------------------------------------------------

Usage Collection:
    usage_logs

Roaming Destination Collection:
    roaming_destination

-------------------------------------------------------------------------------
OUTPUT FILE
-------------------------------------------------------------------------------

roaming_voice_usage_by_country.csv

===============================================================================
"""

from pymongo import MongoClient
from bson.decimal128 import Decimal128
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import pandas as pd

MONGO_URI = "mongodb+srv://prodUser:CxNFHCraErGeEsYI@easteldataanalysis.zwi2ei.mongodb.net/?appName=EastelDataAnalysis"
DATABASE = "eastel-data"

START_DATE = datetime(2026, 4, 1)
END_DATE = datetime(2026, 5, 1)  # exclusive

OUTPUT_FILE = "roaming_voice_usage_by_country.csv"


def to_float(value, default=0.0):
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


def to_int(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, Decimal128):
        return int(value.to_decimal())
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_destination_label(doc):
    roaming_destination_name = str(doc.get("roaming_destination_name", "") or "").strip()
    country = str(doc.get("country", "") or "").strip()
    if roaming_destination_name:
        return roaming_destination_name.replace(": ", "-").replace(":", "-")
    if country:
        return country
    return "UNMAPPED"


client = MongoClient(MONGO_URI)
db = client[DATABASE]

usage_col = db["usage_logs"]
roaming_col = db["roaming_destination"]

destination_labels = {
    int(doc["roaming_destination_id"]): build_destination_label(doc)
    for doc in roaming_col.find(
        {},
        {"_id": 0, "roaming_destination_id": 1, "country": 1, "roaming_destination_name": 1}
    )
    if doc.get("roaming_destination_id") is not None
}

cursor = usage_col.find(
    {
        "rat_type": "VO",
        "service_type_sub_cd": "MO",
        "roaming_destination_id": {"$ne": 87},
        "act_usage_unit": {"$gt": 0},
        "usage_start_time": {
            "$gte": START_DATE,
            "$lt": END_DATE
        }
    },
    {
        "_id": 0,
        "roaming_destination_id": 1,
        "act_usage_unit": 1
    }
)

results = defaultdict(lambda: {"calls": 0, "mou": 0.0})

for record in cursor:
    destination_id = to_int(record.get("roaming_destination_id"))
    if destination_id is None:
        label = "UNMAPPED"
    else:
        label = destination_labels.get(destination_id, f"UNMAPPED-{destination_id}")

    usage_seconds = to_float(record.get("act_usage_unit"))
    if usage_seconds <= 0:
        continue

    results[label]["calls"] += 1
    results[label]["mou"] += usage_seconds / 60.0

rows = []

for country, data in sorted(results.items()):
    rows.append(
        {
            "Service Type": "Voice Roaming",
            "Charge Type": "MO",
            "Country": country,
            "No. of Calls": data["calls"],
            "MOU": round(data["mou"], 2)
        }
    )

df = pd.DataFrame(rows)

if not df.empty:
    df = df.sort_values("Country")

df.to_csv(OUTPUT_FILE, index=False)

print(f"Report generated: {OUTPUT_FILE}")
print(f"Total countries: {len(df)}")
