from pymongo import MongoClient
import pandas as pd

# =========================
# MongoDB Configuration
# =========================
MONGO_URI = "mongodb+srv://prodUser:CxNFHCraErGeEsYI@easteldataanalysis.zwi2ei.mongodb.net/?appName=EastelDataAnalysis"
DB_NAME = "eastel-data"
COLLECTION_NAME = "roaming_destination"

# =========================
# CSV File
# =========================
CSV_FILE = "roaming-destination.csv"

# =========================
# Connect to MongoDB
# =========================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Create collection if it doesn't exist
if COLLECTION_NAME not in db.list_collection_names():
    db.create_collection(COLLECTION_NAME)

collection = db[COLLECTION_NAME]

# =========================
# Read CSV
# =========================
df = pd.read_csv(CSV_FILE)

# Optional: convert IDs to integers
df["roaming_destination_id"] = pd.to_numeric(
    df["roaming_destination_id"],
    errors="coerce"
).astype("Int64")

df["mcc"] = pd.to_numeric(
    df["mcc"],
    errors="coerce"
).astype("Int64")

# Convert NaN to None for MongoDB
records = df.where(pd.notnull(df), None).to_dict("records")

# =========================
# Insert into MongoDB
# =========================
if records:
    result = collection.insert_many(records)
    print(f"Inserted {len(result.inserted_ids)} documents.")
else:
    print("No records found in CSV.")

print(f"Collection: {COLLECTION_NAME}")