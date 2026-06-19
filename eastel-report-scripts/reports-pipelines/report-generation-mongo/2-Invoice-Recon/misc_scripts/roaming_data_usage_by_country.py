"""
===============================================================================
REPORT: Roaming Data Usage by Country
===============================================================================

PURPOSE
-------
This script generates a roaming data usage report showing:

- Subscribers using data while outside Malaysia
- Grouped by visited country / roaming network
- 4G and 5G usage combined

The report produces:

    Service Type
    Charge Type
    Country
    Usage (Mbyte)

-------------------------------------------------------------------------------
BUSINESS LOGIC
-------------------------------------------------------------------------------

Included Records:
-----------------
- rat_type IN ('4G', '5G')
- roaming_destination_id != 87
- act_usage_unit > 0
- usage_start_time within reporting period

Excluded Records:
-----------------
- Malaysia / home network usage
- Zero-usage records
- Non-data records

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

roaming_data_usage_by_country.csv

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

OUTPUT_FILE = "roaming_data_usage_by_country.csv"


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


def to_int(value, default=None):
    """Convert Mongo/Python numeric values to int safely."""
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
    """Normalize roaming destination label to Country-Network format."""
    roaming_destination_name = str(doc.get("roaming_destination_name", "") or "").strip()
    country = str(doc.get("country", "") or "").strip()

    if roaming_destination_name:
        return roaming_destination_name.replace(": ", "-").replace(":", "-")

    if country:
        return country

    return "UNMAPPED"


# =========================
# Mongo Connection
# =========================

client = MongoClient(MONGO_URI)
db = client[DATABASE]

usage_col = db["usage_logs"]
roaming_col = db["roaming_destination"]

# =========================
# Load Roaming Destination Labels
# =========================

destination_labels = {
    int(doc["roaming_destination_id"]): build_destination_label(doc)
    for doc in roaming_col.find(
        {},
        {"_id": 0, "roaming_destination_id": 1, "country": 1, "roaming_destination_name": 1}
    )
    if doc.get("roaming_destination_id") is not None
}

# =========================
# Query Usage Records
# Roaming subscriber data usage outside Malaysia
# =========================

cursor = usage_col.find(
    {
        "rat_type": {"$in": ["4G", "5G"]},
        "roaming_destination_id": {"$ne": 87},
        "act_usage_unit": {"$gt": 0},
        # rating_group 500003 is used for MCMC/MERC999 data.
        # Not filtering it out for now.
        # "rating_group": {"$nin": ["500003"]},
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

# =========================
# Aggregate Results
# =========================

results = defaultdict(lambda: {"usage_mbyte": 0.0})

for record in cursor:
    destination_id = to_int(record.get("roaming_destination_id"))
    if destination_id is None:
        label = "UNMAPPED"
    else:
        label = destination_labels.get(destination_id, f"UNMAPPED-{destination_id}")

    usage_bytes = to_float(record.get("act_usage_unit"))
    if usage_bytes <= 0:
        continue

    results[label]["usage_mbyte"] += usage_bytes / 1048576.0

# =========================
# Convert to DataFrame
# =========================

rows = []

for country, data in sorted(results.items()):
    rows.append(
        {
            "Service Type": "Data Roaming",
            "Charge Type": "MO",
            "Country": country,
            "Usage (Mbyte)": round(data["usage_mbyte"], 2)
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
