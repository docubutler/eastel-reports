"""
===============================================================================
REPORT: International Direct Dial (IDD) Voice Calls by Destination Country
===============================================================================

PURPOSE
-------
This script generates an IDD Voice traffic report showing:

- Malaysian subscribers (home network only)
- Making outgoing voice calls (MO)
- To international destinations (non-Malaysia numbers)

The report groups calls by destination country using the country code
reference table and produces:

    Service Type
    Charge Type
    Country
    No. of Calls
    MOU (Minutes of Usage)

-------------------------------------------------------------------------------
BUSINESS LOGIC
-------------------------------------------------------------------------------

Included Records:
-----------------
- rat_type = 'VO'
- service_type_sub_cd = 'MO'
- roaming_destination_id = 87 (subscriber is in Malaysia)
- act_usage_unit > 0
- opposite_number does NOT start with '60' (international destination)
- usage_start_time within reporting period

Excluded Records:
-----------------
- Incoming voice calls (MT)
- Domestic Malaysia calls
- Roaming subscribers
- SMS/Data records

-------------------------------------------------------------------------------
COUNTRY MAPPING LOGIC
-------------------------------------------------------------------------------

Destination country is derived from the called number
(opposite_number) using the country_code collection.

Example:

    6591234567  -> Singapore (65)
    61412345678 -> Australia (61)
    91987654321 -> India (91)

Longest-prefix matching is used to ensure correct identification.

Example:

    12425551234

Matches:
    1      = USA/Canada
    1242   = Bahamas

Selected:
    1242 (longest match)

-------------------------------------------------------------------------------
INPUT COLLECTIONS
-------------------------------------------------------------------------------

Usage Collection:
    usage_logs

Country Code Collection:
    country_code

Country Code Document Format:
    {
        "country": "Singapore",
        "country_code": "65"
    }

-------------------------------------------------------------------------------
OUTPUT FILE
-------------------------------------------------------------------------------

idd_voice_by_country.csv

-------------------------------------------------------------------------------
SAMPLE OUTPUT
-------------------------------------------------------------------------------

Service Type,Charge Type,Country,No. of Calls,MOU

Voice,Voice MO,Australia,1,0.52
Voice,Voice MO,Austria,16,1.58
Voice,Voice MO,Bangladesh,1256,3273.38
Voice,Voice MO,China,48,78.75
Voice,Voice MO,India,151,234.10
Voice,Voice MO,Indonesia,159,395.50
Voice,Voice MO,Singapore,13,58.27
Voice,Voice MO,Thailand,13,31.03
Voice,Voice MO,United States,1,0.02
Voice,Voice MO,Vietnam,11,10.50

-------------------------------------------------------------------------------
COLUMN DEFINITIONS
-------------------------------------------------------------------------------

Service Type
    Always "Voice"

Charge Type
    Always "Voice MO"

Country
    Destination country derived from country code

No. of Calls
    Count of matching voice call records

MOU
    Sum(act_usage_unit) / 60
    Reported in minutes

-------------------------------------------------------------------------------
AUTHOR NOTES
-------------------------------------------------------------------------------

This script performs country-code matching in Python rather than MongoDB.

Reason:
- country_code is very small (~200 records)
- longest-prefix matching is easier in Python
- avoids expensive MongoDB lookup/regex operations
- generally performs better on large usage datasets

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

OUTPUT_FILE = "idd_voice_by_country.csv"


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
# Calling international numbers
# =========================

cursor = usage_col.find(
    {
        "rat_type": "VO",
        "service_type_sub_cd": "MO",
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

results = defaultdict(
    lambda: {
        "calls": 0,
        "mou": 0.0
    }
)

for record in cursor:

    number = str(record.get("opposite_number", "")).strip()

    if not number or number.lower() == "none":
        continue

    if number.startswith("60"):
        continue

    country = "UNMAPPED"

    for cc in country_codes:
        if number.startswith(cc["code"]):
            country = cc["country"]
            break

    results[country]["calls"] += 1
    results[country]["mou"] += to_float(record.get("act_usage_unit")) / 60.0

# =========================
# Convert to DataFrame
# =========================

rows = []

for country, data in sorted(results.items()):

    rows.append(
        {
            "Service Type": "Voice",
            "Charge Type": "Voice MO",
            "Country": country,
            "No. of Calls": data["calls"],
            "MOU": round(data["mou"], 2)
        }
    )

df = pd.DataFrame(rows)

# Optional: sort by country
df = df.sort_values("Country")

# =========================
# Export CSV
# =========================

df.to_csv(OUTPUT_FILE, index=False)

print(f"Report generated: {OUTPUT_FILE}")
print(f"Total countries: {len(df)}")
